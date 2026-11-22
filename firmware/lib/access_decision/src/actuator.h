#pragma once
// Actuator abstraction — the clutch motor / relay that couples the outer knob.
//
// Fail-safe model (docs/lifecycle-and-security.md, hardware/mechanics):
//   * default = DISENGAGED: the outer knob freewheels; the inner knob and the
//     mechanical override always work, also without power;
//   * engage only after an OPEN decision, for a bounded time, then release.

#include <cstdint>

namespace opencylinder {

class IActuator {
 public:
  virtual ~IActuator() = default;
  // Couple for `ms` milliseconds (non-blocking; re-arming extends the window,
  // capped by the implementation's hard limit).
  virtual void engage(uint32_t ms) = 0;
  // Release immediately.
  virtual void release() = 0;
  virtual bool engaged() const = 0;
  // Call often from the main loop: releases when the window has expired.
  virtual void poll() = 0;
};

}  // namespace opencylinder
