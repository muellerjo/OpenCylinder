// OpenCylinder firmware — dev skeleton.
// For now: boot banner with version info + I2C bus up for the ST25R3916 unit.
// Phase 1 (card detection, ISO-DEP, desfire_auth) builds on top of this.

#include <Arduino.h>
#include <Wire.h>

#include "version.h"

void setup() {
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s (%s) board=%s card-format<=%u\n",
                FW_VERSION, FW_GIT, OC_BOARD_NAME,
                opencylinder::kCardFormatVersion);

  Wire.begin(OC_I2C_SDA, OC_I2C_SCL, 400000);
}

void loop() { delay(1000); }
