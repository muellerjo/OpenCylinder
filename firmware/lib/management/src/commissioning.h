#pragma once
// Commissioning bundles — spec/admin-card.md §5.3. A FACTORY lock decrypts
// the commissioning record (ECIES: ECDH P-256 + HKDF-SHA256 + AES-128-GCM)
// with its own device private key, then verifies the bundle signature with
// the site management key it just received. mbedTLS.

#include <cstddef>
#include <cstdint>
#include <vector>

namespace opencylinder {

constexpr uint8_t kTlvCommissioning = 0x30;
constexpr size_t kMaxZones = 16;

// The site configuration a lock receives at commissioning.
struct SiteConfig {
  uint8_t siteAid[3];          // wire order
  uint8_t adminAid[3];         // wire order
  uint8_t readMasterKey[16];   // site read key master (diversified per card)
  uint8_t uidKey[16];          // site-wide UID key
  uint8_t adminReadMasterKey[16];
  uint8_t managementPublicKey[65];  // ECDSA P-256, uncompressed
  uint16_t doorId;
  std::vector<uint16_t> zones;
};

enum class CommissionStatus : uint8_t {
  Ok,
  Malformed,
  NotForThisLock,        // target_device zero or another lock
  NoCommissioningRecord,
  DecryptFailed,         // not encrypted for this lock, or tampered
  BadSignature,
  WrongSite,             // header site AID != site AID inside the record
};
const char* toString(CommissionStatus s);

// The lock's ECDH with its device private key: peer = uncompressed point,
// shared = 32-byte x-coordinate.
using EcdhFn = bool (*)(const uint8_t peer[65], uint8_t shared[32]);

CommissionStatus openCommissioningBundle(const uint8_t* bundle, size_t len,
                                         const uint8_t deviceId[8], EcdhFn ecdh,
                                         SiteConfig& out);

// HKDF-SHA256 (RFC 5869); exposed for the self-test.
bool hkdfSha256(const uint8_t* salt, size_t saltLen, const uint8_t* ikm, size_t ikmLen,
                const uint8_t* info, size_t infoLen, uint8_t* okm, size_t okmLen);

// RFC 5869 test case 1. Run at boot.
bool commissioningSelfTest();

}  // namespace opencylinder
