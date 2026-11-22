#pragma once
// User feedback via a plain RGB LED (3 PWM pins, no standby current — the
// reason not to use a WS2812 in a battery lock). Non-blocking: call poll()
// from the main loop. Separate from the actuator on purpose: the clutch
// logic never depends on the display.

#include <Arduino.h>

namespace opencylinder {

enum class LedPattern : uint8_t {
  Off,
  Open,         // green, steady
  Deny,         // red, steady
  Retry,        // yellow, steady
  Unreadable,   // yellow, blinking
  TimeUnknown,  // blue, short flash every 2 s (idle pattern)
  Error,        // red, fast blink (forever)
  Admin,        // blue, steady (admin bundle applied)
};

class RgbStatusLed {
 public:
  RgbStatusLed(int pinR, int pinG, int pinB, bool activeHigh)
      : pins_{pinR, pinG, pinB}, activeHigh_(activeHigh) {}

  void begin() {
    for (int i = 0; i < 3; ++i) {
      ledcSetup(kChannel0 + i, 5000, 8);
      ledcAttachPin(pins_[i], kChannel0 + i);
    }
    write(0, 0, 0);
  }

  // Show `p` for `ms` milliseconds (0 = until replaced), then return to the
  // idle pattern.
  void show(LedPattern p, uint32_t ms = 0) {
    const uint32_t now = millis();
    setPattern(p, now);
    since_ = now;
    duration_ = ms;
    apply();
  }

  void setIdle(LedPattern p) { idle_ = p; }

  void poll() {
    const uint32_t now = millis();
    if (duration_ && now - since_ >= duration_) {
      setPattern(idle_, now);
      duration_ = 0;
    }
    // Idle-type patterns always follow the current idle state (e.g. blue
    // flash stops as soon as the time is set).
    if (!duration_ && (pattern_ == LedPattern::Off || pattern_ == LedPattern::TimeUnknown) &&
        pattern_ != idle_) {
      setPattern(idle_, now);
    }
    // Event-based blinking: every on/off change happens even if poll() is
    // called late (the main loop polls only every ~150 ms) — no aliasing.
    if (onMs_ && static_cast<int32_t>(now - nextChange_) >= 0) {
      lit_ = !lit_;
      nextChange_ = now + (lit_ ? onMs_ : offMs_);
    }
    apply();
  }

 private:
  static constexpr uint8_t kChannel0 = 0;
  static constexpr uint8_t kLevel = 60;  // of 255: bright enough, battery-minded

  // Blink timing per pattern: on/off phase lengths (0 = steady).
  void setPattern(LedPattern p, uint32_t now) {
    pattern_ = p;
    switch (p) {
      case LedPattern::Unreadable:  onMs_ = 150; offMs_ = 150;  break;
      case LedPattern::TimeUnknown: onMs_ = 80;  offMs_ = 1920; break;
      case LedPattern::Error:       onMs_ = 100; offMs_ = 100;  break;
      default:                      onMs_ = 0;   offMs_ = 0;    break;
    }
    lit_ = true;  // blink patterns start with the light on
    nextChange_ = now + onMs_;
  }

  void apply() {
    switch (pattern_) {
      case LedPattern::Off:         write(0, 0, 0); break;
      case LedPattern::Open:        write(0, kLevel, 0); break;
      case LedPattern::Deny:        write(kLevel, 0, 0); break;
      case LedPattern::Retry:       write(kLevel, kLevel / 2, 0); break;
      case LedPattern::Admin:       write(0, 0, kLevel); break;
      case LedPattern::Unreadable:  lit_ ? write(kLevel, kLevel / 2, 0) : write(0, 0, 0); break;
      case LedPattern::TimeUnknown: lit_ ? write(0, 0, kLevel) : write(0, 0, 0); break;
      case LedPattern::Error:       lit_ ? write(kLevel, 0, 0) : write(0, 0, 0); break;
    }
  }

  void write(uint8_t r, uint8_t g, uint8_t b) {
    const uint8_t v[3] = {r, g, b};
    for (int i = 0; i < 3; ++i) ledcWrite(kChannel0 + i, activeHigh_ ? v[i] : 255 - v[i]);
  }

  int pins_[3];
  bool activeHigh_;
  LedPattern pattern_ = LedPattern::Off;
  LedPattern idle_ = LedPattern::Off;
  uint32_t since_ = 0;
  uint32_t duration_ = 0;
  uint32_t onMs_ = 0, offMs_ = 0, nextChange_ = 0;
  bool lit_ = false;
};

}  // namespace opencylinder
