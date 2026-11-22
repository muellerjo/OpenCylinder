#pragma once
// Crypto building blocks for DESFire EV1 AES secure messaging.
// Portable (mbedTLS only), no hardware dependencies.

#include <cstddef>
#include <cstdint>

namespace opencylinder {
namespace crypto {

// AES-128 CMAC (NIST SP 800-38B / RFC 4493) with an explicit start IV.
// DESFire EV1 chains its session IV through CMAC: with iv = 0 this is the
// standard CMAC. Writes the full 16-byte MAC to `mac` (which DESFire then
// uses as the next IV). Returns false on an mbedTLS error.
bool cmacAes128(const uint8_t key[16], const uint8_t iv[16], const uint8_t* msg,
                size_t len, uint8_t mac[16]);

// DESFire CRC32: reflected, polynomial 0xEDB88320, init 0xFFFFFFFF,
// no final XOR (a.k.a. CRC-32/JAMCRC).
uint32_t crc32Desfire(const uint8_t* data, size_t len, uint32_t crc = 0xFFFFFFFFu);

// AES-128 CBC over whole 16-byte blocks; `iv` is advanced in place.
bool aesCbc(const uint8_t key[16], bool encrypt, uint8_t iv[16],
            const uint8_t* in, uint8_t* out, size_t len);

// Known-answer tests: RFC 4493 AES-CMAC vectors and the CRC-32/JAMCRC check
// value. Run at boot; never trust the crypto if this fails.
bool selfTest();

// Overwrite secrets in a way the compiler cannot optimise away.
void wipe(void* p, size_t n);

}  // namespace crypto
}  // namespace opencylinder
