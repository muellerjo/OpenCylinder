#pragma once
// Signed management bundles — spec/admin-card.md §2. Carrier-independent:
// the same verification path serves admin cards, update points, network and
// radio. Parsing/applying is portable (host-testable); the ECDSA check is in
// bundle_signature.cpp (mbedTLS).

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "access_decision.h"

namespace opencylinder {

constexpr uint8_t kBundleVersion1 = 1;
constexpr size_t kBundleHeaderSize = 27;
constexpr size_t kBundleSignatureSize = 64;
constexpr size_t kMaxBundleSize = 1024;
constexpr size_t kMaxBlacklist = 256;
constexpr size_t kMaxProfiles = 32;
constexpr size_t kMaxTzRuleLen = 47;

constexpr uint8_t kTlvBlacklistAdd = 0x10;
constexpr uint8_t kTlvBlacklistRemove = 0x11;
constexpr uint8_t kTlvBlacklistReplace = 0x12;
constexpr uint8_t kTlvTimeProfiles = 0x20;
constexpr uint8_t kTlvTzRule = 0x21;

struct BundleHeader {
  uint8_t version;
  uint8_t siteAid[3];       // wire order
  uint8_t targetDevice[8];  // all zero = every lock of the site
  uint32_t sequence;
  uint32_t issuedAt;
  uint32_t validUntil;
  uint16_t payloadLen;
};

bool parseBundleHeader(const uint8_t* data, size_t len, BundleHeader& out);

// ECDSA P-256 / SHA-256 over bundle[0 .. len-64), signature = last 64 bytes
// (r || s). `publicKey` = uncompressed point (65 bytes, 0x04 || X || Y).
bool verifyBundleSignature(const uint8_t* bundle, size_t len, const uint8_t publicKey[65]);

struct BlacklistEntry {
  uint32_t credentialId;
  uint32_t until;   // unsigned Unix UTC; entry ignored after this time
};

// The lock's managed configuration (persisted by the platform layer).
struct ManagedState {
  uint32_t lastSequence = 0;
  std::vector<BlacklistEntry> blacklist;
  std::vector<TimeProfile> profiles;
  std::string tzRule;
};

enum class BundleStatus : uint8_t {
  Applied,
  Malformed,
  WrongSite,
  WrongDevice,
  BadSignature,
  Expired,
  StaleSequence,   // signature fine, but not newer than the last applied one
};
const char* toString(BundleStatus s);

struct ApplySummary {
  uint32_t sequence = 0;
  uint32_t issuedAt = 0;        // caller adopts this as time (rollback rule)
  int blacklistAdded = 0, blacklistRemoved = 0;
  bool blacklistReplaced = false, profilesReplaced = false, tzReplaced = false;
};

// Full check + apply. `verify` is injectable for host tests (pass
// verifyBundleSignature in firmware). Time: if `timeKnown`, a bundle whose
// valid_until has passed is rejected. On anything but Applied the state is
// left untouched.
using SignatureVerifier = bool (*)(const uint8_t*, size_t, const uint8_t[65]);
BundleStatus applyBundle(const uint8_t* bundle, size_t len, const uint8_t siteAid[3],
                         const uint8_t deviceId[8], const uint8_t publicKey[65],
                         SignatureVerifier verify, bool timeKnown, uint32_t now,
                         ManagedState& state, ApplySummary& summary);

// Credential IDs that are blacklisted at `now` (expired entries dropped; if
// the time is unknown every entry stays active — fail safe).
std::vector<uint32_t> activeBlacklist(const ManagedState& s, bool timeKnown, uint32_t now);

}  // namespace opencylinder
