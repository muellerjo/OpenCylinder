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
#include "platform/esp32/gpio_actuator.h"
#include "platform/esp32/m5_desfire_transport.h"
#include "version.h"

namespace {

using namespace opencylinder;

// ---------------------------------------------------------------- bench lock
// Site AID 4F4331 (test site), LSB-first as sent on the wire.
constexpr uint8_t kSiteAid[3] = {0x31, 0x43, 0x4F};
constexpr uint8_t kReadKeyNo = 1;

// ==== PUBLIC DEV TEST MASTER KEY — bench only, never for a real site. ====
// Real keys never live in source code or in this repository. The card holds
// a per-card key diversified from it (AN10922, M = UID || AID).
constexpr uint8_t kDevReadMasterKey[16] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                                     0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};
// Site-wide UID key (key 2): only lets the lock fetch the real UID of a
// random-UID card. Public dev test key.
constexpr uint8_t kUidKeyNo = 2;
constexpr uint8_t kDevUidKey[16] = {0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
                                    0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF};

// Dev switch (serial `uidmode`): force the random-UID path (key 2 +
// GetCardUID) also for fixed-UID cards, to test it without irreversibly
// enabling random UID on a card.
bool forceUidKeyPath = false;

// Door 4 of examples/hospital/site.json, blacklist as in the example.
constexpr uint16_t kDoorId = 4;
constexpr uint16_t kLockZones[] = {3, 4};
constexpr uint32_t kBlacklist[] = {2003};
// Time profiles of examples/hospital/site.json and the site time zone
// (spec/time-profiles.md). Production: delivered by admin card.
const TimeProfile kProfiles[] = {
    {1, 0x7F, {{6 * 60, 20 * 60}, {0, 0}}},                          // Day shift, daily
    {2, kMon | kTue | kWed | kThu | kFri | kSat, {{5 * 60, 11 * 60}, {0, 0}}},  // Cleaning
    {3, kMon | kTue | kWed | kThu | kFri, {{7 * 60, 18 * 60}, {0, 0}}},        // Office hours
};
const char* const kSiteTz = "CET-1CEST,M3.5.0,M10.5.0/3";  // Europe/Berlin
TzRule siteTz;
const LockConfig kLock{kDoorId, kLockZones, sizeof kLockZones / sizeof kLockZones[0],
                       kBlacklist, sizeof kBlacklist / sizeof kBlacklist[0],
                       kProfiles, sizeof kProfiles / sizeof kProfiles[0], &siteTz};

// ------------------------------------------------------------------ hardware
m5::unit::UnitUnified units;
m5::unit::UnitNFC nfcUnit{};          // ST25R3916 over I2C
m5::nfc::NFCLayerA nfcA{nfcUnit};     // ISO14443-A layer
Esp32Clock lockClock;
GpioActuator actuator{OC_ACTUATOR_PIN};
constexpr uint32_t kOpenWindowMs = 3000;   // clutch engaged after OPEN

bool readerReady = false;
std::string lastUid;                  // suppress repeats while a card stays on
std::string serialLine;

bool beginReader() {
  Wire.begin(OC_I2C_SDA, OC_I2C_SCL, 400000);
  return units.add(nfcUnit, Wire) && units.begin();
}

void printTime(const char* label, uint32_t t) {
  static const char* const kDay[] = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
  const UtcDateTime d = toUtc(t);
  const LocalTime l = toLocal(t, siteTz);
  Serial.printf("%s%04u-%02u-%02u %02u:%02u:%02u UTC = %s %02u:%02u local%s (%lu)\n", label,
                d.year, d.month, d.day, d.hour, d.minute, d.second, kDay[l.weekday], l.hour,
                l.minute, l.dst ? " DST" : "", static_cast<unsigned long>(t));
}

// ------------------------------------------------------------ serial commands
void handleCommand(const std::string& line) {
  if (line == "help") {
    Serial.println("commands: time | time <unix-utc-seconds> | time reset-hwm |"
                   " uidmode [auto|key2] | help");
  } else if (line == "uidmode" || line == "uidmode auto" || line == "uidmode key2") {
    if (line != "uidmode") forceUidKeyPath = (line == "uidmode key2");
    Serial.printf("uidmode %s\n", forceUidKeyPath
                                      ? "key2 (always fetch the real UID via key 2 + GetCardUID)"
                                      : "auto (anticollision UID; key 2 only for random-UID cards)");
  } else if (line == "time") {
    uint32_t t;
    if (lockClock.now(t)) printTime("time  ", t);
    else Serial.println("time  UNKNOWN (set with: time <unix-utc-seconds>)");
    if (lockClock.highWater()) printTime("      high-water mark ", lockClock.highWater());
  } else if (line == "time reset-hwm") {
    lockClock.resetHighWater();
    Serial.println("time  high-water mark and time cleared (bench only) - time is UNKNOWN");
  } else if (line.rfind("time ", 0) == 0) {
    char* end = nullptr;
    const unsigned long long v = strtoull(line.c_str() + 5, &end, 10);
    if (end == line.c_str() + 5 || *end != '\0' || v > 0xFFFFFFFFull) {
      Serial.println("time  invalid value (unsigned Unix seconds, UTC)");
      return;
    }
    if (!lockClock.trySet(static_cast<uint32_t>(v))) {
      printTime("time  REJECTED (rollback) — high-water mark is ", lockClock.highWater());
      return;
    }
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
  // Real UID for key diversification (spec: "Getting the real UID").
  //  - fixed 7-byte UID: the anticollision UID is the real one;
  //  - random UID (4 bytes, first byte 0x08): auth with the UID key (key 2),
  //    then GetCardUID returns the real UID, encrypted.
  uint8_t realUid[7];
  const bool randomId = (picc.size == 4 && picc.uid[0] == 0x08);
  if (picc.size == 7 && !forceUidKeyPath) {
    memcpy(realUid, picc.uid, 7);
  } else if (randomId || (picc.size == 7 && forceUidKeyPath)) {
    if (!card.authenticateAes(kUidKeyNo, kDevUidKey)) {
      if (card.lastStatus() == kNoResponse) return retry(card.lastError());
      return deny("UID key authentication failed");
    }
    if (!card.getCardUid(realUid)) {
      if (card.lastStatus() == kNoResponse) return retry(card.lastError());
      Serial.printf("      [%s, status %02X]\n", card.lastError(), card.lastStatus());
      return deny("GetCardUID failed");
    }
    Serial.printf("      real UID via key 2 + GetCardUID: %02X%02X%02X%02X%02X%02X%02X%s\n",
                  realUid[0], realUid[1], realUid[2], realUid[3], realUid[4], realUid[5],
                  realUid[6],
                  picc.size == 7 ? (memcmp(realUid, picc.uid, 7) == 0 ? "  (matches anticollision UID)"
                                                                    : "  (MISMATCH!)")
                                 : "  (random ID card)");
  } else {
    return deny("unsupported UID length");
  }
  uint8_t divInput[10];
  memcpy(divInput, realUid, 7);
  memcpy(divInput + 7, kSiteAid, 3);
  uint8_t cardReadKey[16];
  if (!crypto::diversifyAn10922(kDevReadMasterKey, divInput, sizeof divInput, cardReadKey)) {
    return deny("key diversification failed");
  }
  const bool authOk = card.authenticateAes(kReadKeyNo, cardReadKey);
  crypto::wipe(cardReadKey, sizeof cardReadKey);
  if (!authOk) {
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
    if (r.matched.timeProfile) {
      Serial.printf("OPEN  via %s %u, time profile %u  (%lu ms)\n",
                    r.matched.type == kEntryDoor ? "door" : "zone", r.matched.targetId,
                    r.matched.timeProfile, static_cast<unsigned long>(ms));
    } else {
      Serial.printf("OPEN  via %s %u  (%lu ms)\n", r.matched.type == kEntryDoor ? "door" : "zone",
                    r.matched.targetId, static_cast<unsigned long>(ms));
    }
    actuator.engage(kOpenWindowMs);
    Serial.printf("      clutch engaged for %lu ms (pin %d)\n",
                  static_cast<unsigned long>(kOpenWindowMs), OC_ACTUATOR_PIN);
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
  actuator.begin();  // first: make sure the clutch is disengaged
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s (%s) board=%s card-format<=%u\n", FW_VERSION, FW_GIT,
                OC_BOARD_NAME, kCardFormatVersion);
  Serial.printf("Phase 2 bench: door %u (zones 3, 4), site 4F4331, I2C SDA=%d SCL=%d\n",
                kDoorId, OC_I2C_SDA, OC_I2C_SCL);

  const bool selfTest = crypto::selfTest();
  Serial.printf("Crypto self-test (AES-CMAC RFC 4493, AN10922, CRC32): %s\n",
                selfTest ? "PASS" : "FAIL");
  if (!selfTest) {
    Serial.println("ERROR: crypto self-test failed — refusing to operate.");
    return;
  }

  if (!parsePosixTz(kSiteTz, siteTz)) {
    Serial.println("ERROR: invalid site time zone rule");
    return;
  }
  lockClock.begin();
  readerReady = beginReader();
  if (!readerReady) {
    Serial.println("ERROR: ST25R3916 not found — check wiring "
                   "(yellow=SDA, white=SCL, red=5V, black=GND)");
    return;
  }
  Serial.println("Time UNKNOWN until set (type: help). Hold a card to the antenna.\n");
}

void loop() {
  const bool wasEngaged = actuator.engaged();
  actuator.poll();
  if (wasEngaged && !actuator.engaged()) Serial.println("      clutch released\n");
  pollSerial();
  lockClock.tick();
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
