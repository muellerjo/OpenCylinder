#pragma once
// Card record parsing and the lock's access decision — spec/card-format.md,
// format version 1. Portable, no hardware or crypto dependencies; mirrors
// examples/hospital/check_access.py so both behave identically.

#include <cstddef>
#include <cstdint>
#include <vector>

namespace opencylinder {

constexpr uint8_t  kFormatVersion1 = 1;
constexpr size_t   kHeaderSize     = 16;   // file 0
constexpr size_t   kEntrySize      = 4;    // file 1, per entry
constexpr uint8_t  kMaxEntries     = 64;   // 256-byte file 1
constexpr uint8_t  kEntryDoor      = 0x01;
constexpr uint8_t  kEntryZone      = 0x02;

struct CardHeader {
  uint8_t  formatVersion = 0;
  uint8_t  entryCount    = 0;
  uint32_t credentialId  = 0;
  uint32_t validUntil    = 0;   // unsigned Unix UTC seconds, 0 = no expiry
  uint32_t issuedAt      = 0;   // unsigned Unix UTC seconds
};

// Plain aggregates (no default member initializers) so they can be
// brace-initialized under C++11 as well; `{}` zero-initializes them.
struct AccessEntry {
  uint8_t  type;          // kEntryDoor / kEntryZone, others ignored
  uint16_t targetId;      // door or zone ID
  uint8_t  timeProfile;   // 0 = always
};

// What one lock knows after commissioning (never stored on the card).
struct LockConfig {
  uint16_t doorId;
  const uint16_t* zones;
  size_t zoneCount;
  const uint32_t* blacklist;   // credential IDs
  size_t blacklistCount;
};

enum class Decision : uint8_t {
  Open,
  DenyUnknownFormat,     // format_version not supported
  DenyMalformed,         // entry_count out of range, short data
  DenyTimeUnknown,       // card has an expiry but the lock has no time
  DenyExpired,
  DenyBlacklisted,
  DenyNotAtThisTime,     // matching entry, but its time profile does not allow now
  DenyNoRight,           // no entry for this door or its zones
};

struct Result {
  Decision decision = Decision::DenyNoRight;
  AccessEntry matched{};  // valid for Open (and the blocking entry for NotAtThisTime)
};

// File 0 (16 bytes, little-endian) -> header. False if `len` is too short.
bool parseHeader(const uint8_t* data, size_t len, CardHeader& out);

// File 1 -> the first `count` entries. False if `len` < count * 4.
bool parseEntries(const uint8_t* data, size_t len, uint8_t count,
                  std::vector<AccessEntry>& out);

// Checks that need only the header (done before reading the access list):
// format version, entry count, time-unknown rule, expiry, blacklist.
// Returns Decision::Open if the card may proceed to the access-list check.
Decision checkHeader(const CardHeader& h, const LockConfig& lock,
                     bool timeKnown, uint32_t now);

// Full decision on header + access list.
Result decide(const CardHeader& h, const std::vector<AccessEntry>& entries,
              const LockConfig& lock, bool timeKnown, uint32_t now);

const char* toString(Decision d);

}  // namespace opencylinder
