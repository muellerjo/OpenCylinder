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
#include "management.h"
#include "platform/esp32/esp32_clock.h"
#include "platform/esp32/gpio_actuator.h"
#include "platform/esp32/managed_store.h"
#include "platform/esp32/rgb_status_led.h"
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

// Admin application of the test site (spec/admin-card.md) and its read key
// master (public dev test key, diversified per card: UID || admin AID).
constexpr uint8_t kAdminAid[3] = {0x41, 0x43, 0x4F};  // 4F4341, wire order
constexpr uint8_t kAdminReadKeyNo = 1;
constexpr uint8_t kDevAdminReadMasterKey[16] = {0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0xF6, 0x07, 0x18,
                                                0x29, 0x3A, 0x4B, 0x5C, 0x6D, 0x7E, 0x8F, 0x90};
// Site management public key (ECDSA P-256) — dev key from
// examples/hospital/dev_management_key.pem. Production: installed at
// commissioning.
constexpr uint8_t kDevManagementPublicKey[65] = {
    0x04, 0x72, 0x93, 0xC6, 0xEE, 0x31, 0x36, 0x4E, 0xCA, 0x9E, 0xCC, 0xD0, 0x12, 0x95, 0xED,
    0x55, 0x56, 0x74, 0x33, 0xB0, 0xBE, 0x01, 0x79, 0xB3, 0x3E, 0x4E, 0xCE, 0x14, 0x0B, 0x04,
    0x45, 0x3D, 0x8C, 0xA3, 0x26, 0x32, 0x9F, 0xB6, 0x6D, 0x75, 0xF6, 0xAD, 0x83, 0x97, 0xC0,
    0x38, 0xCB, 0xC8, 0xE3, 0x85, 0xF5, 0x22, 0x07, 0x00, 0xAC, 0x49, 0xF6, 0x7A, 0x05, 0xBB,
    0xBA, 0xAA, 0xC5, 0x79, 0xC1};

// Door 4 of examples/hospital/site.json.
constexpr uint16_t kDoorId = 4;
constexpr uint16_t kLockZones[] = {3, 4};
// Factory defaults of the managed configuration (until the first admin
// bundle): blacklist, time profiles and time zone as in the example.
const TimeProfile kDefaultProfiles[] = {
    {1, 0x7F, {{6 * 60, 20 * 60}, {0, 0}}},                          // Day shift, daily
    {2, kMon | kTue | kWed | kThu | kFri | kSat, {{5 * 60, 11 * 60}, {0, 0}}},  // Cleaning
    {3, kMon | kTue | kWed | kThu | kFri, {{7 * 60, 18 * 60}, {0, 0}}},        // Office hours
};
const char* const kDefaultTz = "CET-1CEST,M3.5.0,M10.5.0/3";  // Europe/Berlin

ManagedState managed;     // blacklist, profiles, TZ, last bundle sequence (NVS)
ManagedStore managedStore;
TzRule siteTz;
uint8_t deviceId[8];      // 00 00 + 6-byte eFuse MAC

void setDefaults(ManagedState& m) {
  m = ManagedState{};
  m.blacklist.push_back(BlacklistEntry{2003, 0xFFFFFFFFu});
  m.profiles.assign(kDefaultProfiles, kDefaultProfiles + sizeof kDefaultProfiles / sizeof kDefaultProfiles[0]);
  m.tzRule = kDefaultTz;
}

// The lock's effective configuration for one decision.
LockConfig currentLock(std::vector<uint32_t>& blacklistStorage, bool timeKnown, uint32_t now) {
  blacklistStorage = activeBlacklist(managed, timeKnown, now);
  return LockConfig{kDoorId, kLockZones, sizeof kLockZones / sizeof kLockZones[0],
                    blacklistStorage.data(), blacklistStorage.size(),
                    managed.profiles.data(), managed.profiles.size(), &siteTz};
}

// ------------------------------------------------------------------ hardware
m5::unit::UnitUnified units;
m5::unit::UnitNFC nfcUnit{};          // ST25R3916 over I2C
m5::nfc::NFCLayerA nfcA{nfcUnit};     // ISO14443-A layer
Esp32Clock lockClock;
GpioActuator actuator{OC_ACTUATOR_PIN};
RgbStatusLed led{OC_LED_R, OC_LED_G, OC_LED_B, OC_LED_ACTIVE_HIGH != 0};
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
                   " mgmt | mgmt reset | uidmode [auto|key2] | help");
  } else if (line == "mgmt") {
    Serial.printf("mgmt  bundle sequence %lu, TZ %s\n",
                  static_cast<unsigned long>(managed.lastSequence), managed.tzRule.c_str());
    for (const BlacklistEntry& e : managed.blacklist) {
      Serial.printf("      blacklist %lu until %lu\n", static_cast<unsigned long>(e.credentialId),
                    static_cast<unsigned long>(e.until));
    }
    for (const TimeProfile& p : managed.profiles) {
      Serial.printf("      profile %u days 0x%02X %02u:%02u-%02u:%02u\n", p.id, p.days,
                    p.iv[0].from / 60, p.iv[0].from % 60, p.iv[0].to / 60, p.iv[0].to % 60);
    }
  } else if (line == "mgmt reset") {
    managedStore.clear();
    setDefaults(managed);
    parsePosixTz(managed.tzRule.c_str(), siteTz);
    Serial.println("mgmt  reset to factory defaults (bench only)");
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
  led.show(LedPattern::Deny, 1000);
  return Outcome::Final;
}
Outcome retry(const char* reason) {
  retryReason = reason;
  return Outcome::Retry;
}

// After a failed card operation: retry only if the card did not answer (RF);
// if it answered with an error status, refuse at once and say why.
Outcome cardFailure(DesfireAuth& card, const char* what) {
  if (card.lastStatus() == kNoResponse) return retry(what);
  Serial.printf("      [%s: %s, card status %02X]\n", what, card.lastError(), card.lastStatus());
  return deny(what);
}

// Read `len` bytes of an encrypted file in chunks (DESFire read <= 256 B).
bool readChunked(DesfireAuth& card, uint8_t fileNo, uint32_t offset, uint32_t len,
                 std::vector<uint8_t>& out) {
  out.clear();
  while (len) {
    const uint32_t n = len > DesfireAuth::kMaxReadLength ? DesfireAuth::kMaxReadLength : len;
    std::vector<uint8_t> part;
    if (!card.readDataEncrypted(fileNo, offset, n, part)) return false;
    out.insert(out.end(), part.begin(), part.end());
    offset += n;
    len -= n;
  }
  return true;
}

// Admin tap (spec/admin-card.md §7): verify + apply the signed maintenance
// bundle; admin cards never open the door.
Outcome handleAdminCard(m5::nfc::a::PICC& picc, DesfireAuth& card) {
  Serial.println("ADMIN admin application found");
  if (picc.size != 7) return deny("admin card: random/short UID not supported yet");
  uint8_t divInput[10];
  memcpy(divInput, picc.uid, 7);
  memcpy(divInput + 7, kAdminAid, 3);
  uint8_t key[16];
  if (!crypto::diversifyAn10922(kDevAdminReadMasterKey, divInput, sizeof divInput, key)) {
    return deny("admin key diversification failed");
  }
  const bool authOk = card.authenticateAes(kAdminReadKeyNo, key);
  crypto::wipe(key, sizeof key);
  if (!authOk) {
    if (card.lastStatus() == kNoResponse) return retry(card.lastError());
    return deny("admin card: authentication failed");
  }

  std::vector<uint8_t> hdr, bundle, rest;
  if (!card.readDataEncrypted(0, 0, 16, hdr)) return cardFailure(card, "admin header read");
  if (hdr[0] != 1) return deny("admin card: unknown admin format");
  const uint32_t adminId = hdr[4] | (hdr[5] << 8) | (hdr[6] << 16) | (static_cast<uint32_t>(hdr[7]) << 24);
  if (!readChunked(card, 1, 0, kBundleHeaderSize, bundle)) return cardFailure(card, "bundle header read");
  BundleHeader bh;
  parseBundleHeader(bundle.data(), bundle.size(), bh);
  const uint32_t total = kBundleHeaderSize + bh.payloadLen + kBundleSignatureSize;
  if (total > kMaxBundleSize) return deny("admin card: bundle too large");
  if (!readChunked(card, 1, kBundleHeaderSize, total - kBundleHeaderSize, rest)) {
    return cardFailure(card, "bundle read");
  }
  bundle.insert(bundle.end(), rest.begin(), rest.end());

  uint32_t now = 0;
  const bool timeKnown = lockClock.now(now);
  ApplySummary sum;
  const uint32_t tv0 = millis();
  const BundleStatus st = applyBundle(bundle.data(), bundle.size(), kSiteAid, deviceId,
                                      kDevManagementPublicKey, verifyBundleSignature, timeKnown,
                                      now, managed, sum);
  Serial.printf("ADMIN admin_id %lu, bundle sequence %lu, %u bytes, signature check %lu ms\n",
                static_cast<unsigned long>(adminId), static_cast<unsigned long>(bh.sequence),
                static_cast<unsigned>(bundle.size()), static_cast<unsigned long>(millis() - tv0));

  // Time sync whenever the signature was valid (also for a stale sequence).
  if (st == BundleStatus::Applied || st == BundleStatus::StaleSequence) {
    if (lockClock.trySet(sum.issuedAt)) printTime("ADMIN time set to ", sum.issuedAt);
    else printTime("ADMIN time NOT set (rollback) - high-water mark ", lockClock.highWater());
  }
  if (st != BundleStatus::Applied) {
    Serial.printf("ADMIN bundle not applied: %s\n", toString(st));
    led.show(st == BundleStatus::StaleSequence ? LedPattern::Admin : LedPattern::Deny, 1500);
    return Outcome::Final;
  }
  parsePosixTz(managed.tzRule.c_str(), siteTz);
  managedStore.save(managed);
  Serial.printf("ADMIN applied: blacklist %s%d added, %d removed -> %u entries; profiles %s; TZ %s\n",
                sum.blacklistReplaced ? "replaced, " : "", sum.blacklistAdded, sum.blacklistRemoved,
                static_cast<unsigned>(managed.blacklist.size()),
                sum.profilesReplaced ? "replaced" : "unchanged",
                sum.tzReplaced ? managed.tzRule.c_str() : "unchanged");
  led.show(LedPattern::Admin, 1500);
  return Outcome::Final;
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

  // Admin application present? Then this is an admin card (never opens).
  if (card.selectApplication(kAdminAid)) return handleAdminCard(picc, card);
  if (card.lastStatus() == kNoResponse) return retry(card.lastError());

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
  if (!card.readDataEncrypted(0, 0, kHeaderSize, file0)) {
    return cardFailure(card, "encrypted read of header");
  }
  CardHeader h;
  parseHeader(file0.data(), file0.size(), h);
  Serial.printf("REC   credential %lu, format %u, %u entries\n",
                static_cast<unsigned long>(h.credentialId), h.formatVersion, h.entryCount);
  if (h.validUntil) printTime("      valid until ", h.validUntil);
  else Serial.println("      valid until: no expiry");
  printTime("      issued at   ", h.issuedAt);

  uint32_t now = 0;
  const bool timeKnown = lockClock.now(now);
  std::vector<uint32_t> blacklistNow;
  const LockConfig lock = currentLock(blacklistNow, timeKnown, now);
  const Decision pre = checkHeader(h, lock, timeKnown, now);
  if (pre != Decision::Open) return deny(toString(pre));

  std::vector<uint8_t> file1;
  std::vector<AccessEntry> entries;
  if (h.entryCount) {
    if (!card.readDataEncrypted(1, 0, h.entryCount * kEntrySize, file1)) {
      return cardFailure(card, "encrypted read of access list");
    }
    parseEntries(file1.data(), file1.size(), h.entryCount, entries);
  }
  const Result r = decide(h, entries, lock, timeKnown, now);
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
    led.show(LedPattern::Open, kOpenWindowMs);
    Serial.printf("      clutch engaged for %lu ms (pin %d)\n",
                  static_cast<unsigned long>(kOpenWindowMs), OC_ACTUATOR_PIN);
  } else {
    Serial.printf("DENY  %s  (%lu ms)\n", toString(r.decision), static_cast<unsigned long>(ms));
    led.show(LedPattern::Deny, 1000);
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
    led.show(LedPattern::Retry);
    led.poll();
    nfcA.deactivate();
    delay(kRetryDelayMs);
  }
  deny("card not readable - hold it flat on the reader");
  led.show(LedPattern::Unreadable, 1500);
}

}  // namespace

void setup() {
  actuator.begin();  // first: make sure the clutch is disengaged
  led.begin();
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s+%s.%s (%s) card-format<=%u\n", FW_VERSION, OC_BOARD_NAME,
                OC_VARIANT_NAME, FW_GIT, kCardFormatVersion);
  Serial.printf("Phase 2 bench: door %u (zones 3, 4), site 4F4331, I2C SDA=%d SCL=%d\n",
                kDoorId, OC_I2C_SDA, OC_I2C_SCL);

  const bool selfTest = crypto::selfTest();
  Serial.printf("Crypto self-test (AES-CMAC RFC 4493, AN10922, CRC32): %s\n",
                selfTest ? "PASS" : "FAIL");
  if (!selfTest) {
    Serial.println("ERROR: crypto self-test failed — refusing to operate.");
    led.show(LedPattern::Error);
    return;
  }

  if (!managedStore.load(managed)) {
    setDefaults(managed);
    Serial.println("Managed config: factory defaults (no admin bundle applied yet)");
  } else {
    Serial.printf("Managed config: bundle sequence %lu, %u blacklist entries, %u profiles\n",
                  static_cast<unsigned long>(managed.lastSequence),
                  static_cast<unsigned>(managed.blacklist.size()),
                  static_cast<unsigned>(managed.profiles.size()));
  }
  const uint64_t mac = ESP.getEfuseMac();
  memset(deviceId, 0, sizeof deviceId);
  for (int i = 0; i < 6; ++i) deviceId[2 + i] = static_cast<uint8_t>(mac >> (8 * (5 - i)));
  Serial.printf("Device ID %02X%02X%02X%02X%02X%02X%02X%02X\n", deviceId[0], deviceId[1],
                deviceId[2], deviceId[3], deviceId[4], deviceId[5], deviceId[6], deviceId[7]);
  if (!parsePosixTz(managed.tzRule.c_str(), siteTz)) {
    Serial.println("ERROR: invalid site time zone rule");
    led.show(LedPattern::Error);
    return;
  }
  lockClock.begin();
  readerReady = beginReader();
  if (!readerReady) {
    Serial.println("ERROR: ST25R3916 not found — check wiring "
                   "(yellow=SDA, white=SCL, red=5V, black=GND)");
    led.show(LedPattern::Error);
    return;
  }
  Serial.println("Time UNKNOWN until set (type: help). Hold a card to the antenna.\n");
}

void loop() {
  const bool wasEngaged = actuator.engaged();
  actuator.poll();
  if (wasEngaged && !actuator.engaged()) Serial.println("      clutch released\n");
  uint32_t nowT;
  led.setIdle(lockClock.now(nowT) ? LedPattern::Off : LedPattern::TimeUnknown);
  led.poll();
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
