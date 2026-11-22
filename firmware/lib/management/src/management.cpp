#include "management.h"

#include <algorithm>
#include <cstring>

namespace opencylinder {
namespace {

uint16_t le16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }
uint32_t le32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

bool allZero(const uint8_t* p, size_t n) {
  for (size_t i = 0; i < n; ++i) if (p[i]) return false;
  return true;
}

void removeId(std::vector<BlacklistEntry>& bl, uint32_t id) {
  bl.erase(std::remove_if(bl.begin(), bl.end(),
                          [id](const BlacklistEntry& e) { return e.credentialId == id; }),
           bl.end());
}

}  // namespace

bool parseBundleHeader(const uint8_t* d, size_t len, BundleHeader& h) {
  if (len < kBundleHeaderSize) return false;
  h.version = d[0];
  memcpy(h.siteAid, d + 2, 3);
  memcpy(h.targetDevice, d + 5, 8);
  h.sequence = le32(d + 13);
  h.issuedAt = le32(d + 17);
  h.validUntil = le32(d + 21);
  h.payloadLen = le16(d + 25);
  return true;
}

BundleStatus applyBundle(const uint8_t* b, size_t len, const uint8_t siteAid[3],
                         const uint8_t deviceId[8], const uint8_t publicKey[65],
                         SignatureVerifier verify, bool timeKnown, uint32_t now,
                         ManagedState& state, ApplySummary& sum) {
  sum = ApplySummary{};
  BundleHeader h;
  if (len > kMaxBundleSize || !parseBundleHeader(b, len, h)) return BundleStatus::Malformed;
  if (h.version != kBundleVersion1) return BundleStatus::Malformed;
  if (kBundleHeaderSize + h.payloadLen + kBundleSignatureSize != len) return BundleStatus::Malformed;
  if (memcmp(h.siteAid, siteAid, 3) != 0) return BundleStatus::WrongSite;
  if (!allZero(h.targetDevice, 8) && memcmp(h.targetDevice, deviceId, 8) != 0) {
    return BundleStatus::WrongDevice;
  }
  // Signature before looking at any record content.
  if (!verify || !verify(b, len, publicKey)) return BundleStatus::BadSignature;
  if (timeKnown && now > h.validUntil) return BundleStatus::Expired;

  sum.sequence = h.sequence;
  sum.issuedAt = h.issuedAt;  // time sync is valid even for a stale sequence
  if (h.sequence <= state.lastSequence) return BundleStatus::StaleSequence;

  // Parse into a copy; commit only if every record is well-formed.
  ManagedState next = state;
  const uint8_t* p = b + kBundleHeaderSize;
  const uint8_t* end = p + h.payloadLen;
  while (p < end) {
    if (end - p < 3) return BundleStatus::Malformed;
    const uint8_t type = p[0];
    const uint16_t n = le16(p + 1);
    p += 3;
    if (end - p < n) return BundleStatus::Malformed;
    const uint8_t* v = p;
    p += n;
    switch (type) {
      case kTlvBlacklistReplace:
      case kTlvBlacklistAdd: {
        if (n % 8) return BundleStatus::Malformed;
        if (type == kTlvBlacklistReplace) {
          next.blacklist.clear();
          sum.blacklistReplaced = true;
        }
        for (uint16_t i = 0; i < n; i += 8) {
          const uint32_t id = le32(v + i);
          removeId(next.blacklist, id);
          if (next.blacklist.size() >= kMaxBlacklist) return BundleStatus::Malformed;
          next.blacklist.push_back(BlacklistEntry{id, le32(v + i + 4)});
          if (type == kTlvBlacklistAdd) ++sum.blacklistAdded;
        }
        break;
      }
      case kTlvBlacklistRemove:
        if (n % 4) return BundleStatus::Malformed;
        for (uint16_t i = 0; i < n; i += 4) {
          removeId(next.blacklist, le32(v + i));
          ++sum.blacklistRemoved;
        }
        break;
      case kTlvTimeProfiles: {
        if (n % 10 || n / 10 > kMaxProfiles) return BundleStatus::Malformed;
        next.profiles.clear();
        for (uint16_t i = 0; i < n; i += 10) {
          TimeProfile tp{};
          tp.id = v[i];
          tp.days = v[i + 1];
          tp.iv[0] = TimeInterval{le16(v + i + 2), le16(v + i + 4)};
          tp.iv[1] = TimeInterval{le16(v + i + 6), le16(v + i + 8)};
          if (tp.id == 0 || tp.iv[0].to > 1440 || tp.iv[1].to > 1440) return BundleStatus::Malformed;
          next.profiles.push_back(tp);
        }
        sum.profilesReplaced = true;
        break;
      }
      case kTlvTzRule: {
        if (n == 0 || n > kMaxTzRuleLen) return BundleStatus::Malformed;
        std::string rule(reinterpret_cast<const char*>(v), n);
        TzRule check;
        if (!parsePosixTz(rule.c_str(), check)) return BundleStatus::Malformed;
        next.tzRule = rule;
        sum.tzReplaced = true;
        break;
      }
      default:
        break;  // unknown records are skipped (forward compatible)
    }
  }
  next.lastSequence = h.sequence;
  state = next;
  return BundleStatus::Applied;
}

std::vector<uint32_t> activeBlacklist(const ManagedState& s, bool timeKnown, uint32_t now) {
  std::vector<uint32_t> out;
  for (const BlacklistEntry& e : s.blacklist) {
    if (!timeKnown || now <= e.until) out.push_back(e.credentialId);
  }
  return out;
}

const char* toString(BundleStatus s) {
  switch (s) {
    case BundleStatus::Applied:       return "applied";
    case BundleStatus::Malformed:     return "malformed bundle";
    case BundleStatus::WrongSite:     return "bundle for another site";
    case BundleStatus::WrongDevice:   return "bundle for another lock";
    case BundleStatus::BadSignature:  return "bad signature";
    case BundleStatus::Expired:       return "bundle expired";
    case BundleStatus::StaleSequence: return "stale sequence (not newer than last applied)";
  }
  return "?";
}

}  // namespace opencylinder
