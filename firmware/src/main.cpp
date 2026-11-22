// OpenCylinder firmware — Phase 2 bench: the access decision.
//
// The XIAO plays door 4 "Ward 1 - ward door" (zones 3 + 4) of the fictional
// hospital in examples/hospital/. On every card tap:
//   select site app 4F4331 -> AES auth with the site read key (key 1)
//   -> encrypted read of file 0 (header) and file 1 (access list)
//   -> decision per spec/card-format.md -> "OPEN ..." or "DENY: <reason>"
//
// Serial commands (dev only — production sets the time from admin cards):
//   time              show the lock's time
//   time <unix>       set UTC time in Unix seconds, e.g. `time 1795510800`
//   help

#include <Arduino.h>
#include <Wire.h>

#include <M5UnitUnified.h>
#include <M5UnitUnifiedNFC.h>

#include <string>
#include <vector>

#include "access_decision.h"
#include "clock.h"
#include "desfire_auth.h"
#include "desfire_crypto.h"
#include "platform/esp32/esp32_clock.h"
#include "platform/esp32/m5_desfire_transport.h"
#include "version.h"

namespace {

using namespace opencylinder;

// ---------------------------------------------------------------- bench lock
// Site AID 4F4331 (test site), LSB-first as sent on the wire.
constexpr uint8_t kSiteAid[3] = {0x31, 0x43, 0x4F};
constexpr uint8_t kReadKeyNo = 1;

// ==== PUBLIC DEV TEST KEY — bench only, never for a real site. ====
// Real keys never live in source code or in this repository. Not diversified
// per card yet (bench simplification, see examples/hospital/README.md).
constexpr uint8_t kDevReadKey[16] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                                     0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};

// Door 4 of examples/hospital/site.json, blacklist as in the example.
constexpr uint16_t kDoorId = 4;
constexpr uint16_t kLockZones[] = {3, 4};
constexpr uint32_t kBlacklist[] = {2003};
const LockConfig kLock{kDoorId, kLockZones, sizeof kLockZones / sizeof kLockZones[0],
                       kBlacklist, sizeof kBlacklist / sizeof kBlacklist[0]};

// ------------------------------------------------------------------ hardware
m5::unit::UnitUnified units;
m5::unit::UnitNFC nfcUnit{};          // ST25R3916 over I2C
m5::nfc::NFCLayerA nfcA{nfcUnit};     // ISO14443-A layer
Esp32Clock lockClock;

bool readerReady = false;
std::string lastUid;                  // suppress repeats while a card stays on
std::string serialLine;

bool beginReader() {
  Wire.begin(OC_I2C_SDA, OC_I2C_SCL, 400000);
  return units.add(nfcUnit, Wire) && units.begin();
}

void printTime(const char* label, uint32_t t) {
  const UtcDateTime d = toUtc(t);
  Serial.printf("%s%04u-%02u-%02u %02u:%02u:%02u UTC (%lu)\n", label, d.year, d.month, d.day,
                d.hour, d.minute, d.second, static_cast<unsigned long>(t));
}

// ------------------------------------------------------------ serial commands
void handleCommand(const std::string& line) {
  if (line == "help") {
    Serial.println("commands: time | time <unix-utc-seconds> | help");
  } else if (line == "time") {
    uint32_t t;
    if (lockClock.now(t)) printTime("time  ", t);
    else Serial.println("time  UNKNOWN (set with: time <unix-utc-seconds>)");
  } else if (line.rfind("time ", 0) == 0) {
    char* end = nullptr;
    const unsigned long long v = strtoull(line.c_str() + 5, &end, 10);
    if (end == line.c_str() + 5 || *end != '\0' || v > 0xFFFFFFFFull) {
      Serial.println("time  invalid value (unsigned Unix seconds, UTC)");
      return;
    }
    lockClock.set(static_cast<uint32_t>(v));
    printTime("time  set to ", static_cast<uint32_t>(v));
  } else if (!line.empty()) {
    Serial.printf("unknown command '%s' (try: help)\n", line.c_str());
  }
}

// Minimal line editor: the serial monitor sends every key raw and does not
// echo, so echo printable characters and handle Backspace / Delete here.
void pollSerial() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r' || c == '\n') {
      if (c == '\n' && serialLine.empty()) continue;  // CR LF: ignore the LF
      Serial.println();
      handleCommand(serialLine);
      serialLine.clear();
    } else if (c == '\b' || c == 0x7F) {
      if (!serialLine.empty()) {
        serialLine.pop_back();
        Serial.print("\b \b");
      }
    } else if (c >= 0x20 && c < 0x7F && serialLine.size() < 64) {
      serialLine += c;
      Serial.print(c);
    }
  }
}

// ---------------------------------------------------------------- decision
// A tap is evaluated at first detection, often while the card is still moving
// into the field. Communication failures there (the card browns out during the
// AES computation) are RETRIED; only real refusals are final.
enum class Outcome { Final, Retry };
constexpr int kMaxAttempts = 3;
constexpr uint32_t kRetryDelayMs = 50;
constexpr uint8_t kStatusNoSuchApp = 0xA0;
constexpr uint8_t kStatusAuthError = 0xAE;
constexpr uint8_t kNoResponse = 0xFF;

const char* retryReason = "";

Outcome deny(const char* reason) {
  Serial.printf("DENY  %s\n", reason);
  return Outcome::Final;
}
Outcome retry(const char* reason) {
  retryReason = reason;
  return Outcome::Retry;
}

Outcome evaluateCard(m5::nfc::a::PICC& picc) {
  const uint32_t t0 = millis();
  if (!picc.isMifareDESFire()) return deny("not a DESFire card");

  // Fresh activation incl. RATS -> ISO-DEP session sized from the card's ATS.
  if (!nfcA.reactivate(picc)) return retry("ISO-DEP activation failed");
  auto* dep = nfcA.isoDEP();
  if (!dep) return deny("no ISO-DEP context");
  M5DesfireTransport transport{*dep};
  DesfireAuth card{transport};

  if (!card.selectApplication(kSiteAid)) {
    if (card.lastStatus() == kStatusNoSuchApp) return deny("no application for this site (4F4331)");
    if (card.lastStatus() == kNoResponse) return retry(card.lastError());
    Serial.printf("      [%s, status %02X]\n", card.lastError(), card.lastStatus());
    return deny("select application failed");
  }
  if (!card.authenticateAes(kReadKeyNo, kDevReadKey)) {
    if (card.lastStatus() == kStatusAuthError) {
      return deny("authentication failed (wrong key or cloned card)");
    }
    if (card.lastStatus() == kNoResponse) return retry(card.lastError());
    Serial.printf("      [%s, status %02X]\n", card.lastError(), card.lastStatus());
    return deny("authentication failed");
  }

  std::vector<uint8_t> file0;
  if (!card.readDataEncrypted(0, 0, kHeaderSize, file0)) return retry("encrypted read of header");
  CardHeader h;
  parseHeader(file0.data(), file0.size(), h);
  Serial.printf("REC   credential %lu, format %u, %u entries\n",
                static_cast<unsigned long>(h.credentialId), h.formatVersion, h.entryCount);
  if (h.validUntil) printTime("      valid until ", h.validUntil);
  else Serial.println("      valid until: no expiry");
  printTime("      issued at   ", h.issuedAt);

  uint32_t now = 0;
  const bool timeKnown = lockClock.now(now);
  const Decision pre = checkHeader(h, kLock, timeKnown, now);
  if (pre != Decision::Open) return deny(toString(pre));

  std::vector<uint8_t> file1;
  std::vector<AccessEntry> entries;
  if (h.entryCount) {
    if (!card.readDataEncrypted(1, 0, h.entryCount * kEntrySize, file1)) {
      return retry("encrypted read of access list");
    }
    parseEntries(file1.data(), file1.size(), h.entryCount, entries);
  }
  const Result r = decide(h, entries, kLock, timeKnown, now);
  const uint32_t ms = millis() - t0;
  if (r.decision == Decision::Open) {
    Serial.printf("OPEN  via %s %u%s  (%lu ms)\n",
                  r.matched.type == kEntryDoor ? "door" : "zone", r.matched.targetId,
                  r.matched.timeProfile ? ", time profile" : "", static_cast<unsigned long>(ms));
  } else {
    Serial.printf("DENY  %s  (%lu ms)\n", toString(r.decision), static_cast<unsigned long>(ms));
  }
  return Outcome::Final;
}

// One tap: up to kMaxAttempts tries while the card stays in the field.
void handleTap(m5::nfc::a::PICC& picc) {
  Serial.printf("CARD  %s  %s\n", picc.uidAsString().c_str(), picc.typeAsString().c_str());
  for (int attempt = 1; attempt <= kMaxAttempts; ++attempt) {
    if (evaluateCard(picc) == Outcome::Final) return;
    if (attempt == kMaxAttempts) break;
    Serial.printf("      retry %d/%d (%s)\n", attempt, kMaxAttempts - 1, retryReason);
    nfcA.deactivate();
    delay(kRetryDelayMs);
  }
  deny("card not readable - hold it flat on the reader");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s (%s) board=%s card-format<=%u\n", FW_VERSION, FW_GIT,
                OC_BOARD_NAME, kCardFormatVersion);
  Serial.printf("Phase 2 bench: door %u (zones 3, 4), site 4F4331, I2C SDA=%d SCL=%d\n",
                kDoorId, OC_I2C_SDA, OC_I2C_SCL);

  const bool selfTest = crypto::selfTest();
  Serial.printf("Crypto self-test (AES-CMAC RFC 4493, CRC32): %s\n", selfTest ? "PASS" : "FAIL");
  if (!selfTest) {
    Serial.println("ERROR: crypto self-test failed — refusing to operate.");
    return;
  }

  readerReady = beginReader();
  if (!readerReady) {
    Serial.println("ERROR: ST25R3916 not found — check wiring "
                   "(yellow=SDA, white=SCL, red=5V, black=GND)");
    return;
  }
  Serial.println("Time UNKNOWN until set (type: help). Hold a card to the antenna.\n");
}

void loop() {
  pollSerial();
  if (!readerReady) {
    delay(50);
    return;
  }
  units.update();

  m5::nfc::a::PICC picc{};
  if (nfcA.detect(picc)) {
    const std::string uid = picc.uidAsString();
    if (uid != lastUid) {
      lastUid = uid;
      // detect() only classifies by SAK; identify() asks the card for details.
      nfcA.identify(picc);
      handleTap(picc);
      Serial.println();
    }
    nfcA.deactivate();
  } else {
    lastUid.clear();  // card removed: next tap is evaluated again
  }
  delay(50);
}
