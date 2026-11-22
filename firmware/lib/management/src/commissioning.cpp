#include "commissioning.h"

#include <cstring>
#include <mbedtls/gcm.h>
#include <mbedtls/md.h>
#include <mbedtls/platform_util.h>

#include "management.h"

namespace opencylinder {
namespace {

constexpr char kHkdfInfo[] = "OpenCylinder commissioning v1";
constexpr size_t kEphKey = 65, kNonce = 12, kTag = 16;
constexpr size_t kPlainFixed = 3 + 3 + 16 + 16 + 16 + 65 + 2 + 1;  // + 2 per zone

uint16_t le16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }

bool hmacSha256(const uint8_t* key, size_t keyLen, const uint8_t* a, size_t aLen,
                const uint8_t* b, size_t bLen, uint8_t out[32]) {
  const mbedtls_md_info_t* md = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  int rc = mbedtls_md_setup(&ctx, md, 1);
  if (rc == 0) rc = mbedtls_md_hmac_starts(&ctx, key, keyLen);
  if (rc == 0 && aLen) rc = mbedtls_md_hmac_update(&ctx, a, aLen);
  if (rc == 0 && bLen) rc = mbedtls_md_hmac_update(&ctx, b, bLen);
  if (rc == 0) rc = mbedtls_md_hmac_finish(&ctx, out);
  mbedtls_md_free(&ctx);
  return rc == 0;
}

}  // namespace

bool hkdfSha256(const uint8_t* salt, size_t saltLen, const uint8_t* ikm, size_t ikmLen,
                const uint8_t* info, size_t infoLen, uint8_t* okm, size_t okmLen) {
  if (okmLen > 255 * 32) return false;
  uint8_t prk[32], t[32];
  if (!hmacSha256(salt, saltLen, ikm, ikmLen, nullptr, 0, prk)) return false;  // extract
  size_t done = 0, tLen = 0;
  for (uint8_t i = 1; done < okmLen; ++i) {                                     // expand
    uint8_t buf[32 + 64 + 1];
    if (infoLen > 64) return false;
    memcpy(buf, t, tLen);
    memcpy(buf + tLen, info, infoLen);
    buf[tLen + infoLen] = i;
    if (!hmacSha256(prk, sizeof prk, buf, tLen + infoLen + 1, nullptr, 0, t)) return false;
    tLen = 32;
    const size_t n = (okmLen - done) < 32 ? (okmLen - done) : 32;
    memcpy(okm + done, t, n);
    done += n;
  }
  mbedtls_platform_zeroize(prk, sizeof prk);
  mbedtls_platform_zeroize(t, sizeof t);
  return true;
}

bool commissioningSelfTest() {
  // RFC 5869 A.1
  uint8_t ikm[22];
  memset(ikm, 0x0b, sizeof ikm);
  const uint8_t salt[13] = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
                            0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c};
  const uint8_t info[10] = {0xf0, 0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8, 0xf9};
  const uint8_t expect[42] = {0x3c, 0xb2, 0x5f, 0x25, 0xfa, 0xac, 0xd5, 0x7a, 0x90, 0x43, 0x4f,
                              0x64, 0xd0, 0x36, 0x2f, 0x2a, 0x2d, 0x2d, 0x0a, 0x90, 0xcf, 0x1a,
                              0x5a, 0x4c, 0x5d, 0xb0, 0x2d, 0x56, 0xec, 0xc4, 0xc5, 0xbf, 0x34,
                              0x00, 0x72, 0x08, 0xd5, 0xb8, 0x87, 0x18, 0x58, 0x65};
  uint8_t okm[42];
  return hkdfSha256(salt, sizeof salt, ikm, sizeof ikm, info, sizeof info, okm, sizeof okm) &&
         memcmp(okm, expect, sizeof okm) == 0;
}

CommissionStatus openCommissioningBundle(const uint8_t* b, size_t len, const uint8_t deviceId[8],
                                         EcdhFn ecdh, SiteConfig& out) {
  BundleHeader h;
  if (len > kMaxBundleSize || !parseBundleHeader(b, len, h) || h.version != kBundleVersion1 ||
      kBundleHeaderSize + h.payloadLen + kBundleSignatureSize != len) {
    return CommissionStatus::Malformed;
  }
  static const uint8_t kZero[8] = {0};
  if (memcmp(h.targetDevice, kZero, 8) == 0 || memcmp(h.targetDevice, deviceId, 8) != 0) {
    return CommissionStatus::NotForThisLock;
  }

  // Find record 0x30.
  const uint8_t* p = b + kBundleHeaderSize;
  const uint8_t* end = p + h.payloadLen;
  const uint8_t* rec = nullptr;
  uint16_t recLen = 0;
  while (p < end) {
    if (end - p < 3) return CommissionStatus::Malformed;
    const uint8_t type = p[0];
    const uint16_t n = le16(p + 1);
    p += 3;
    if (end - p < n) return CommissionStatus::Malformed;
    if (type == kTlvCommissioning) { rec = p; recLen = n; }
    p += n;
  }
  if (!rec) return CommissionStatus::NoCommissioningRecord;
  if (recLen < kEphKey + kNonce + kPlainFixed + kTag) return CommissionStatus::Malformed;
  const size_t ctLen = recLen - kEphKey - kNonce - kTag;
  if (ctLen > kPlainFixed + 2 * kMaxZones) return CommissionStatus::Malformed;

  // ECIES: ECDH -> HKDF -> AES-128-GCM (AAD = bundle header).
  uint8_t shared[32], key[16];
  if (!ecdh(rec, shared)) return CommissionStatus::DecryptFailed;
  const bool kdfOk = hkdfSha256(deviceId, 8, shared, sizeof shared,
                                reinterpret_cast<const uint8_t*>(kHkdfInfo), sizeof kHkdfInfo - 1,
                                key, sizeof key);
  mbedtls_platform_zeroize(shared, sizeof shared);
  if (!kdfOk) return CommissionStatus::DecryptFailed;

  std::vector<uint8_t> plain(ctLen);
  mbedtls_gcm_context gcm;
  mbedtls_gcm_init(&gcm);
  int rc = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key, 128);
  if (rc == 0) {
    rc = mbedtls_gcm_auth_decrypt(&gcm, ctLen, rec + kEphKey, kNonce, b, kBundleHeaderSize,
                                  rec + kEphKey + kNonce + ctLen, kTag, rec + kEphKey + kNonce,
                                  plain.data());
  }
  mbedtls_gcm_free(&gcm);
  mbedtls_platform_zeroize(key, sizeof key);
  if (rc != 0) return CommissionStatus::DecryptFailed;

  // Parse the plaintext.
  const uint8_t* q = plain.data();
  SiteConfig c;
  memcpy(c.siteAid, q, 3);
  memcpy(c.adminAid, q + 3, 3);
  memcpy(c.readMasterKey, q + 6, 16);
  memcpy(c.uidKey, q + 22, 16);
  memcpy(c.adminReadMasterKey, q + 38, 16);
  memcpy(c.managementPublicKey, q + 54, 65);
  c.doorId = le16(q + 119);
  const uint8_t zoneCount = q[121];
  bool ok = zoneCount <= kMaxZones && ctLen == kPlainFixed + 2u * zoneCount && c.doorId != 0;
  for (uint8_t i = 0; ok && i < zoneCount; ++i) c.zones.push_back(le16(q + 122 + 2 * i));
  mbedtls_platform_zeroize(plain.data(), plain.size());
  if (!ok) return CommissionStatus::Malformed;

  if (!verifyBundleSignature(b, len, c.managementPublicKey)) return CommissionStatus::BadSignature;
  if (memcmp(h.siteAid, c.siteAid, 3) != 0) return CommissionStatus::WrongSite;
  out = c;
  mbedtls_platform_zeroize(&c, sizeof c.siteAid + sizeof c.adminAid + 48);
  return CommissionStatus::Ok;
}

const char* toString(CommissionStatus s) {
  switch (s) {
    case CommissionStatus::Ok:                    return "ok";
    case CommissionStatus::Malformed:             return "malformed commissioning bundle";
    case CommissionStatus::NotForThisLock:        return "commissioning bundle is for another lock";
    case CommissionStatus::NoCommissioningRecord: return "no commissioning record";
    case CommissionStatus::DecryptFailed:         return "cannot decrypt (not encrypted for this lock, or tampered)";
    case CommissionStatus::BadSignature:          return "bad signature";
    case CommissionStatus::WrongSite:             return "site mismatch";
  }
  return "?";
}

}  // namespace opencylinder
