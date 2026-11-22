#pragma once
#include <cstdint>

// Values injected at build time by scripts/version.py (see docs/versioning.md).
#ifndef FW_VERSION
#define FW_VERSION "0.0.0-unversioned"
#endif
#ifndef FW_GIT
#define FW_GIT "unknown"
#endif
#ifndef OC_BOARD_NAME
#define OC_BOARD_NAME "unknown"
#endif

namespace opencylinder {

// Highest card record format this firmware understands (spec/card-format.md).
// Cards with any other format_version are rejected, never guessed at.
constexpr uint8_t kCardFormatVersion = 1;

}  // namespace opencylinder
