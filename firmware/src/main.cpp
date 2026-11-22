// OpenCylinder firmware — Phase 1 bring-up.
//
// Step 1: detect a card, print UID / type / ATQA / SAK
//         (compare with Proxmark3 `hf 14a info`).
// Step 2: for DESFire cards, open an ISO-DEP session and send the native
//         GetVersion command through IDesfireTransport
//         (compare with Proxmark3 `hf mfdes info`, "raw" lines).
// Step 3: select application F51001 and run AES authentication with
//         desfire_auth, first with the factory zero key, then with the
//         dev test key (cross-check with Proxmark3 `hf mfdes auth`).

#include <Arduino.h>
#include <Wire.h>

#include <M5UnitUnified.h>
#include <M5UnitUnifiedNFC.h>

#include <string>
#include <vector>

#include "platform/esp32/m5_desfire_transport.h"
#include "version.h"

namespace {

m5::unit::UnitUnified units;
m5::unit::UnitNFC nfcUnit{};          // ST25R3916 over I2C
m5::nfc::NFCLayerA nfcA{nfcUnit};     // ISO14443-A layer

bool readerReady = false;
std::string lastUid;                  // suppress repeats while a card stays on

constexpr uint8_t kCmdGetVersion      = 0x60;
constexpr uint8_t kCmdAdditionalFrame = 0xAF;
constexpr uint8_t kStatusOk           = 0x00;

// OpenCylinder application, LSB-first as sent on the wire (AID 0xF51001).
constexpr uint8_t kAppAid[3] = {0x01, 0x10, 0xF5};

// ==== DEV TEST KEYS ONLY — never use for a real site key. ====
// Real keys never live in source code or in this repository.
constexpr uint8_t kZeroKey[16] = {0};
constexpr uint8_t kDevTestKey[16] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55,
                                     0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB,
                                     0xCC, 0xDD, 0xEE, 0xFF};

bool beginReader() {
  Wire.begin(OC_I2C_SDA, OC_I2C_SCL, 400000);
  return units.add(nfcUnit, Wire) && units.begin();
}

void printHex(const char* label, const uint8_t* p, size_t n) {
  Serial.printf("%s", label);
  for (size_t i = 0; i < n; ++i) Serial.printf("%02X", p[i]);
  Serial.println();
}

void printCard(m5::nfc::a::PICC& picc) {
  Serial.printf("UID   %s  (%u bytes)\n", picc.uidAsString().c_str(),
                static_cast<unsigned>(picc.size));
  Serial.printf("Type  %s\n", picc.typeAsString().c_str());
  Serial.printf("ATQA  %04X  SAK %02X  ISO14443-4: %s  DESFire: %s\n",
                picc.atqa, picc.sak, picc.isISO14443_4() ? "yes" : "no",
                picc.isMifareDESFire() ? "yes" : "no");
}

// Native DESFire GetVersion: three frames (0x60, then 0xAF twice).
// Expected 28 bytes: hw info (7) | sw info (7) | UID (7) | batch (5) |
// production week (1) | production year (1).
bool desfireGetVersion(opencylinder::IDesfireTransport& t,
                       std::vector<uint8_t>& version) {
  version.clear();
  opencylinder::DesfireResponse r;
  uint8_t cmd = kCmdGetVersion;
  for (int frame = 0; frame < 3; ++frame) {
    if (!t.transceive(cmd, nullptr, 0, r)) {
      Serial.printf("GetVersion: no response in frame %d\n", frame + 1);
      return false;
    }
    version.insert(version.end(), r.data.begin(), r.data.end());
    const bool last = (frame == 2);
    const uint8_t expected = last ? kStatusOk : kCmdAdditionalFrame;
    if (r.status != expected) {
      Serial.printf("GetVersion: frame %d status %02X (expected %02X)\n",
                    frame + 1, r.status, expected);
      return false;
    }
    cmd = kCmdAdditionalFrame;
  }
  return version.size() == 28;
}

void runStep2(m5::nfc::a::PICC& picc) {
  // Fresh activation incl. RATS -> ISO-DEP session sized from the card's ATS.
  if (!nfcA.reactivate(picc)) {
    Serial.println("ISO-DEP: reactivate failed");
    return;
  }
  auto* dep = nfcA.isoDEP();
  if (!dep) {
    Serial.println("ISO-DEP: no ISO-DEP context");
    return;
  }
  opencylinder::M5DesfireTransport transport{*dep};

  std::vector<uint8_t> v;
  if (!desfireGetVersion(transport, v)) {
    Serial.printf("GetVersion failed (%u bytes received)\n",
                  static_cast<unsigned>(v.size()));
    return;
  }
  printHex("HW    ", v.data() + 0, 7);
  printHex("SW    ", v.data() + 7, 7);
  printHex("UID'  ", v.data() + 14, 7);
  printHex("Batch ", v.data() + 21, 5);
  Serial.printf("Prod  week %02X / 20%02X\n", v[26], v[27]);

  // ---- Step 3: AES authentication on application F51001, key 0 ----
  opencylinder::DesfireAuth auth{transport};
  struct Candidate {
    const char* name;
    const uint8_t* key;
  };
  const Candidate candidates[] = {{"zero key", kZeroKey},
                                  {"dev test key", kDevTestKey}};
  for (const auto& c : candidates) {
    // A failed authentication drops the card's auth state, so select again
    // before every attempt.
    if (!auth.selectApplication(kAppAid)) {
      Serial.println("AUTH  SelectApplication F51001 failed "
                     "(app not created on this card?)");
      return;
    }
    uint8_t sessionKey[16];
    const bool ok = auth.authenticateAes(0, c.key, sessionKey);
    memset(sessionKey, 0, sizeof(sessionKey));  // not needed yet; don't keep it
    Serial.printf("AUTH  app F51001 key 0, %-12s : %s\n", c.name,
                  ok ? "OK" : "failed");
    if (ok) return;
  }
  Serial.println("AUTH  no candidate key accepted");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s (%s) board=%s card-format<=%u\n",
                FW_VERSION, FW_GIT, OC_BOARD_NAME,
                opencylinder::kCardFormatVersion);
  Serial.printf("Phase 1 / steps 1+2: detection + ISO-DEP GetVersion, "
                "I2C SDA=%d SCL=%d\n", OC_I2C_SDA, OC_I2C_SCL);

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
      // detect() only classifies by SAK; identify() asks the card for details.
      if (!nfcA.identify(picc)) Serial.println("(identify failed, provisional)");
      printCard(picc);
      if (picc.isMifareDESFire()) runStep2(picc);
      Serial.println();
    }
    nfcA.deactivate();
  } else {
    lastUid.clear();  // card removed: next tap is printed again
  }
  delay(100);
}
