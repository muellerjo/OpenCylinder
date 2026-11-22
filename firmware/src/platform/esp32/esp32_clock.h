#pragma once
// Dev-board clock: counts from the ESP32's 64-bit microsecond timer after the
// time has been set (serial `time` command for now, admin card later).
// RAM only: a reset means "time unknown" — handy for testing the fail-safe
// rule. The production lock uses an RTC with backup (see docs §2.5).

#include <esp_timer.h>

#include "clock.h"

namespace opencylinder {

class Esp32Clock : public IClock {
 public:
  bool now(uint32_t& unixUtc) const override {
    if (!set_) return false;
    const uint64_t elapsed = static_cast<uint64_t>(esp_timer_get_time() - refUs_) / 1000000u;
    const uint64_t t = static_cast<uint64_t>(base_) + elapsed;
    if (t > 0xFFFFFFFFu) return false;  // beyond 2106: treat as unknown
    unixUtc = static_cast<uint32_t>(t);
    return true;
  }

  void set(uint32_t unixUtc) override {
    base_ = unixUtc;
    refUs_ = esp_timer_get_time();
    set_ = true;
  }

 private:
  bool set_ = false;
  uint32_t base_ = 0;
  int64_t refUs_ = 0;
};

}  // namespace opencylinder
