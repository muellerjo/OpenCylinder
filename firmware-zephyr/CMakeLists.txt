# OpenCylinder firmware — Zephyr / nRF Connect SDK (production path, nRF54L15).
# Milestone M1 skeleton: banner + ST25R3916 detection on I2C. The portable
# libraries (../firmware/lib/*) and ST RFAL follow in M1/M2.
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(opencylinder)

file(READ ${CMAKE_CURRENT_SOURCE_DIR}/VERSION OC_FW_VERSION)
string(STRIP "${OC_FW_VERSION}" OC_FW_VERSION)
execute_process(COMMAND git describe --tags --match "fw-v*" --always --dirty
                WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
                OUTPUT_VARIABLE OC_FW_GIT OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
target_compile_definitions(app PRIVATE
    FW_VERSION="${OC_FW_VERSION}" FW_GIT="${OC_FW_GIT}"
    OC_VARIANT_OFFLINE=1 OC_VARIANT_NAME="offline" OC_BOARD_NAME="xiao-nrf54l15")

target_sources(app PRIVATE src/main.c)
