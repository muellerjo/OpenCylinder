#!/bin/sh
# Builds and runs all host tests (plain g++, no hardware). Used by CI.
set -e
cd "$(dirname "$0")"
OUT=$(mktemp -d)
g++ -std=c++17 -Wall -Wextra -I../../lib/access_decision/src test_access_decision.cpp \
    ../../lib/access_decision/src/*.cpp -o "$OUT/t" && "$OUT/t"
g++ -std=c++11 -Wall -Wextra -I../../lib/eventlog/src test_eventlog.cpp \
    ../../lib/eventlog/src/eventlog.cpp -o "$OUT/te" && "$OUT/te"
g++ -std=c++11 -Wall -Wextra -I../../lib/access_decision/src -I../../lib/management/src test_management.cpp \
    ../../lib/management/src/management.cpp ../../lib/access_decision/src/*.cpp -o "$OUT/tm" && "$OUT/tm"
rm -rf "$OUT"
echo "all host tests passed"
