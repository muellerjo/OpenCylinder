#pragma once
// IDesfireTransport on top of the M5Unit-NFC ISO-DEP layer (ST25R3916).
// ESP32 dev-board specific; the nRF52 / STM32 port provides its own transport.

#include <M5UnitUnifiedNFC.h>

#include "desfire_auth.h"

namespace opencylinder {

// Sends *native* DESFire frames over ISO14443-4:
//   tx INF = [cmd][data...]      rx INF = [status][data...]
// DESFire-level chaining (status 0xAF) is left to the caller, exactly like
// the card does it; ISO-DEP block chaining / WTX is handled by the library.
class M5DesfireTransport : public IDesfireTransport {
 public:
  explicit M5DesfireTransport(m5::nfc::isodep::IsoDEP& isoDep) : dep_(isoDep) {}

  bool transceive(uint8_t cmd, const uint8_t* data, size_t len,
                  DesfireResponse& out) override;

 private:
  m5::nfc::isodep::IsoDEP& dep_;
};

}  // namespace opencylinder
