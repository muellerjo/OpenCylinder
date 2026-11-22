#pragma once
// Persists the lock's managed configuration (blacklist, time profiles,
// time-zone rule, last bundle sequence) in NVS flash.

#include <Preferences.h>

#include "management.h"

namespace opencylinder {

class ManagedStore {
 public:
  // Load; returns false if nothing has been stored yet (caller sets defaults).
  bool load(ManagedState& s) {
    prefs_.begin("oc-mgmt", false);
    if (!prefs_.isKey("seq")) return false;
    s.lastSequence = prefs_.getUInt("seq", 0);
    s.tzRule = prefs_.getString("tz", "").c_str();

    s.blacklist.clear();
    const size_t blLen = prefs_.getBytesLength("bl");
    if (blLen % 8 == 0 && blLen / 8 <= kMaxBlacklist) {
      std::vector<uint8_t> raw(blLen);
      if (blLen) prefs_.getBytes("bl", raw.data(), blLen);
      for (size_t i = 0; i < blLen; i += 8) {
        s.blacklist.push_back(BlacklistEntry{le32(&raw[i]), le32(&raw[i + 4])});
      }
    }
    s.profiles.clear();
    const size_t prLen = prefs_.getBytesLength("prof");
    if (prLen % 10 == 0 && prLen / 10 <= kMaxProfiles) {
      std::vector<uint8_t> raw(prLen);
      if (prLen) prefs_.getBytes("prof", raw.data(), prLen);
      for (size_t i = 0; i < prLen; i += 10) {
        TimeProfile p{};
        p.id = raw[i];
        p.days = raw[i + 1];
        p.iv[0] = TimeInterval{le16(&raw[i + 2]), le16(&raw[i + 4])};
        p.iv[1] = TimeInterval{le16(&raw[i + 6]), le16(&raw[i + 8])};
        s.profiles.push_back(p);
      }
    }
    return true;
  }

  void save(const ManagedState& s) {
    std::vector<uint8_t> bl;
    for (const BlacklistEntry& e : s.blacklist) { put32(bl, e.credentialId); put32(bl, e.until); }
    std::vector<uint8_t> pr;
    for (const TimeProfile& p : s.profiles) {
      pr.push_back(p.id);
      pr.push_back(p.days);
      for (const TimeInterval& iv : p.iv) { put16(pr, iv.from); put16(pr, iv.to); }
    }
    prefs_.putBytes("bl", bl.data(), bl.size());
    prefs_.putBytes("prof", pr.data(), pr.size());
    prefs_.putString("tz", s.tzRule.c_str());
    prefs_.putUInt("seq", s.lastSequence);  // written last: marks a complete state
  }

  void clear() { prefs_.clear(); }

 private:
  static uint16_t le16(const uint8_t* p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }
  static uint32_t le32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
  }
  static void put16(std::vector<uint8_t>& v, uint16_t x) {
    v.push_back(static_cast<uint8_t>(x));
    v.push_back(static_cast<uint8_t>(x >> 8));
  }
  static void put32(std::vector<uint8_t>& v, uint32_t x) {
    for (int i = 0; i < 4; ++i) v.push_back(static_cast<uint8_t>(x >> (8 * i)));
  }

  Preferences prefs_;
};

}  // namespace opencylinder
