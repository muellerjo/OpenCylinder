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

// DESFire EV1 session: application select, AES authentication (0xAA) and
// EV1 AES secure messaging for encrypted reads.
//
// SECURITY NOTES — read before trusting this in production:
//  * Verified on a real DESFire EV1 against Proxmark3 `hf mfdes`.
//  * `key` must never originate from plain flash. Production targets keep it
//    in hardware key storage (nRF52 CryptoCell/KMU, STM32 secure storage, or an
//    ATECC608A); on the ESP32 dev boards at minimum use flash encryption +
//    secure boot. Until then this is a prototype, not secure.
//  * The session key and IV live only inside this object and are wiped on
//    reset, on any error and on destruction.
class DesfireAuth {
 public:
  explicit DesfireAuth(IDesfireTransport& transport) : t_(transport) {}
  ~DesfireAuth();
  DesfireAuth(const DesfireAuth&) = delete;
  DesfireAuth& operator=(const DesfireAuth&) = delete;

  // Select an application by its 3-byte AID, given LSB-first (wire order),
  // e.g. AID 0x4F4331 -> {0x31, 0x43, 0x4F}. Drops any session.
  bool selectApplication(const uint8_t aid[3]);

  // Authenticate with AES `key` (16 bytes) as key number `keyNo` of the
  // selected application. On success a session is established (IV = 0).
  bool authenticateAes(uint8_t keyNo, const uint8_t key[16]);

  bool authenticated() const { return authenticated_; }

  // Diagnostics for the last failed call: where it failed and the card's
  // status byte (0xFF = no response / transport error). Never secret.
  const char* lastError() const { return lastError_; }
  uint8_t lastStatus() const { return lastStatus_; }

  // ReadData (0xBD) of a StandardDataFile in communication mode "full"
  // (encrypted, CRC32-protected). Needs a preceding authenticateAes with a
  // key that has read rights. `length` 1..kMaxReadLength bytes from `offset`.
  // Fails (and drops the session) on any protocol, padding or CRC error.
  static constexpr uint32_t kMaxReadLength = 256;
  bool readDataEncrypted(uint8_t fileNo, uint32_t offset, uint32_t length,
                         std::vector<uint8_t>& out);

  // ReadData (0xBD) of a file with FREE read access, communication mode
  // plain, without authentication (commissioning card, spec §5.3).
  bool readDataPlain(uint8_t fileNo, uint32_t offset, uint32_t length, std::vector<uint8_t>& out);

  // WriteData (0x3D) to a file with FREE write access, communication mode
  // plain, without authentication (identify card, spec/admin-card.md §5.5).
  // Long data is sent in DESFire-level frames (0xAF chaining).
  bool writeDataPlain(uint8_t fileNo, uint32_t offset, const uint8_t* data, uint32_t length);

  // GetCardUID (0x51): the card's real 7-byte UID, also on random-UID cards.
  // Needs a preceding authenticateAes (any key); response is encrypted with
  // CRC32 like a "full" read.
  bool getCardUid(uint8_t uid[7]);

 private:
  void resetSession();
  bool fail(const char* where, uint8_t status = 0xFF);
  // Send cmd || hdr (plain, CMAC-chained IV) and receive an encrypted
  // response of `length` plaintext bytes + CRC32 + zero padding.
  bool exchangeEncrypted(uint8_t cmd, const uint8_t* hdr, size_t hdrLen,
                         uint32_t length, std::vector<uint8_t>& out);

  IDesfireTransport& t_;
  bool authenticated_ = false;
  uint8_t sessionKey_[16] = {0};
  uint8_t iv_[16] = {0};
  const char* lastError_ = "";
  uint8_t lastStatus_ = 0xFF;
};

}  // namespace opencylinder
