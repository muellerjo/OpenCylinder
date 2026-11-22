#pragma once
// Event log storage in NVS (dev board). One 16-byte blob per slot plus the
// total count. NVS is wear-levelled; capacity is kept small (64) because the
// default NVS partition is only 20 KB. The production lock uses a dedicated
// flash area with more room.

#include <Preferences.h>

#include <cstdio>

#include "eventlog.h"

namespace opencylinder {

class NvsEventStore : public IEventStore {
 public:
  void begin() { prefs_.begin("oc-log", false); }

  bool readSlot(size_t slot, uint8_t out[kEventSize]) override {
    char key[8];
    snprintf(key, sizeof key, "e%u", static_cast<unsigned>(slot));
    return prefs_.getBytes(key, out, kEventSize) == kEventSize;
  }
  void writeSlot(size_t slot, const uint8_t in[kEventSize]) override {
    char key[8];
    snprintf(key, sizeof key, "e%u", static_cast<unsigned>(slot));
    prefs_.putBytes(key, in, kEventSize);
  }
  uint32_t readCount() override { return prefs_.getUInt("cnt", 0); }
  void writeCount(uint32_t n) override { prefs_.putUInt("cnt", n); }
  void clear() override { prefs_.clear(); }

 private:
  Preferences prefs_;
};

}  // namespace opencylinder
