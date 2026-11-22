// OpenCylinder firmware — Phase 1, step 1: detect a card.
//
// Polls the ST25R3916 (M5Stack Unit NFC) for ISO14443-A cards and prints
// UID, type, ATQA/SAK each time a new card is presented. Compare the UID with
// the Proxmark3 (`hf 14a info`). No cryptography yet.

#include <Arduino.h>
#include <Wire.h>

#include <M5UnitUnified.h>
#include <M5UnitUnifiedNFC.h>

#include <string>

#include "version.h"

namespace {

m5::unit::UnitUnified units;
m5::unit::UnitNFC nfcUnit{};          // ST25R3916 over I2C
m5::nfc::NFCLayerA nfcA{nfcUnit};     // ISO14443-A layer

bool readerReady = false;
std::string lastUid;                  // suppress repeats while a card stays on

bool beginReader() {
  Wire.begin(OC_I2C_SDA, OC_I2C_SCL, 400000);
  return units.add(nfcUnit, Wire) && units.begin();
}

void printCard(m5::nfc::a::PICC& picc) {
  // detect() only classifies by SAK; identify() asks the card for details.
  const bool identified = nfcA.identify(picc);

  Serial.printf("UID   %s  (%u bytes)\n", picc.uidAsString().c_str(),
                static_cast<unsigned>(picc.size));
  Serial.printf("Type  %s%s\n", picc.typeAsString().c_str(),
                identified ? "" : "  (identify failed, provisional)");
  Serial.printf("ATQA  %04X  SAK %02X  ISO14443-4: %s  DESFire: %s\n\n",
                picc.atqa, picc.sak, picc.isISO14443_4() ? "yes" : "no",
                picc.isMifareDESFire() ? "yes" : "no");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s (%s) board=%s card-format<=%u\n",
                FW_VERSION, FW_GIT, OC_BOARD_NAME,
                opencylinder::kCardFormatVersion);
  Serial.printf("Phase 1 / step 1: card detection, I2C SDA=%d SCL=%d\n",
                OC_I2C_SDA, OC_I2C_SCL);

  readerReady = beginReader();
  if (!readerReady) {
    Serial.println("ERROR: ST25R3916 not found — check wiring "
                   "(yellow=SDA, white=SCL, red=5V, black=GND)");
    return;
  }
  Serial.println("Reader ready. Hold a card to the antenna.\n");
}

void loop() {
  if (!readerReady) {
    delay(1000);
    return;
  }
  units.update();

  m5::nfc::a::PICC picc{};
  if (nfcA.detect(picc)) {
    const std::string uid = picc.uidAsString();
    if (uid != lastUid) {
      lastUid = uid;
      printCard(picc);
    }
    nfcA.deactivate();
  } else {
    lastUid.clear();  // card removed: next tap is printed again
  }
  delay(100);
}
