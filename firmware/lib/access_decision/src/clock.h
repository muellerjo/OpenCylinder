#pragma once
// Lock clock — docs/lifecycle-and-security.md §2.5.
// Unsigned 32-bit Unix UTC seconds (valid until 2106); never time_t, which is
// a signed 32-bit type on some embedded C libraries (e.g. Arduino ESP32-C3).

#include <cstdint>

namespace opencylinder {

class IClock {
 public:
  virtual ~IClock() = default;
  // Current time; false = time unknown (never set, or lost with power).
  virtual bool now(uint32_t& unixUtc) const = 0;
  virtual void set(uint32_t unixUtc) = 0;
};

// Civil UTC date/time from Unix seconds without time_t / gmtime (Y2038-safe).
struct UtcDateTime {
  uint16_t year;
  uint8_t month, day, hour, minute, second;
};
UtcDateTime toUtc(uint32_t unixUtc);

}  // namespace opencylinder
