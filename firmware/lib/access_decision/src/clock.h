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

// Rollback rule (docs/lifecycle-and-security.md §2.5 rule 3): a new time is
// accepted only if it is not more than `tolerance` seconds earlier than the
// high-water mark (latest time ever accepted). Otherwise an old admin card
// could turn the clock back and revive expired cards.
constexpr uint32_t kRollbackToleranceS = 5 * 60;
inline bool timeUpdateAllowed(uint32_t newTime, uint32_t highWater,
                              uint32_t tolerance = kRollbackToleranceS) {
  return highWater <= tolerance || newTime >= highWater - tolerance;
}

// Civil UTC date/time from Unix seconds without time_t / gmtime (Y2038-safe).
struct UtcDateTime {
  uint16_t year;
  uint8_t month, day, hour, minute, second;
};
UtcDateTime toUtc(uint32_t unixUtc);

// Site time zone as a POSIX TZ rule subset — spec/time-profiles.md:
//   STD offset [DST [offset] ,Mm.w.d[/time] ,Mm.w.d[/time]]
// e.g. "CET-1CEST,M3.5.0,M10.5.0/3" (Germany), "UTC0", "EST5EDT,M3.2.0,M11.1.0".
// The lock keeps UTC; this converts to local wall time incl. daylight saving.
struct TzRule {
  int32_t stdOffset = 0;   // seconds EAST of UTC (CET = +3600)
  int32_t dstOffset = 0;   // seconds east of UTC during DST
  bool hasDst = false;
  struct Transition {
    uint8_t month, week, weekday;  // Mm.w.d: week 1..5 (5 = last), weekday 0 = Sunday
    int32_t time;                  // local seconds after midnight (default 02:00)
  } start{}, end{};
};
bool parsePosixTz(const char* s, TzRule& out);

struct LocalTime {
  uint16_t year;
  uint8_t month, day, hour, minute;
  uint8_t weekday;          // 0 = Monday ... 6 = Sunday
  uint16_t minuteOfDay;     // 0..1439
  bool dst;
};
LocalTime toLocal(uint32_t unixUtc, const TzRule& tz);

}  // namespace opencylinder
