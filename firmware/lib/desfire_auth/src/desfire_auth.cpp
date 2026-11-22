#include "desfire_auth.h"

#include <cstring>
#include <mbedtls/aes.h>
#include <mbedtls/platform_util.h>

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

constexpr uint8_t CMD_ADDITIONAL_FRAME = 0xAF;
constexpr uint8_t CMD_SELECT_APP       = 0x5A;
constexpr uint8_t CMD_AUTH_AES         = 0xAA;
constexpr uint8_t STATUS_OK            = 0x00;

// AES-128 CBC over whole 16-byte blocks. `iv` is advanced in place by mbedtls.
// Returns false if mbedtls reports an error.
bool aesCbc(const uint8_t key[16], int mode, uint8_t iv[16],
            const uint8_t* in, uint8_t* out, size_t len) {
  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  int rc = (mode == MBEDTLS_AES_ENCRYPT)
               ? mbedtls_aes_setkey_enc(&ctx, key, 128)
               : mbedtls_aes_setkey_dec(&ctx, key, 128);
  if (rc == 0) rc = mbedtls_aes_crypt_cbc(&ctx, mode, len, iv, in, out);
  mbedtls_aes_free(&ctx);  // also wipes the expanded key schedule
  return rc == 0;
}

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
  ~AuthScratch() { mbedtls_platform_zeroize(this, sizeof(*this)); }
};

}  // namespace

bool DesfireAuth::selectApplication(const uint8_t aid[3]) {
  DesfireResponse r;
  if (!t_.transceive(CMD_SELECT_APP, aid, 3, r)) return false;
  return r.status == STATUS_OK;
}

bool DesfireAuth::authenticateAes(uint8_t keyNo, const uint8_t key[16],
                                  uint8_t sessionKey[16]) {
  memset(sessionKey, 0, 16);
  AuthScratch s;

  // Step 1 — card replies 0xAF + E(RndB).
  DesfireResponse r1;
  if (!t_.transceive(CMD_AUTH_AES, &keyNo, 1, r1)) return false;
  if (r1.status != CMD_ADDITIONAL_FRAME || r1.data.size() != 16) return false;

  uint8_t ekRndB[16];
  memcpy(ekRndB, r1.data.data(), 16);

  // Recover RndB: decrypt E(RndB) with IV = 0.
  uint8_t iv[16] = {0};
  if (!aesCbc(key, MBEDTLS_AES_DECRYPT, iv, ekRndB, s.rndB, 16)) return false;

  // Our challenge token: RndA || rot(RndB).
  fill_random(s.rndA, 16);
  rotLeft1(s.rndB, s.rndBrot);
  memcpy(s.plain, s.rndA, 16);
  memcpy(s.plain + 16, s.rndBrot, 16);

  // Encrypt token, CBC chaining from the received ciphertext E(RndB).
  // >>> Verify this IV convention against Proxmark before trusting it. <<<
  uint8_t ivEnc[16];
  memcpy(ivEnc, ekRndB, 16);
  uint8_t token[32];
  if (!aesCbc(key, MBEDTLS_AES_ENCRYPT, ivEnc, s.plain, token, 32)) return false;

  // Step 2 — card replies 0x00 + E(rot(RndA)).
  DesfireResponse r2;
  if (!t_.transceive(CMD_ADDITIONAL_FRAME, token, 32, r2)) return false;
  if (r2.status != STATUS_OK || r2.data.size() != 16) return false;

  // Decrypt with IV = last ciphertext block we sent.
  uint8_t ivDec[16];
  memcpy(ivDec, token + 16, 16);
  if (!aesCbc(key, MBEDTLS_AES_DECRYPT, ivDec, r2.data.data(), s.rndArotRecv,
              16)) {
    return false;
  }

  // The card must return rot(RndA): proof it holds the same key.
  rotLeft1(s.rndA, s.rndArotExpected);
  if (memcmp(s.rndArotRecv, s.rndArotExpected, 16) != 0) return false;

  // AES session key: RndA[0..3] | RndB[0..3] | RndA[12..15] | RndB[12..15].
  memcpy(sessionKey + 0,  s.rndA + 0,  4);
  memcpy(sessionKey + 4,  s.rndB + 0,  4);
  memcpy(sessionKey + 8,  s.rndA + 12, 4);
  memcpy(sessionKey + 12, s.rndB + 12, 4);
  return true;
}

}  // namespace opencylinder
