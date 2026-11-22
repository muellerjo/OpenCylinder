#include "m5_desfire_transport.h"

#include <cstring>

namespace opencylinder {

bool M5DesfireTransport::transceive(uint8_t cmd, const uint8_t* data,
                                    size_t len, DesfireResponse& out) {
  out.status = 0xFF;
  out.data.clear();

  uint8_t tx[m5::nfc::isodep::MAX_FRAME_SIZE];
  if (len + 1 > sizeof(tx)) return false;
  tx[0] = cmd;
  if (len) memcpy(tx + 1, data, len);

  uint8_t rx[m5::nfc::isodep::MAX_FRAME_SIZE];
  uint16_t rxLen = sizeof(rx);
  if (!dep_.transceiveINF(rx, rxLen, tx, static_cast<uint16_t>(len + 1)) ||
      rxLen < 1) {
    return false;
  }

  out.status = rx[0];
  out.data.assign(rx + 1, rx + rxLen);
  return true;
}

}  // namespace opencylinder
