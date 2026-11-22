#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace opencylinder {

// One native DESFire command exchange: status byte + response data.
// status == 0x00 -> OK, 0xAF -> additional frame expected, otherwise an error.
struct DesfireResponse {
  uint8_t status = 0xFF;
  std::vector<uint8_t> data;
};

// Transport abstraction. Implement this on top of the NFC frontend
// (ST25R3916 via M5Unit-NFC / ST RFAL ISO-DEP), or a mock for PC tests.
// Commands are sent as *native* DESFire commands over ISO14443-4 (ISO-DEP),
// not wrapped in ISO 7816 APDUs.
// Keeping the auth logic behind this interface means the crypto flow can be
// unit-tested on a PC, and porting to nRF52 / STM32L5 only swaps this layer.
class IDesfireTransport {
 public:
  virtual ~IDesfireTransport() = default;
  virtual bool transceive(uint8_t cmd, const uint8_t* data, size_t len,
                          DesfireResponse& out) = 0;
};

// AES-128 authentication (DESFire native command 0xAA) against one key of the
// currently selected application. On success derives the 16-byte session key.
//
// SECURITY NOTES — read before trusting this in production:
//  * Follows the common DESFire EV1 AES convention; the CBC/IV chaining is the
//    part to validate against a known-good reference. Use the Proxmark3
//    `hf mfdes auth` as the oracle on a real card.
//  * `key` must never originate from plain flash. Production targets keep it
//    in hardware key storage (nRF52 CryptoCell/KMU, STM32 secure storage, or an
//    ATECC608A); on the ESP32 dev boards at minimum use flash encryption +
//    secure boot. Until then this is a prototype, not secure.
class DesfireAuth {
 public:
  explicit DesfireAuth(IDesfireTransport& transport) : t_(transport) {}

  // Select an application by its 3-byte AID, given LSB-first (wire order),
  // e.g. AID 0xF51001 -> {0x01, 0x10, 0xF5}.
  bool selectApplication(const uint8_t aid[3]);

  // Authenticate with AES `key` (16 bytes) as key number `keyNo`.
  // Writes the 16-byte session key on success; on failure `sessionKey` is
  // left zeroed.
  bool authenticateAes(uint8_t keyNo, const uint8_t key[16],
                       uint8_t sessionKey[16]);

 private:
  IDesfireTransport& t_;
};

}  // namespace opencylinder
