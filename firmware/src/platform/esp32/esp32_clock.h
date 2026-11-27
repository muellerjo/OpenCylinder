#pragma once
// Dev-board clock: counts from the ESP32's 64-bit microsecond timer after the
// time has been set (serial `time` command for now, admin card later).
// The time itself is RAM only — a reset means "time unknown" (fail-safe rule).
// The rollback high-water mark is persisted in NVS flash, so it survives
// resets. The production lock uses an RTC with backup (docs §2.5).

#include <Preferences.h>
#include <esp_timer.h>

#include "clock.h"

namespace opencylinder {

class Esp32Clock : public IClock {
 public:
  void begin() {
    prefs_.begin("oc-clock", false);
    highWater_ = prefs_.getUInt("hw", 0);
  }

  bool now(uint32_t& unixUtc) const override {
    if (!set_) return false;
    const uint64_t elapsed = static_cast<uint64_t>(esp_timer_get_time() - refUs_) / 1000000u;
    const uint64_t t = static_cast<uint64_t>(base_) + elapsed;
    if (t > 0xFFFFFFFFu) return false;  // beyond 2106: treat as unknown
    unixUtc = static_cast<uint32_t>(t);
    return true;
  }

  // Unconditional set (IClock); callers go through trySet() for the rule.
  void set(uint32_t unixUtc) override {
    base_ = unixUtc;
    refUs_ = esp_timer_get_time();
    set_ = true;
    raiseHighWater(unixUtc);
  }

  // Set the time only if the rollback rule allows it. The reference is the
  // later of the stored high-water mark and the running clock: the mark is
  // only written every 10 minutes, so comparing against it alone would let an
  // old bundle turn the clock back by up to 10 + 5 minutes.
  // `forwardOnly`: stale bundles (sequence not newer) may only move the clock
  // forward — a backward correction needs a fresh bundle.
  bool trySet(uint32_t unixUtc, bool forwardOnly = false) {
    uint32_t reference = highWater_;
    uint32_t now = 0;
    if (this->now(now) && now > reference) reference = now;
    if (forwardOnly && set_ && unixUtc < now) return false;
    if (!timeUpdateAllowed(unixUtc, reference)) return false;
    set(unixUtc);
    return true;
  }

  // Call periodically: keeps the high-water mark close to the running time
  // (at most one flash write per 10 minutes).
  void tick() {
    uint32_t t;
    if (now(t) && t >= highWater_ + 600) raiseHighWater(t);
  }

  uint32_t highWater() const { return highWater_; }

  // Bench only: forget the high-water mark AND the current time (otherwise
  // tick() would immediately raise the mark again from the running clock).
  void resetHighWater() {
    set_ = false;
    highWater_ = 0;
    prefs_.putUInt("hw", 0);
  }

 private:
  void raiseHighWater(uint32_t t) {
    if (t <= highWater_) return;
    highWater_ = t;
    prefs_.putUInt("hw", t);
  }

  Preferences prefs_;
  bool set_ = false;
  uint32_t base_ = 0;
  int64_t refUs_ = 0;
  uint32_t highWater_ = 0;
};

}  // namespace opencylinder
