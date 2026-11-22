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

#ifndef OC_VARIANT_NAME
#define OC_VARIANT_NAME "unknown"
#endif

// Remote unlock must never be part of an offline build (docs/online-architecture.md).
#if defined(OC_VARIANT_OFFLINE) && defined(OC_FEATURE_REMOTE_UNLOCK)
#error "OC_FEATURE_REMOTE_UNLOCK is not allowed in an offline variant"
#endif

namespace opencylinder {

// Highest card record format this firmware understands (spec/card-format.md).
// Cards with any other format_version are rejected, never guessed at.
constexpr uint8_t kCardFormatVersion = 1;

}  // namespace opencylinder
