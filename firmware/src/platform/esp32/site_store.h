#pragma once
// Persists the site configuration received at commissioning (NVS on the dev
// board; production: secure element / key storage for the keys).

#include <Preferences.h>

#include "commissioning.h"

namespace opencylinder {

class SiteStore {
 public:
  void begin() { prefs_.begin("oc-site", false); }

  bool load(SiteConfig& c) {
    uint8_t raw[kFixed + 2 * kMaxZones];
    const size_t n = prefs_.isKey("cfg") ? prefs_.getBytesLength("cfg") : 0;
    if (n < kFixed || n > sizeof raw || (n - kFixed) % 2) return false;
    prefs_.getBytes("cfg", raw, n);
    memcpy(c.siteAid, raw, 3);
    memcpy(c.adminAid, raw + 3, 3);
    memcpy(c.readMasterKey, raw + 6, 16);
    memcpy(c.uidKey, raw + 22, 16);
    memcpy(c.adminReadMasterKey, raw + 38, 16);
    memcpy(c.managementPublicKey, raw + 54, 65);
    c.doorId = static_cast<uint16_t>(raw[119] | (raw[120] << 8));
    c.zones.clear();
    for (size_t i = kFixed; i < n; i += 2) c.zones.push_back(static_cast<uint16_t>(raw[i] | (raw[i + 1] << 8)));
    memset(raw, 0, sizeof raw);
    return true;
  }

  void save(const SiteConfig& c) {
    uint8_t raw[kFixed + 2 * kMaxZones];
    memcpy(raw, c.siteAid, 3);
    memcpy(raw + 3, c.adminAid, 3);
    memcpy(raw + 6, c.readMasterKey, 16);
    memcpy(raw + 22, c.uidKey, 16);
    memcpy(raw + 38, c.adminReadMasterKey, 16);
    memcpy(raw + 54, c.managementPublicKey, 65);
    raw[119] = static_cast<uint8_t>(c.doorId);
    raw[120] = static_cast<uint8_t>(c.doorId >> 8);
    size_t n = kFixed;
    for (size_t i = 0; i < c.zones.size() && i < kMaxZones; ++i) {
      raw[n++] = static_cast<uint8_t>(c.zones[i]);
      raw[n++] = static_cast<uint8_t>(c.zones[i] >> 8);
    }
    prefs_.putBytes("cfg", raw, n);
    memset(raw, 0, sizeof raw);
  }

  void clear() {
    if (prefs_.isKey("cfg")) prefs_.remove("cfg");
  }

 private:
  static constexpr size_t kFixed = 121;
  Preferences prefs_;
};

}  // namespace opencylinder
