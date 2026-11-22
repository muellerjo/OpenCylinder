#include "clock.h"

namespace opencylinder {

UtcDateTime toUtc(uint32_t t) {
  // Howard Hinnant's civil_from_days, valid for the whole uint32_t range.
  const uint32_t days = t / 86400u;
  const uint32_t secs = t % 86400u;
  int64_t z = static_cast<int64_t>(days) + 719468;
  const int64_t era = z / 146097;
  const uint32_t doe = static_cast<uint32_t>(z - era * 146097);
  const uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const uint32_t mp = (5 * doy + 2) / 153;
  const uint32_t d = doy - (153 * mp + 2) / 5 + 1;
  const uint32_t m = mp < 10 ? mp + 3 : mp - 9;
  const int64_t y = static_cast<int64_t>(yoe) + era * 400 + (m <= 2 ? 1 : 0);

  UtcDateTime r;
  r.year = static_cast<uint16_t>(y);
  r.month = static_cast<uint8_t>(m);
  r.day = static_cast<uint8_t>(d);
  r.hour = static_cast<uint8_t>(secs / 3600);
  r.minute = static_cast<uint8_t>((secs / 60) % 60);
  r.second = static_cast<uint8_t>(secs % 60);
  return r;
}

}  // namespace opencylinder
