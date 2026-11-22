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

namespace {

// Days since 1970-01-01 for a civil date (Howard Hinnant's days_from_civil).
int64_t daysFromCivil(int64_t y, uint32_t m, uint32_t d) {
  y -= m <= 2;
  const int64_t era = (y >= 0 ? y : y - 399) / 400;
  const uint32_t yoe = static_cast<uint32_t>(y - era * 400);
  const uint32_t doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
  const uint32_t doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + static_cast<int64_t>(doe) - 719468;
}

// 0 = Sunday for a day count since 1970-01-01 (a Thursday).
uint32_t weekdaySun0(int64_t days) {
  const int64_t w = (days + 4) % 7;
  return static_cast<uint32_t>(w < 0 ? w + 7 : w);
}

const uint8_t kDaysInMonth[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};

bool isLeap(int64_t y) { return (y % 4 == 0 && y % 100 != 0) || y % 400 == 0; }

// Local (wall clock) seconds since epoch at which rule `t` fires in year y.
int64_t transitionLocal(int64_t y, const TzRule::Transition& t) {
  const int64_t first = daysFromCivil(y, t.month, 1);
  const uint32_t wdFirst = weekdaySun0(first);
  uint32_t day = 1 + (t.weekday + 7 - wdFirst) % 7 + (t.week - 1) * 7;
  uint32_t dim = kDaysInMonth[t.month - 1] + ((t.month == 2 && isLeap(y)) ? 1 : 0);
  while (day > dim) day -= 7;  // week 5 = last occurrence
  return (first + (day - 1)) * 86400 + t.time;
}

// --- tiny parser helpers ---
bool parseName(const char*& p) {
  int n = 0;
  if (*p == '<') {  // quoted form <+03>
    ++p;
    while (*p && *p != '>') { ++p; ++n; }
    if (*p != '>') return false;
    ++p;
    return n >= 1;
  }
  while ((*p >= 'A' && *p <= 'Z') || (*p >= 'a' && *p <= 'z')) { ++p; ++n; }
  return n >= 3;
}

bool parseUint(const char*& p, int32_t& v) {
  if (*p < '0' || *p > '9') return false;
  v = 0;
  while (*p >= '0' && *p <= '9') v = v * 10 + (*p++ - '0');
  return true;
}

// [+-]hh[:mm[:ss]] -> seconds
bool parseHms(const char*& p, int32_t& secs) {
  int sign = 1;
  if (*p == '+' || *p == '-') sign = (*p++ == '-') ? -1 : 1;
  int32_t h = 0, m = 0, s = 0;
  if (!parseUint(p, h)) return false;
  if (*p == ':') { ++p; if (!parseUint(p, m)) return false; }
  if (*p == ':') { ++p; if (!parseUint(p, s)) return false; }
  secs = sign * (h * 3600 + m * 60 + s);
  return true;
}

bool parseRule(const char*& p, TzRule::Transition& t) {
  if (*p++ != 'M') return false;  // only the Mm.w.d form is supported
  int32_t m, w, d;
  if (!parseUint(p, m) || *p++ != '.' || !parseUint(p, w) || *p++ != '.' || !parseUint(p, d)) {
    return false;
  }
  if (m < 1 || m > 12 || w < 1 || w > 5 || d < 0 || d > 6) return false;
  t.month = static_cast<uint8_t>(m);
  t.week = static_cast<uint8_t>(w);
  t.weekday = static_cast<uint8_t>(d);
  t.time = 2 * 3600;
  if (*p == '/') {
    ++p;
    if (!parseHms(p, t.time)) return false;
  }
  return true;
}

}  // namespace

bool parsePosixTz(const char* s, TzRule& out) {
  TzRule r;
  const char* p = s;
  int32_t off;
  if (!parseName(p) || !parseHms(p, off)) return false;
  r.stdOffset = -off;  // POSIX offsets are WEST of UTC
  if (*p == '\0') {
    out = r;
    return true;
  }
  if (!parseName(p)) return false;
  r.hasDst = true;
  r.dstOffset = r.stdOffset + 3600;
  if (*p != ',' && *p != '\0') {
    if (!parseHms(p, off)) return false;
    r.dstOffset = -off;
  }
  if (*p++ != ',' || !parseRule(p, r.start) || *p++ != ',' || !parseRule(p, r.end) || *p) {
    return false;
  }
  out = r;
  return true;
}

LocalTime toLocal(uint32_t unixUtc, const TzRule& tz) {
  const int64_t t = unixUtc;
  bool dst = false;
  if (tz.hasDst) {
    // Year of the standard-time wall clock decides which rules apply.
    const int64_t y = toUtc(static_cast<uint32_t>(t + tz.stdOffset > 0 ? t + tz.stdOffset : 0)).year;
    const int64_t startUtc = transitionLocal(y, tz.start) - tz.stdOffset;  // start in std time
    const int64_t endUtc = transitionLocal(y, tz.end) - tz.dstOffset;      // end in DST
    dst = (startUtc < endUtc) ? (t >= startUtc && t < endUtc)              // northern
                              : !(t >= endUtc && t < startUtc);            // southern
  }
  const int64_t local = t + (dst ? tz.dstOffset : tz.stdOffset);
  const int64_t days = (local >= 0 ? local : local - 86399) / 86400;
  const uint32_t sod = static_cast<uint32_t>(local - days * 86400);
  const UtcDateTime d = toUtc(static_cast<uint32_t>(days * 86400));

  LocalTime lt;
  lt.year = d.year;
  lt.month = d.month;
  lt.day = d.day;
  lt.hour = static_cast<uint8_t>(sod / 3600);
  lt.minute = static_cast<uint8_t>((sod / 60) % 60);
  lt.minuteOfDay = static_cast<uint16_t>(sod / 60);
  lt.weekday = static_cast<uint8_t>((weekdaySun0(days) + 6) % 7);  // Monday = 0
  lt.dst = dst;
  return lt;
}

}  // namespace opencylinder
