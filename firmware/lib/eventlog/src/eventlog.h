#pragma once
// Local event log of the lock — spec/admin-card.md §6 (v1: local only).
// Fixed 16-byte records in a ring buffer; storage behind IEventStore so the
// platform decides where it lives (NVS on the ESP32 dev board, a dedicated
// flash area on the production lock). Portable, host-testable.
//
// Privacy: entries contain credential IDs — who opened which door when.
// Access to the log and its retention follow the site's privacy rules.

#include <cstddef>
#include <cstdint>
#include <vector>

namespace opencylinder {

enum class EventType : uint8_t {
  Boot = 1,
  Open = 2,
  Deny = 3,
  Admin = 4,     // code = BundleStatus, credential = bundle sequence, target = admin_id
  TimeSet = 5,   // code = source (1 serial, 2 admin bundle), credential = new time
  Bench = 6,     // bench-only actions (code: 1 time reset-hwm, 2 mgmt reset, 3 log clear)
};

// Deny codes 0..15 = opencylinder::Decision values; extra codes from 32 on.
namespace deny_code {
constexpr uint8_t kNotDesfire = 32;
constexpr uint8_t kNoSiteApp = 33;
constexpr uint8_t kAuthFailed = 34;
constexpr uint8_t kUnreadable = 35;
constexpr uint8_t kCardError = 36;
constexpr uint8_t kUidUnsupported = 37;
constexpr uint8_t kOther = 63;
}  // namespace deny_code

struct Event {
  uint32_t time;          // unsigned Unix UTC, 0 = time unknown
  uint32_t number;        // monotonic event number (gaps = lost entries)
  EventType type;
  uint8_t code;
  uint16_t target;        // matched door/zone ID (open), admin_id (admin), ...
  uint32_t credential;    // credential ID, bundle sequence or time value
};

constexpr size_t kEventSize = 16;
void encodeEvent(const Event& e, uint8_t out[kEventSize]);
bool decodeEvent(const uint8_t in[kEventSize], Event& e);

class IEventStore {
 public:
  virtual ~IEventStore() = default;
  virtual bool readSlot(size_t slot, uint8_t out[kEventSize]) = 0;
  virtual void writeSlot(size_t slot, const uint8_t in[kEventSize]) = 0;
  virtual uint32_t readCount() = 0;          // events ever written (0 = empty)
  virtual void writeCount(uint32_t n) = 0;
  virtual void clear() = 0;
};

class EventLog {
 public:
  EventLog(IEventStore& store, size_t capacity) : store_(store), capacity_(capacity) {}

  void begin() { count_ = store_.readCount(); }

  // Append; `number` is assigned here.
  void add(EventType type, uint8_t code, uint32_t time, uint32_t credential = 0,
           uint16_t target = 0);

  // Entries oldest -> newest (at most `capacity`).
  std::vector<Event> entries();

  uint32_t total() const { return count_; }
  size_t capacity() const { return capacity_; }
  void clear();

 private:
  IEventStore& store_;
  size_t capacity_;
  uint32_t count_ = 0;
};

const char* eventTypeName(EventType t);

}  // namespace opencylinder
