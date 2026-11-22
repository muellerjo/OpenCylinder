#include "desfire_auth.h"

#include <cstring>

#include "desfire_crypto.h"

// Random source: hardware RNG on ESP32, std fallback for PC unit tests.
// (On nRF52 / STM32 ports, swap in the platform TRNG here.)
#if defined(ESP_PLATFORM)
#include "esp_random.h"
static void fill_random(uint8_t* buf, size_t n) { esp_fill_random(buf, n); }
#else
#include <random>
static void fill_random(uint8_t* buf, size_t n) {
  static std::random_device rd;
  for (size_t i = 0; i < n; ++i) buf[i] = static_cast<uint8_t>(rd());
}
#endif

namespace opencylinder {
namespace {

using crypto::aesCbc;
using crypto::wipe;

constexpr uint8_t CMD_ADDITIONAL_FRAME = 0xAF;
constexpr uint8_t CMD_SELECT_APP       = 0x5A;
constexpr uint8_t CMD_AUTH_AES         = 0xAA;
constexpr uint8_t CMD_READ_DATA        = 0xBD;
constexpr uint8_t CMD_GET_CARD_UID     = 0x51;
constexpr uint8_t STATUS_OK            = 0x00;

// Rotate a 16-byte block left by one byte.
void rotLeft1(const uint8_t in[16], uint8_t out[16]) {
  memcpy(out, in + 1, 15);
  out[15] = in[0];
}

// Holds every secret intermediate of one authentication, wiped on scope exit
// so random numbers / plaintexts don't linger on the stack.
struct AuthScratch {
  uint8_t rndA[16], rndB[16], rndBrot[16], plain[32];
  uint8_t rndArotRecv[16], rndArotExpected[16];
  ~AuthScratch() { wipe(this, sizeof(*this)); }
};

void putLe24(uint8_t* p, uint32_t v) {
  p[0] = static_cast<uint8_t>(v);
  p[1] = static_cast<uint8_t>(v >> 8);
  p[2] = static_cast<uint8_t>(v >> 16);
}

}  // namespace

DesfireAuth::~DesfireAuth() { resetSession(); }

bool DesfireAuth::fail(const char* where, uint8_t status) {
  lastError_ = where;
  lastStatus_ = status;
  resetSession();
  return false;
}

void DesfireAuth::resetSession() {
  authenticated_ = false;
  wipe(sessionKey_, sizeof sessionKey_);
  wipe(iv_, sizeof iv_);
}

bool DesfireAuth::selectApplication(const uint8_t aid[3]) {
  resetSession();
  DesfireResponse r;
  if (!t_.transceive(CMD_SELECT_APP, aid, 3, r)) return fail("select: no response");
  if (r.status != STATUS_OK) return fail("select: card status", r.status);
  return true;
}

bool DesfireAuth::authenticateAes(uint8_t keyNo, const uint8_t key[16]) {
  resetSession();
  AuthScratch s;

  // Step 1 — card replies 0xAF + E(RndB).
  DesfireResponse r1;
  if (!t_.transceive(CMD_AUTH_AES, &keyNo, 1, r1)) return fail("auth step 1: no response");
  if (r1.status != CMD_ADDITIONAL_FRAME) return fail("auth step 1: card status", r1.status);
  if (r1.data.size() != 16) return fail("auth step 1: wrong length", r1.status);

  uint8_t ekRndB[16];
  memcpy(ekRndB, r1.data.data(), 16);

  // Recover RndB: decrypt E(RndB) with IV = 0.
  uint8_t iv[16] = {0};
  if (!aesCbc(key, false, iv, ekRndB, s.rndB, 16)) return fail("auth: aes error");

  // Our challenge token: RndA || rot(RndB).
  fill_random(s.rndA, 16);
  rotLeft1(s.rndB, s.rndBrot);
  memcpy(s.plain, s.rndA, 16);
  memcpy(s.plain + 16, s.rndBrot, 16);

  // Encrypt token, CBC chaining from the received ciphertext E(RndB).
  uint8_t ivEnc[16];
  memcpy(ivEnc, ekRndB, 16);
  uint8_t token[32];
  if (!aesCbc(key, true, ivEnc, s.plain, token, 32)) return fail("auth: aes error");

  // Step 2 — card replies 0x00 + E(rot(RndA)).
  DesfireResponse r2;
  if (!t_.transceive(CMD_ADDITIONAL_FRAME, token, 32, r2)) return fail("auth step 2: no response");
  if (r2.status != STATUS_OK) return fail("auth step 2: card status", r2.status);
  if (r2.data.size() != 16) return fail("auth step 2: wrong length", r2.status);

  // Decrypt with IV = last ciphertext block we sent.
  uint8_t ivDec[16];
  memcpy(ivDec, token + 16, 16);
  if (!aesCbc(key, false, ivDec, r2.data.data(), s.rndArotRecv, 16)) return fail("auth: aes error");

  // The card must return rot(RndA): proof it holds the same key.
  rotLeft1(s.rndA, s.rndArotExpected);
  if (memcmp(s.rndArotRecv, s.rndArotExpected, 16) != 0) return fail("auth: card proof mismatch");

  // AES session key: RndA[0..3] | RndB[0..3] | RndA[12..15] | RndB[12..15].
  memcpy(sessionKey_ + 0,  s.rndA + 0,  4);
  memcpy(sessionKey_ + 4,  s.rndB + 0,  4);
  memcpy(sessionKey_ + 8,  s.rndA + 12, 4);
  memcpy(sessionKey_ + 12, s.rndB + 12, 4);
  memset(iv_, 0, sizeof iv_);  // EV1 secure messaging starts with IV = 0
  authenticated_ = true;
  return true;
}

bool DesfireAuth::readDataEncrypted(uint8_t fileNo, uint32_t offset,
                                    uint32_t length, std::vector<uint8_t>& out) {
  out.clear();
  if (!authenticated_) return fail("read: not authenticated");
  if (length == 0 || length > kMaxReadLength || offset > 0xFFFFFF) {
    return fail("read: bad length/offset");
  }
  // Command header: file no | offset (3, LE) | length (3, LE).
  uint8_t hdr[7];
  hdr[0] = fileNo;
  putLe24(hdr + 1, offset);
  putLe24(hdr + 4, length);
  return exchangeEncrypted(CMD_READ_DATA, hdr, sizeof hdr, length, out);
}

bool DesfireAuth::getCardUid(uint8_t uid[7]) {
  if (!authenticated_) return fail("get uid: not authenticated");
  std::vector<uint8_t> out;
  if (!exchangeEncrypted(CMD_GET_CARD_UID, nullptr, 0, 7, out)) return false;
  memcpy(uid, out.data(), 7);
  wipe(out.data(), out.size());
  return true;
}

bool DesfireAuth::exchangeEncrypted(uint8_t cmd, const uint8_t* hdr, size_t hdrLen,
                                    uint32_t length, std::vector<uint8_t>& out) {
  out.clear();
  // EV1 secure messaging: every command updates the IV with a CMAC over
  // cmd || header, computed with the session key, even though it is sent plain.
  uint8_t cmdMsg[1 + 16];
  if (hdrLen > 16) return fail("exchange: header too long");
  cmdMsg[0] = cmd;
  if (hdrLen) memcpy(cmdMsg + 1, hdr, hdrLen);
  if (!crypto::cmacAes128(sessionKey_, iv_, cmdMsg, 1 + hdrLen, iv_)) {
    return fail("exchange: cmac error");
  }

  // Collect the encrypted response; long responses come in frames (0xAF).
  std::vector<uint8_t> enc;
  DesfireResponse r;
  bool ok = t_.transceive(cmd, hdr, hdrLen, r);
  while (ok && r.status == CMD_ADDITIONAL_FRAME) {
    enc.insert(enc.end(), r.data.begin(), r.data.end());
    ok = t_.transceive(CMD_ADDITIONAL_FRAME, nullptr, 0, r);
  }
  if (!ok) return fail("exchange: no response");
  if (r.status != STATUS_OK) return fail("exchange: card status", r.status);
  enc.insert(enc.end(), r.data.begin(), r.data.end());

  // Plaintext = data || CRC32(data || status) || zero padding, AES-CBC.
  const size_t expected = ((length + 4 + 15) / 16) * 16;
  if (enc.size() != expected) return fail("exchange: wrong length", r.status);
  std::vector<uint8_t> plain(enc.size());
  uint8_t nextIv[16];
  memcpy(nextIv, enc.data() + enc.size() - 16, 16);  // IV for the next command
  if (!aesCbc(sessionKey_, false, iv_, enc.data(), plain.data(), enc.size())) {
    return fail("exchange: aes error");
  }
  memcpy(iv_, nextIv, 16);

  uint32_t crc = crypto::crc32Desfire(plain.data(), length);
  const uint8_t status = STATUS_OK;
  crc = crypto::crc32Desfire(&status, 1, crc);
  const uint8_t* c = plain.data() + length;
  const uint32_t cardCrc = static_cast<uint32_t>(c[0]) | (static_cast<uint32_t>(c[1]) << 8) |
                           (static_cast<uint32_t>(c[2]) << 16) |
                           (static_cast<uint32_t>(c[3]) << 24);
  bool padOk = true;
  for (size_t i = length + 4; i < plain.size(); ++i) padOk &= (plain[i] == 0);

  if (crc != cardCrc || !padOk) {
    wipe(plain.data(), plain.size());
    return fail("exchange: CRC/padding mismatch");
  }
  out.assign(plain.begin(), plain.begin() + length);
  wipe(plain.data(), plain.size());
  return true;
}

}  // namespace opencylinder
