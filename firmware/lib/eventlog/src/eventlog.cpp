#include "eventlog.h"

namespace opencylinder {
namespace {

void put32(uint8_t* p, uint32_t v) {
  for (int i = 0; i < 4; ++i) p[i] = static_cast<uint8_t>(v >> (8 * i));
}
uint32_t get32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

}  // namespace

// Layout (little-endian): time 4 | number 4 | type 1 | code 1 | target 2 | credential 4
void encodeEvent(const Event& e, uint8_t out[kEventSize]) {
  put32(out, e.time);
  put32(out + 4, e.number);
  out[8] = static_cast<uint8_t>(e.type);
  out[9] = e.code;
  out[10] = static_cast<uint8_t>(e.target);
  out[11] = static_cast<uint8_t>(e.target >> 8);
  put32(out + 12, e.credential);
}

bool decodeEvent(const uint8_t in[kEventSize], Event& e) {
  e.time = get32(in);
  e.number = get32(in + 4);
  e.type = static_cast<EventType>(in[8]);
  e.code = in[9];
  e.target = static_cast<uint16_t>(in[10] | (in[11] << 8));
  e.credential = get32(in + 12);
  return in[8] >= static_cast<uint8_t>(EventType::Boot) &&
         in[8] <= static_cast<uint8_t>(EventType::Commission);
}

void EventLog::add(EventType type, uint8_t code, uint32_t time, uint32_t credential,
                   uint16_t target) {
  Event e{time, count_ + 1, type, code, target, credential};
  uint8_t raw[kEventSize];
  encodeEvent(e, raw);
  store_.writeSlot(count_ % capacity_, raw);
  ++count_;
  store_.writeCount(count_);  // written after the slot: a crash loses at most this entry
}

std::vector<Event> EventLog::entries() {
  std::vector<Event> out;
  const uint32_t n = count_ < capacity_ ? count_ : static_cast<uint32_t>(capacity_);
  const uint32_t first = count_ - n;
  for (uint32_t i = first; i < count_; ++i) {
    uint8_t raw[kEventSize];
    Event e;
    if (store_.readSlot(i % capacity_, raw) && decodeEvent(raw, e)) out.push_back(e);
  }
  return out;
}

void EventLog::clear() {
  store_.clear();
  count_ = 0;
}

const char* eventTypeName(EventType t) {
  switch (t) {
    case EventType::Boot:    return "BOOT";
    case EventType::Open:    return "OPEN";
    case EventType::Deny:    return "DENY";
    case EventType::Admin:   return "ADMIN";
    case EventType::TimeSet: return "TIME";
    case EventType::Bench:   return "BENCH";
    case EventType::Identify: return "IDENT";
    case EventType::Commission: return "COMM";
  }
  return "?";
}

}  // namespace opencylinder
