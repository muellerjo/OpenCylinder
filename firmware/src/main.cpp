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
#include <bootloader_random.h>

#include <M5UnitUnified.h>
#include <M5UnitUnifiedNFC.h>

#include <string>
#include <vector>

#include "access_decision.h"
#include "clock.h"
#include "desfire_auth.h"
#include "desfire_crypto.h"
#include "eventlog.h"
#include "commissioning.h"
#include "management.h"
#include "platform/esp32/esp32_clock.h"
#include "platform/esp32/gpio_actuator.h"
#include "platform/esp32/device_identity.h"
#include "platform/esp32/managed_store.h"
#include "platform/esp32/site_store.h"
#include "platform/esp32/nvs_event_store.h"
#include "platform/esp32/rgb_status_led.h"
#include "platform/esp32/m5_desfire_transport.h"
#include "version.h"

namespace {

using namespace opencylinder;

// ---------------------------------------------------------------- bench lock
// Site AID 4F4331 (test site), LSB-first as sent on the wire.
constexpr uint8_t kDevSiteAid[3] = {0x31, 0x43, 0x4F};
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
constexpr uint8_t kDevAdminAid[3] = {0x41, 0x43, 0x4F};  // 4F4341, wire order
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
constexpr uint16_t kDevDoorId = 4;
constexpr uint16_t kDevLockZones[] = {3, 4};
// Factory defaults of the managed configuration (until the first admin
// bundle): blacklist, time profiles and time zone as in the example.
const TimeProfile kDefaultProfiles[] = {
    {1, 0x7F, {{6 * 60, 20 * 60}, {0, 0}}},                          // Day shift, daily
    {2, kMon | kTue | kWed | kThu | kFri | kSat, {{5 * 60, 11 * 60}, {0, 0}}},  // Cleaning
    {3, kMon | kTue | kWed | kThu | kFri, {{7 * 60, 18 * 60}, {0, 0}}},        // Office hours
};
const char* const kDefaultTz = "CET-1CEST,M3.5.0,M10.5.0/3";  // Europe/Berlin

// Site configuration — received at commissioning (spec/admin-card.md §5.3),
// persisted in NVS. Valid only in state OWNED.
SiteConfig site;
SiteStore siteStore;
bool siteFromCommissioning = false;  // false = built-in dev site (bench)
void printSite();

// Bench: the built-in dev test site (= what the examples' commissioning card
// carries). Removed once commissioning is the only way in.
void loadDevSite(SiteConfig& c) {
  memcpy(c.siteAid, kDevSiteAid, 3);
  memcpy(c.adminAid, kDevAdminAid, 3);
  memcpy(c.readMasterKey, kDevReadMasterKey, 16);
  memcpy(c.uidKey, kDevUidKey, 16);
  memcpy(c.adminReadMasterKey, kDevAdminReadMasterKey, 16);
  memcpy(c.managementPublicKey, kDevManagementPublicKey, 65);
  c.doorId = kDevDoorId;
  c.zones.assign(kDevLockZones, kDevLockZones + sizeof kDevLockZones / sizeof kDevLockZones[0]);
}

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
  return LockConfig{site.doorId, site.zones.data(), site.zones.size(),
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
NvsEventStore eventStore;
DeviceIdentity identity;

// Lock state — spec/admin-card.md §5.1. FACTORY opens nothing.
enum class LockState : uint8_t { Factory = 0, Owned = 1 };
LockState lockState = LockState::Factory;
Preferences statePrefs;

void setLockState(LockState s) {
  lockState = s;
  statePrefs.putUChar("state", static_cast<uint8_t>(s));
}
const char* lockStateName() { return lockState == LockState::Owned ? "OWNED" : "FACTORY"; }

// Sequence floor (kept across decommission, like the device key pair): a
// commissioning bundle must be newer than the last decommission, so old
// commissioning / decommission cards cannot be replayed in a loop.
uint32_t sequenceFloor() { return statePrefs.getUInt("seqfloor", 0); }
void raiseSequenceFloor(uint32_t s) {
  if (s > sequenceFloor()) statePrefs.putUInt("seqfloor", s);
}
EventLog eventLog{eventStore, 64};
uint32_t tapCredential = 0;   // credential of the card being evaluated (0 = not read yet)

uint32_t timeOrZero() {
  uint32_t t = 0;
  return lockClock.now(t) ? t : 0;
}
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

// ------------------------------------------------------------ event log output
const char* denyReason(uint8_t code) {
  switch (code) {
    case deny_code::kNotDesfire:     return "not a DESFire card";
    case deny_code::kNoSiteApp:      return "no application for this site";
    case deny_code::kAuthFailed:     return "authentication failed";
    case deny_code::kUnreadable:     return "card not readable";
    case deny_code::kCardError:      return "card error";
    case deny_code::kUidUnsupported: return "UID not supported";
    case deny_code::kNotCommissioned: return "lock not commissioned";
    case deny_code::kOther:          return "other";
    default:
      return code < 16 ? toString(static_cast<Decision>(code)) : "?";
  }
}

void printEvent(const Event& e) {
  char when[40];
  if (e.time) {
    const UtcDateTime d = toUtc(e.time);
    snprintf(when, sizeof when, "%04u-%02u-%02u %02u:%02u:%02u UTC", d.year, d.month, d.day,
             d.hour, d.minute, d.second);
  } else {
    snprintf(when, sizeof when, "%-23s", "(time unknown)");
  }
  Serial.printf("  #%-5lu %s  %-5s ", static_cast<unsigned long>(e.number), when,
                eventTypeName(e.type));
  switch (e.type) {
    case EventType::Open:
      Serial.printf("credential %lu via %s %u\n", static_cast<unsigned long>(e.credential),
                    e.code == kEntryDoor ? "door" : "zone", e.target);
      break;
    case EventType::Deny:
      Serial.printf("credential %lu: %s\n", static_cast<unsigned long>(e.credential),
                    denyReason(e.code));
      break;
    case EventType::Admin:
      Serial.printf("admin_id %u, bundle sequence %lu: %s\n", e.target,
                    static_cast<unsigned long>(e.credential),
                    toString(static_cast<BundleStatus>(e.code)));
      break;
    case EventType::TimeSet:
      Serial.printf("set via %s\n", e.code == 2 ? "admin bundle" : "serial");
      break;
    case EventType::Boot:
      Serial.printf("reset reason %u\n", e.code);
      break;
    case EventType::Commission:
      Serial.printf("door %u, bundle sequence %lu: %s\n", e.target,
                    static_cast<unsigned long>(e.credential),
                    e.code == 0xFE ? "older than last decommission"
                                   : toString(static_cast<CommissionStatus>(e.code)));
      break;
    case EventType::Decommission:
      Serial.printf("bundle sequence %lu -> FACTORY\n", static_cast<unsigned long>(e.credential));
      break;
    case EventType::Reassign:
      Serial.printf("new door %u, bundle sequence %lu\n", e.target,
                    static_cast<unsigned long>(e.credential));
      break;
    case EventType::Identify:
      Serial.printf("identity written (state %s)\n", e.code ? "OWNED" : "FACTORY");
      break;
    case EventType::Bench:
      Serial.printf("%s\n", e.code == 1 ? "time reset-hwm" : e.code == 2 ? "mgmt reset"
                           : e.code == 3 ? "log clear" : e.code == 4 ? "state -> FACTORY"
                                                                     : "state -> OWNED (dev site)");
      break;
  }
}

// ------------------------------------------------------------ serial commands
void handleCommand(const std::string& line) {
  if (line == "help") {
    Serial.println("commands: time | time <unix-utc-seconds> | time reset-hwm |"
                   " mgmt | mgmt reset | log | log clear | id | state factory|owned |"
                   " uidmode [auto|key2] | help");
  } else if (line == "id") {
    char qr[100];
    identity.qrText(qr, sizeof qr);
    Serial.printf("id    state %s, %s\n", lockStateName(), qr);
#if defined(OC_DEV_BUILTIN_SITE)
  } else if (line == "state factory" || line == "state owned") {
    // Bench only: simulate decommission / commission with the built-in site.
    managedStore.clear();
    setDefaults(managed);
    parsePosixTz(managed.tzRule.c_str(), siteTz);
    const bool owned = (line == "state owned");
    siteStore.clear();
    if (owned) loadDevSite(site);  // built-in dev site, not stored
    siteFromCommissioning = false;
    setLockState(owned ? LockState::Owned : LockState::Factory);
    eventLog.add(EventType::Bench, owned ? 5 : 4, timeOrZero());
    Serial.printf("state %s (bench; site data reset, device key pair kept)\n", lockStateName());
#endif
  } else if (line == "log") {
    const std::vector<Event> ev = eventLog.entries();
    Serial.printf("log   %lu events total, showing the last %u\n",
                  static_cast<unsigned long>(eventLog.total()), static_cast<unsigned>(ev.size()));
    for (const Event& e : ev) printEvent(e);
  } else if (line == "log clear") {
    eventLog.clear();
    eventLog.add(EventType::Bench, 3, timeOrZero());
    Serial.println("log   cleared (bench only)");
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
    eventLog.add(EventType::Bench, 2, timeOrZero());
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
    eventLog.add(EventType::Bench, 1, 0);
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
    eventLog.add(EventType::TimeSet, 1, static_cast<uint32_t>(v), static_cast<uint32_t>(v));
  } else if (!line.empty()) {
    Serial.printf("unknown command '%s' (try: help)\n", line.c_str());
  }
}

// Minimal line editor: the serial monitor sends every key raw and does not
// echo, so echo printable characters and handle Backspace / Delete here.
void pollSerial() {
  static uint8_t escState = 0;  // 0 = normal, 1 = after ESC, 2 = inside ESC [ ... sequence
  // While a Linux host (re)opens the port it may briefly echo our own boot
  // output back to us: ignore everything received in the first 3 s.
  constexpr uint32_t kIgnoreInputAfterBootMs = 3000;
  if (millis() < kIgnoreInputAfterBootMs) {
    while (Serial.available()) Serial.read();
    serialLine.clear();
    return;
  }
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    // Swallow ANSI escape sequences (arrow keys etc.): ESC [ <params> <final byte>
    if (escState == 1) { escState = (c == '[') ? 2 : 0; continue; }
    if (escState == 2) { if (c >= 0x40 && c <= 0x7E) escState = 0; continue; }
    if (c == 0x1B) { escState = 1; continue; }
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

Outcome deny(const char* reason, uint8_t code = deny_code::kOther) {
  eventLog.add(EventType::Deny, code, timeOrZero(), tapCredential);
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
  return deny(what, deny_code::kCardError);
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
  if (picc.size != 7) return deny("admin card: random/short UID not supported yet", deny_code::kUidUnsupported);
  uint8_t divInput[10];
  memcpy(divInput, picc.uid, 7);
  memcpy(divInput + 7, site.adminAid, 3);
  uint8_t key[16];
  if (!crypto::diversifyAn10922(site.adminReadMasterKey, divInput, sizeof divInput, key)) {
    return deny("admin key diversification failed");
  }
  const bool authOk = card.authenticateAes(kAdminReadKeyNo, key);
  crypto::wipe(key, sizeof key);
  if (!authOk) {
    if (card.lastStatus() == kNoResponse) return retry(card.lastError());
    return deny("admin card: authentication failed", deny_code::kAuthFailed);
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
  const BundleStatus st = applyBundle(bundle.data(), bundle.size(), site.siteAid, deviceId,
                                      site.managementPublicKey, verifyBundleSignature, timeKnown,
                                      now, managed, sum);
  Serial.printf("ADMIN admin_id %lu, bundle sequence %lu, %u bytes, signature check %lu ms\n",
                static_cast<unsigned long>(adminId), static_cast<unsigned long>(bh.sequence),
                static_cast<unsigned>(bundle.size()), static_cast<unsigned long>(millis() - tv0));

  // Time sync whenever the signature was valid (also for a stale sequence).
  if (st == BundleStatus::Applied || st == BundleStatus::StaleSequence) {
    if (lockClock.trySet(sum.issuedAt)) {
      printTime("ADMIN time set to ", sum.issuedAt);
      eventLog.add(EventType::TimeSet, 2, sum.issuedAt, sum.issuedAt);
    }
    else printTime("ADMIN time NOT set (rollback) - high-water mark ", lockClock.highWater());
  }
  if (st != BundleStatus::Applied) {
    Serial.printf("ADMIN bundle not applied: %s\n", toString(st));
    eventLog.add(EventType::Admin, static_cast<uint8_t>(st), timeOrZero(), bh.sequence,
                 static_cast<uint16_t>(adminId));
    led.show(st == BundleStatus::StaleSequence ? LedPattern::Admin : LedPattern::Deny, 1500);
    return Outcome::Final;
  }
  if (sum.decommission) {
    // spec §5.4: forget the site (keys, door, zones, managed config) -> FACTORY.
    // Kept: device key pair, event log, sequence floor.
    raiseSequenceFloor(sum.sequence);
    siteStore.clear();
    managedStore.clear();
    setDefaults(managed);
    managed.blacklist.clear();
    site = SiteConfig{};
    siteFromCommissioning = false;
    setLockState(LockState::Factory);
    eventLog.add(EventType::Decommission, 0, timeOrZero(), sum.sequence);
    Serial.println("DECOM signed decommission for this lock -> FACTORY (site data wiped, device key kept)");
    led.show(LedPattern::Admin, 2000);
    return Outcome::Final;
  }
  if (sum.reassigned) {
    site.doorId = sum.doorId;
    site.zones = sum.zones;
    siteStore.save(site);
    siteFromCommissioning = true;
    eventLog.add(EventType::Reassign, 0, timeOrZero(), sum.sequence, site.doorId);
    Serial.print("REASS reassigned: ");
    printSite();
  }
  parsePosixTz(managed.tzRule.c_str(), siteTz);
  managedStore.save(managed);
  Serial.printf("ADMIN applied: blacklist %s%d added, %d removed -> %u entries; profiles %s; TZ %s\n",
                sum.blacklistReplaced ? "replaced, " : "", sum.blacklistAdded, sum.blacklistRemoved,
                static_cast<unsigned>(managed.blacklist.size()),
                sum.profilesReplaced ? "replaced" : "unchanged",
                sum.tzReplaced ? managed.tzRule.c_str() : "unchanged");
  eventLog.add(EventType::Admin, static_cast<uint8_t>(st), timeOrZero(), bh.sequence,
               static_cast<uint16_t>(adminId));
  led.show(LedPattern::Admin, 1500);
  return Outcome::Final;
}

// Identify card (spec/admin-card.md §5.5): write our public identity into
// the card's free-access file. Works in every state; never opens; the lock
// takes no instructions from this card.
constexpr uint8_t kIdentifyAid[3] = {0x49, 0x43, 0x4F};  // 4F4349, wire order

void parseVersion(const char* v, uint8_t out[3]) {
  unsigned a = 0, b = 0, c = 0;
  sscanf(v, "%u.%u.%u", &a, &b, &c);
  out[0] = static_cast<uint8_t>(a);
  out[1] = static_cast<uint8_t>(b);
  out[2] = static_cast<uint8_t>(c);
}

Outcome handleIdentifyCard(DesfireAuth& card) {
  uint8_t rec[64] = {0};
  rec[0] = 1;                                         // format
  rec[1] = static_cast<uint8_t>(lockState);           // 0 FACTORY, 1 OWNED
  memcpy(rec + 2, deviceId, 8);
  memcpy(rec + 10, identity.publicKey(), 33);
  parseVersion(FW_VERSION, rec + 43);
  if (lockState == LockState::Owned) {
    memcpy(rec + 46, site.siteAid, 3);
    rec[49] = static_cast<uint8_t>(site.doorId);
    rec[50] = static_cast<uint8_t>(site.doorId >> 8);
  }
  if (!card.writeDataPlain(0, 0, rec, sizeof rec)) return cardFailure(card, "identify write");
  char qr[100];
  identity.qrText(qr, sizeof qr);
  Serial.printf("IDENT identity written to identify card (state %s)\n      %s\n",
                lockStateName(), qr);
  eventLog.add(EventType::Identify, static_cast<uint8_t>(lockState), timeOrZero());
  led.show(LedPattern::Admin, 1500);
  return Outcome::Final;
}

// ------------------------------------------------------------ commissioning
// Commissioning card (spec/admin-card.md §5.3): own application, one file
// with FREE read access holding the commissioning bundle — a blank lock has
// no keys; the content protects itself (ECIES to this lock + signature).
constexpr uint8_t kCommissioningAid[3] = {0x4B, 0x43, 0x4F};  // 4F434B, wire order

void printSite() {
  Serial.printf("Site %02X%02X%02X, admin app %02X%02X%02X, door %u, zones",
                site.siteAid[2], site.siteAid[1], site.siteAid[0], site.adminAid[2],
                site.adminAid[1], site.adminAid[0], site.doorId);
  for (uint16_t z : site.zones) Serial.printf(" %u", z);
  Serial.println(siteFromCommissioning ? "  (commissioned)" : "  (built-in dev site)");
}

bool deviceEcdh(const uint8_t peer[65], uint8_t shared[32]) { return identity.ecdh(peer, shared); }

bool readPlainChunked(DesfireAuth& card, uint8_t fileNo, uint32_t offset, uint32_t len,
                      std::vector<uint8_t>& out) {
  out.clear();
  while (len) {
    const uint32_t n = len > DesfireAuth::kMaxReadLength ? DesfireAuth::kMaxReadLength : len;
    std::vector<uint8_t> part;
    if (!card.readDataPlain(fileNo, offset, n, part)) return false;
    out.insert(out.end(), part.begin(), part.end());
    offset += n;
    len -= n;
  }
  return true;
}

Outcome handleCommissioningCard(DesfireAuth& card) {
  Serial.println("COMM  commissioning card found");
  std::vector<uint8_t> bundle, rest;
  if (!readPlainChunked(card, 0, 0, kBundleHeaderSize, bundle)) {
    return cardFailure(card, "commissioning bundle header read");
  }
  BundleHeader bh;
  parseBundleHeader(bundle.data(), bundle.size(), bh);
  const uint32_t total = kBundleHeaderSize + bh.payloadLen + kBundleSignatureSize;
  if (total > kMaxBundleSize) return deny("commissioning bundle too large");
  if (!readPlainChunked(card, 0, kBundleHeaderSize, total - kBundleHeaderSize, rest)) {
    return cardFailure(card, "commissioning bundle read");
  }
  bundle.insert(bundle.end(), rest.begin(), rest.end());

  if (bh.sequence <= sequenceFloor()) {
    Serial.printf("COMM  bundle sequence %lu not newer than the last decommission (%lu) - refused\n",
                  static_cast<unsigned long>(bh.sequence), static_cast<unsigned long>(sequenceFloor()));
    eventLog.add(EventType::Commission, 0xFE, timeOrZero(), bh.sequence);
    led.show(LedPattern::Deny, 1500);
    return Outcome::Final;
  }
  const uint32_t t0 = millis();
  SiteConfig cfg;
  const CommissionStatus cs =
      openCommissioningBundle(bundle.data(), bundle.size(), deviceId, deviceEcdh, cfg);
  Serial.printf("COMM  bundle sequence %lu, %u bytes, decrypt + verify %lu ms: %s\n",
                static_cast<unsigned long>(bh.sequence), static_cast<unsigned>(bundle.size()),
                static_cast<unsigned long>(millis() - t0), toString(cs));
  if (cs != CommissionStatus::Ok) {
    eventLog.add(EventType::Commission, static_cast<uint8_t>(cs), timeOrZero(), bh.sequence);
    led.show(LedPattern::Deny, 1500);
    return Outcome::Final;
  }

  // Commit: site configuration, fresh managed state, then the bundle's other
  // records (TZ, profiles, blacklist, sequence) through the normal path.
  site = cfg;
  siteStore.save(site);
  siteFromCommissioning = true;
  managed = ManagedState{};
  managed.tzRule = "UTC0";
  uint32_t now = 0;
  const bool timeKnown = lockClock.now(now);
  ApplySummary sum;
  const BundleStatus st = applyBundle(bundle.data(), bundle.size(), site.siteAid, deviceId,
                                      site.managementPublicKey, verifyBundleSignature, timeKnown,
                                      now, managed, sum);
  if (st == BundleStatus::Applied || st == BundleStatus::StaleSequence) {
    if (lockClock.trySet(bh.issuedAt)) printTime("COMM  time set to ", bh.issuedAt);
  }
  parsePosixTz(managed.tzRule.c_str(), siteTz);
  managedStore.save(managed);
  setLockState(LockState::Owned);
  eventLog.add(EventType::Commission, static_cast<uint8_t>(cs), timeOrZero(), bh.sequence,
               site.doorId);
  Serial.printf("COMM  commissioned -> OWNED (maintenance records: %s)\n      ", toString(st));
  printSite();
  led.show(LedPattern::Admin, 2000);
  return Outcome::Final;
}

Outcome evaluateCard(m5::nfc::a::PICC& picc) {
  const uint32_t t0 = millis();
  tapCredential = 0;
  if (!picc.isMifareDESFire()) return deny("not a DESFire card", deny_code::kNotDesfire);

  // Fresh activation incl. RATS -> ISO-DEP session sized from the card's ATS.
  if (!nfcA.reactivate(picc)) return retry("ISO-DEP activation failed");
  auto* dep = nfcA.isoDEP();
  if (!dep) return deny("no ISO-DEP context");
  M5DesfireTransport transport{*dep};
  DesfireAuth card{transport};

  // Identify card? Works in every state (also FACTORY).
  if (card.selectApplication(kIdentifyAid)) return handleIdentifyCard(card);
  if (card.lastStatus() == kNoResponse) return retry(card.lastError());

  // Commissioning card? Only a FACTORY lock accepts one.
  if (card.selectApplication(kCommissioningAid)) {
    if (lockState == LockState::Owned) {
      Serial.println("COMM  lock already commissioned - commissioning card ignored");
      led.show(LedPattern::Deny, 1000);
      return Outcome::Final;
    }
    return handleCommissioningCard(card);
  }
  if (card.lastStatus() == kNoResponse) return retry(card.lastError());

  if (lockState == LockState::Factory) {
    // FACTORY opens nothing.
    return deny("lock not commissioned (FACTORY)", deny_code::kNotCommissioned);
  }

  // Admin application present? Then this is an admin card (never opens).
  if (card.selectApplication(site.adminAid)) return handleAdminCard(picc, card);
  if (card.lastStatus() == kNoResponse) return retry(card.lastError());

  if (!card.selectApplication(site.siteAid)) {
    if (card.lastStatus() == kStatusNoSuchApp) return deny("no application for this site (4F4331)", deny_code::kNoSiteApp);
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
    if (!card.authenticateAes(kUidKeyNo, site.uidKey)) {
      if (card.lastStatus() == kNoResponse) return retry(card.lastError());
      return deny("UID key authentication failed", deny_code::kAuthFailed);
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
    return deny("unsupported UID length", deny_code::kUidUnsupported);
  }
  uint8_t divInput[10];
  memcpy(divInput, realUid, 7);
  memcpy(divInput + 7, site.siteAid, 3);
  uint8_t cardReadKey[16];
  if (!crypto::diversifyAn10922(site.readMasterKey, divInput, sizeof divInput, cardReadKey)) {
    return deny("key diversification failed");
  }
  const bool authOk = card.authenticateAes(kReadKeyNo, cardReadKey);
  crypto::wipe(cardReadKey, sizeof cardReadKey);
  if (!authOk) {
    if (card.lastStatus() == kStatusAuthError) {
      return deny("authentication failed (wrong key or cloned card)", deny_code::kAuthFailed);
    }
    if (card.lastStatus() == kNoResponse) return retry(card.lastError());
    Serial.printf("      [%s, status %02X]\n", card.lastError(), card.lastStatus());
    return deny("authentication failed", deny_code::kAuthFailed);
  }

  std::vector<uint8_t> file0;
  if (!card.readDataEncrypted(0, 0, kHeaderSize, file0)) {
    return cardFailure(card, "encrypted read of header");
  }
  CardHeader h;
  parseHeader(file0.data(), file0.size(), h);
  tapCredential = h.credentialId;
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
  if (pre != Decision::Open) return deny(toString(pre), static_cast<uint8_t>(pre));

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
    eventLog.add(EventType::Open, r.matched.type, timeOrZero(), h.credentialId, r.matched.targetId);
    led.show(LedPattern::Open, kOpenWindowMs);
    Serial.printf("      clutch engaged for %lu ms (pin %d)\n",
                  static_cast<unsigned long>(kOpenWindowMs), OC_ACTUATOR_PIN);
  } else {
    Serial.printf("DENY  %s  (%lu ms)\n", toString(r.decision), static_cast<unsigned long>(ms));
    eventLog.add(EventType::Deny, static_cast<uint8_t>(r.decision), timeOrZero(), h.credentialId);
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
  deny("card not readable - hold it flat on the reader", deny_code::kUnreadable);
  led.show(LedPattern::Unreadable, 1500);
}

}  // namespace

void setup() {
  actuator.begin();  // first: make sure the clutch is disengaged
  led.begin();
  // Offline build = no WiFi/BT, so the hardware RNG needs the SAR-ADC noise
  // entropy source for true random numbers (key generation, RndA). The ADC is
  // not used otherwise.
  bootloader_random_enable();
  Serial.begin(115200);
  delay(1500);  // give USB-CDC time to enumerate so the banner isn't lost

  Serial.printf("OpenCylinder fw %s+%s.%s (%s) card-format<=%u\n", FW_VERSION, OC_BOARD_NAME,
                OC_VARIANT_NAME, FW_GIT, kCardFormatVersion);
  Serial.printf("Bench lock, I2C SDA=%d SCL=%d\n", OC_I2C_SDA, OC_I2C_SCL);

  const bool selfTest = crypto::selfTest() && commissioningSelfTest();
  Serial.printf("Crypto self-test (AES-CMAC RFC 4493, AN10922, CRC32, HKDF RFC 5869): %s\n",
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
  // getEfuseMac() holds the MAC little-endian (first MAC byte in the lowest
  // byte); the device ID shows it in the usual order (matches esptool / USB).
  for (int i = 0; i < 6; ++i) deviceId[2 + i] = static_cast<uint8_t>(mac >> (8 * i));
  Serial.printf("Device ID %02X%02X%02X%02X%02X%02X%02X%02X\n", deviceId[0], deviceId[1],
                deviceId[2], deviceId[3], deviceId[4], deviceId[5], deviceId[6], deviceId[7]);
  bool generated = false;
  if (!identity.begin(deviceId, generated)) {
    Serial.println("ERROR: device key pair could not be created/loaded");
    led.show(LedPattern::Error);
    return;
  }
  char qr[100];
  identity.qrText(qr, sizeof qr);
  Serial.printf("Device key pair %s; QR: %s\n", generated ? "GENERATED (first boot)" : "loaded", qr);

  statePrefs.begin("oc-state", false);
#if defined(OC_DEV_BUILTIN_SITE)
  // Bench: until commissioning exists, a lock without stored state starts
  // OWNED by the built-in dev test site.
  lockState = static_cast<LockState>(statePrefs.getUChar("state", static_cast<uint8_t>(LockState::Owned)));
#else
  lockState = static_cast<LockState>(statePrefs.getUChar("state", static_cast<uint8_t>(LockState::Factory)));
#endif
  siteStore.begin();
  siteFromCommissioning = (lockState == LockState::Owned) && siteStore.load(site);
  if (lockState == LockState::Owned && !siteFromCommissioning) {
#if defined(OC_DEV_BUILTIN_SITE)
    loadDevSite(site);  // bench: OWNED by the built-in dev test site
#else
    lockState = LockState::Factory;  // no site configuration -> blank
#endif
  }
  Serial.printf("Lock state: %s\n", lockStateName());
  if (lockState == LockState::Owned) printSite();
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
  eventStore.begin();
  eventLog.begin();
  eventLog.add(EventType::Boot, static_cast<uint8_t>(esp_reset_reason()), 0);
  Serial.printf("Event log: %lu events so far (keeps the last %u)\n",
                static_cast<unsigned long>(eventLog.total()),
                static_cast<unsigned>(eventLog.capacity()));
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
