// Host test for lib/eventlog (ring buffer, ordering, wrap-around, encoding).
// Run from firmware/test/host:
//   g++ -std=c++11 -Wall -Wextra -I../../lib/eventlog/src test_eventlog.cpp ../../lib/eventlog/src/eventlog.cpp -o te && ./te

#include <cstdio>
#include <cstring>
#include <map>

#include "eventlog.h"

using namespace opencylinder;

static int failures = 0;
#define CHECK(cond)                                                        \
  do {                                                                     \
    if (!(cond)) {                                                         \
      std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);          \
      ++failures;                                                          \
    }                                                                      \
  } while (0)

struct MemStore : IEventStore {
  std::map<size_t, std::vector<uint8_t>> slots;
  uint32_t count = 0;
  int writes = 0;
  bool readSlot(size_t s, uint8_t out[kEventSize]) override {
    auto it = slots.find(s);
    if (it == slots.end()) return false;
    memcpy(out, it->second.data(), kEventSize);
    return true;
  }
  void writeSlot(size_t s, const uint8_t in[kEventSize]) override {
    slots[s].assign(in, in + kEventSize);
    ++writes;
  }
  uint32_t readCount() override { return count; }
  void writeCount(uint32_t n) override { count = n; }
  void clear() override { slots.clear(); count = 0; }
};

int main() {
  // Encoding round trip
  Event e{1795510800u, 42, EventType::Open, 0, 4, 2001};
  uint8_t raw[kEventSize];
  encodeEvent(e, raw);
  Event d;
  CHECK(decodeEvent(raw, d));
  CHECK(d.time == e.time && d.number == 42 && d.type == EventType::Open && d.target == 4 &&
        d.credential == 2001);
  raw[8] = 0;  // invalid type
  CHECK(!decodeEvent(raw, d));

  // Ring buffer: capacity 4, 6 events -> the last 4, oldest first
  MemStore store;
  EventLog log(store, 4);
  log.begin();
  CHECK(log.entries().empty());
  for (uint32_t i = 1; i <= 6; ++i) log.add(EventType::Deny, 33, 1000 + i, 2000 + i);
  auto all = log.entries();
  CHECK(all.size() == 4 && log.total() == 6);
  CHECK(all.front().number == 3 && all.front().credential == 2003);
  CHECK(all.back().number == 6 && all.back().time == 1006);
  CHECK(store.slots.size() == 4);  // never more slots than capacity

  // Persistence: a new EventLog on the same store continues the numbering
  EventLog again(store, 4);
  again.begin();
  again.add(EventType::Boot, 0, 0);
  CHECK(again.total() == 7 && again.entries().back().number == 7 &&
        again.entries().back().time == 0);

  again.clear();
  CHECK(again.entries().empty() && again.total() == 0);

  if (failures == 0) std::printf("eventlog host tests: all passed\n");
  return failures == 0 ? 0 : 1;
}
