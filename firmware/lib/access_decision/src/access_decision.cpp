#include "access_decision.h"

namespace opencylinder {
namespace {

uint16_t le16(const uint8_t* p) {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}
uint32_t le32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

bool contains(const uint16_t* list, size_t n, uint16_t v) {
  for (size_t i = 0; i < n; ++i) if (list[i] == v) return true;
  return false;
}
bool contains(const uint32_t* list, size_t n, uint32_t v) {
  for (size_t i = 0; i < n; ++i) if (list[i] == v) return true;
  return false;
}

// Time profiles are not implemented yet (definitions come with admin cards):
// only profile 0 ("always") can allow access. Fails closed otherwise.
bool profileAllows(uint8_t profile, bool /*timeKnown*/, uint32_t /*now*/) {
  return profile == 0;
}

}  // namespace

bool parseHeader(const uint8_t* d, size_t len, CardHeader& h) {
  if (len < kHeaderSize) return false;
  h.formatVersion = d[0];
  h.entryCount    = d[1];
  // d[2..3] reserved
  h.credentialId  = le32(d + 4);
  h.validUntil    = le32(d + 8);
  h.issuedAt      = le32(d + 12);
  return true;
}

bool parseEntries(const uint8_t* d, size_t len, uint8_t count,
                  std::vector<AccessEntry>& out) {
  out.clear();
  if (len < static_cast<size_t>(count) * kEntrySize) return false;
  out.reserve(count);
  for (uint8_t i = 0; i < count; ++i) {
    const uint8_t* e = d + i * kEntrySize;
    out.push_back(AccessEntry{e[0], le16(e + 1), e[3]});
  }
  return true;
}

Decision checkHeader(const CardHeader& h, const LockConfig& lock,
                     bool timeKnown, uint32_t now) {
  if (h.formatVersion != kFormatVersion1) return Decision::DenyUnknownFormat;
  if (h.entryCount > kMaxEntries) return Decision::DenyMalformed;
  if (h.validUntil != 0 && !timeKnown) return Decision::DenyTimeUnknown;
  if (h.validUntil != 0 && now > h.validUntil) return Decision::DenyExpired;
  if (contains(lock.blacklist, lock.blacklistCount, h.credentialId)) {
    return Decision::DenyBlacklisted;
  }
  return Decision::Open;
}

Result decide(const CardHeader& h, const std::vector<AccessEntry>& entries,
              const LockConfig& lock, bool timeKnown, uint32_t now) {
  Result r;
  r.decision = checkHeader(h, lock, timeKnown, now);
  if (r.decision != Decision::Open) return r;
  if (entries.size() < h.entryCount) {
    r.decision = Decision::DenyMalformed;
    return r;
  }

  bool profileBlocked = false;
  for (uint8_t i = 0; i < h.entryCount; ++i) {
    const AccessEntry& e = entries[i];
    const bool target =
        (e.type == kEntryDoor && e.targetId == lock.doorId) ||
        (e.type == kEntryZone && contains(lock.zones, lock.zoneCount, e.targetId));
    if (!target) continue;
    if (profileAllows(e.timeProfile, timeKnown, now)) {
      r.decision = Decision::Open;
      r.matched = e;
      return r;
    }
    profileBlocked = true;
    r.matched = e;
  }
  r.decision = profileBlocked ? Decision::DenyNotAtThisTime : Decision::DenyNoRight;
  return r;
}

const char* toString(Decision d) {
  switch (d) {
    case Decision::Open:              return "open";
    case Decision::DenyUnknownFormat: return "unknown card format version";
    case Decision::DenyMalformed:     return "malformed card record";
    case Decision::DenyTimeUnknown:   return "time unknown and card has an expiry";
    case Decision::DenyExpired:       return "card expired";
    case Decision::DenyBlacklisted:   return "credential blacklisted";
    case Decision::DenyNotAtThisTime: return "right exists, but not at this time";
    case Decision::DenyNoRight:       return "no matching door/zone entry";
  }
  return "?";
}

}  // namespace opencylinder
