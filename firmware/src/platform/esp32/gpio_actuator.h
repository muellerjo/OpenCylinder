#pragma once
// Bench actuator: one GPIO driving an LED or a relay module (active high).
// The pin is forced low (disengaged) in begin() — call it first thing in
// setup() — and whenever the window expires.

#include <Arduino.h>

#include "actuator.h"

namespace opencylinder {

class GpioActuator : public IActuator {
 public:
  static constexpr uint32_t kHardLimitMs = 10000;  // never engaged longer

  explicit GpioActuator(int pin) : pin_(pin) {}

  void begin() {
    digitalWrite(pin_, LOW);
    pinMode(pin_, OUTPUT);
    digitalWrite(pin_, LOW);
    engaged_ = false;
  }

  void engage(uint32_t ms) override {
    if (ms > kHardLimitMs) ms = kHardLimitMs;
    since_ = millis();
    window_ = ms;
    digitalWrite(pin_, HIGH);
    engaged_ = true;
  }

  void release() override {
    digitalWrite(pin_, LOW);
    engaged_ = false;
  }

  bool engaged() const override { return engaged_; }

  void poll() override {
    if (engaged_ && millis() - since_ >= window_) release();
  }

 private:
  int pin_;
  bool engaged_ = false;
  uint32_t since_ = 0;
  uint32_t window_ = 0;
};

}  // namespace opencylinder
