#include "desfire_crypto.h"

#include <cstring>
#include <mbedtls/aes.h>
#include <mbedtls/platform_util.h>

namespace opencylinder {
namespace crypto {
namespace {

bool aesEcbEncrypt(const uint8_t key[16], const uint8_t in[16], uint8_t out[16]) {
  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  int rc = mbedtls_aes_setkey_enc(&ctx, key, 128);
  if (rc == 0) rc = mbedtls_aes_crypt_ecb(&ctx, MBEDTLS_AES_ENCRYPT, in, out);
  mbedtls_aes_free(&ctx);
  return rc == 0;
}

// Left shift of a 128-bit block by one bit; XOR Rb (0x87) if the MSB was set.
void cmacDouble(const uint8_t in[16], uint8_t out[16]) {
  const uint8_t msb = in[0] & 0x80;
  for (int i = 0; i < 15; ++i) out[i] = static_cast<uint8_t>((in[i] << 1) | (in[i + 1] >> 7));
  out[15] = static_cast<uint8_t>(in[15] << 1);
  if (msb) out[15] ^= 0x87;
}

bool equal16(const uint8_t* a, const uint8_t* b) { return memcmp(a, b, 16) == 0; }

}  // namespace

void wipe(void* p, size_t n) { mbedtls_platform_zeroize(p, n); }

bool aesCbc(const uint8_t key[16], bool encrypt, uint8_t iv[16],
            const uint8_t* in, uint8_t* out, size_t len) {
  if (len % 16 != 0) return false;
  mbedtls_aes_context ctx;
  mbedtls_aes_init(&ctx);
  int rc = encrypt ? mbedtls_aes_setkey_enc(&ctx, key, 128)
                   : mbedtls_aes_setkey_dec(&ctx, key, 128);
  if (rc == 0) {
    rc = mbedtls_aes_crypt_cbc(&ctx, encrypt ? MBEDTLS_AES_ENCRYPT : MBEDTLS_AES_DECRYPT,
                               len, iv, in, out);
  }
  mbedtls_aes_free(&ctx);
  return rc == 0;
}

bool cmacAes128(const uint8_t key[16], const uint8_t iv[16], const uint8_t* msg,
                size_t len, uint8_t mac[16]) {
  // Subkeys K1, K2 from L = AES_K(0^128).
  uint8_t zero[16] = {0}, l[16], k1[16], k2[16];
  if (!aesEcbEncrypt(key, zero, l)) return false;
  cmacDouble(l, k1);
  cmacDouble(k1, k2);

  const size_t blocks = (len == 0) ? 1 : (len + 15) / 16;
  const bool lastComplete = (len != 0) && (len % 16 == 0);

  uint8_t x[16];
  memcpy(x, iv, 16);
  uint8_t block[16];
  bool ok = true;
  for (size_t b = 0; b < blocks && ok; ++b) {
    const size_t off = b * 16;
    if (b + 1 < blocks) {
      memcpy(block, msg + off, 16);
    } else {
      // Last block: XOR K1 if complete, else pad 0x80 00.. and XOR K2.
      memset(block, 0, 16);
      const size_t rem = len - off;
      memcpy(block, msg + off, rem);
      if (!lastComplete) block[rem] = 0x80;
      const uint8_t* k = lastComplete ? k1 : k2;
      for (int i = 0; i < 16; ++i) block[i] ^= k[i];
    }
    for (int i = 0; i < 16; ++i) block[i] ^= x[i];
    ok = aesEcbEncrypt(key, block, x);
  }
  if (ok) memcpy(mac, x, 16);
  wipe(l, sizeof l);
  wipe(k1, sizeof k1);
  wipe(k2, sizeof k2);
  wipe(block, sizeof block);
  wipe(x, sizeof x);
  return ok;
}

bool diversifyAn10922(const uint8_t masterKey[16], const uint8_t* m, size_t mLen,
                      uint8_t out[16]) {
  if (mLen == 0 || mLen > 31) return false;
  uint8_t zero[16] = {0}, l[16], k1[16], k2[16];
  if (!aesEcbEncrypt(masterKey, zero, l)) return false;
  cmacDouble(l, k1);
  cmacDouble(k1, k2);

  uint8_t d[32] = {0};
  d[0] = 0x01;
  memcpy(d + 1, m, mLen);
  const bool padded = (mLen + 1) < 32;
  if (padded) d[mLen + 1] = 0x80;
  const uint8_t* k = padded ? k2 : k1;
  for (int i = 0; i < 16; ++i) d[16 + i] ^= k[i];

  uint8_t x[16];
  bool ok = aesEcbEncrypt(masterKey, d, x);           // block 1
  for (int i = 0; ok && i < 16; ++i) x[i] ^= d[16 + i];
  ok = ok && aesEcbEncrypt(masterKey, x, out);        // block 2 -> key
  wipe(l, sizeof l);
  wipe(k1, sizeof k1);
  wipe(k2, sizeof k2);
  wipe(d, sizeof d);
  wipe(x, sizeof x);
  return ok;
}

uint32_t crc32Desfire(const uint8_t* data, size_t len, uint32_t crc) {
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
  }
  return crc;
}

bool selfTest() {
  // RFC 4493 §4 (= NIST SP 800-38B D.1), AES-128.
  static const uint8_t key[16] = {0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
                                  0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c};
  static const uint8_t msg[64] = {
      0x6b, 0xc1, 0xbe, 0xe2, 0x2e, 0x40, 0x9f, 0x96, 0xe9, 0x3d, 0x7e, 0x11, 0x73, 0x93, 0x17, 0x2a,
      0xae, 0x2d, 0x8a, 0x57, 0x1e, 0x03, 0xac, 0x9c, 0x9e, 0xb7, 0x6f, 0xac, 0x45, 0xaf, 0x8e, 0x51,
      0x30, 0xc8, 0x1c, 0x46, 0xa3, 0x5c, 0xe4, 0x11, 0xe5, 0xfb, 0xc1, 0x19, 0x1a, 0x0a, 0x52, 0xef,
      0xf6, 0x9f, 0x24, 0x45, 0xdf, 0x4f, 0x9b, 0x17, 0xad, 0x2b, 0x41, 0x7b, 0xe6, 0x6c, 0x37, 0x10};
  static const struct {
    size_t len;
    uint8_t mac[16];
  } vectors[] = {
      {0, {0xbb, 0x1d, 0x69, 0x29, 0xe9, 0x59, 0x37, 0x28, 0x7f, 0xa3, 0x7d, 0x12, 0x9b, 0x75, 0x67, 0x46}},
      {16, {0x07, 0x0a, 0x16, 0xb4, 0x6b, 0x4d, 0x41, 0x44, 0xf7, 0x9b, 0xdd, 0x9d, 0xd0, 0x4a, 0x28, 0x7c}},
      {40, {0xdf, 0xa6, 0x67, 0x47, 0xde, 0x9a, 0xe6, 0x30, 0x30, 0xca, 0x32, 0x61, 0x14, 0x97, 0xc8, 0x27}},
      {64, {0x51, 0xf0, 0xbe, 0xbf, 0x7e, 0x3b, 0x9d, 0x92, 0xfc, 0x49, 0x74, 0x17, 0x79, 0x36, 0x3c, 0xfe}},
  };
  const uint8_t zeroIv[16] = {0};
  for (const auto& v : vectors) {
    uint8_t mac[16];
    if (!cmacAes128(key, zeroIv, msg, v.len, mac) || !equal16(mac, v.mac)) return false;
  }
  // NXP AN10922 §2.2.1 AES-128 example: master key 00112233..EEFF,
  // M = UID 04782E21801D80 || AID 3042F5 || system id 4E585020416275.
  {
    static const uint8_t mk[16] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                                   0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};
    static const uint8_t m[17] = {0x04, 0x78, 0x2E, 0x21, 0x80, 0x1D, 0x80, 0x30, 0x42,
                                  0xF5, 0x4E, 0x58, 0x50, 0x20, 0x41, 0x62, 0x75};
    static const uint8_t expect[16] = {0xA8, 0xDD, 0x63, 0xA3, 0xB8, 0x9D, 0x54, 0xB3,
                                       0x7C, 0xA8, 0x02, 0x47, 0x3F, 0xDA, 0x91, 0x75};
    uint8_t div[16];
    if (!diversifyAn10922(mk, m, sizeof m, div) || !equal16(div, expect)) return false;
  }
  // CRC-32/JAMCRC check value: "123456789" -> 0x340BC6D9.
  static const uint8_t check[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  return crc32Desfire(check, sizeof check) == 0x340BC6D9u;
}

}  // namespace crypto
}  // namespace opencylinder
