#pragma once
// The lock's identity — spec/admin-card.md §5.2: a permanent ECDH P-256 key
// pair, generated once by the lock itself. Never wiped by reset or
// decommission. Dev board: kept in NVS (a full erase_flash loses it);
// production: secure element / MCU key storage, private key not exportable.

#include <Preferences.h>
#include <esp_random.h>
#include <mbedtls/ecdh.h>
#include <mbedtls/ecp.h>

#include <cstdio>
#include <cstring>

namespace opencylinder {

// True randomness on the ESP32 needs an entropy source: WiFi/BT (not in an
// offline build) or the SAR-ADC noise source enabled by bootloader_random_
// enable() (see setup()). esp_fill_random then returns true random numbers.
inline int espRng(void*, unsigned char* buf, size_t len) {
  esp_fill_random(buf, len);
  return 0;
}

class DeviceIdentity {
 public:
  // Load the key pair, or generate it on the very first boot.
  // Returns false only on a crypto error.
  bool begin(const uint8_t deviceId[8], bool& generated) {
    memcpy(deviceId_, deviceId, 8);
    generated = false;
    prefs_.begin("oc-dev", false);
    uint8_t priv[32];
    if (!prefs_.isKey("priv") || prefs_.getBytes("priv", priv, sizeof priv) != sizeof priv) {
      if (!generate(priv)) return false;
      prefs_.putBytes("priv", priv, sizeof priv);
      generated = true;
    }
    const bool ok = derivePublic(priv);
    mbedtls_platform_zeroize_compat(priv, sizeof priv);
    return ok;
  }

  // ECDH with the device private key: peer = uncompressed P-256 point,
  // shared = x-coordinate. The private key is loaded only for this call.
  bool ecdh(const uint8_t peer[65], uint8_t shared[32]) {
    uint8_t priv[32];
    if (prefs_.getBytes("priv", priv, sizeof priv) != sizeof priv) return false;
    mbedtls_ecp_group grp;
    mbedtls_mpi d, z;
    mbedtls_ecp_point q;
    mbedtls_ecp_group_init(&grp);
    mbedtls_mpi_init(&d);
    mbedtls_mpi_init(&z);
    mbedtls_ecp_point_init(&q);
    int rc = mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1);
    if (rc == 0) rc = mbedtls_mpi_read_binary(&d, priv, 32);
    if (rc == 0) rc = mbedtls_ecp_point_read_binary(&grp, &q, peer, 65);
    if (rc == 0) rc = mbedtls_ecp_check_pubkey(&grp, &q);
    if (rc == 0) rc = mbedtls_ecdh_compute_shared(&grp, &z, &q, &d, espRng, nullptr);
    if (rc == 0) rc = mbedtls_mpi_write_binary(&z, shared, 32);
    mbedtls_ecp_point_free(&q);
    mbedtls_mpi_free(&z);
    mbedtls_mpi_free(&d);
    mbedtls_ecp_group_free(&grp);
    mbedtls_platform_zeroize_compat(priv, sizeof priv);
    return rc == 0;
  }

  const uint8_t* deviceId() const { return deviceId_; }
  const uint8_t* publicKey() const { return pub_; }  // compressed, 33 bytes

  // "OC1:<device ID hex>:<compressed public key hex>" (spec §5.2)
  void qrText(char* out, size_t n) const {
    int k = snprintf(out, n, "OC1:");
    for (int i = 0; i < 8 && k < static_cast<int>(n); ++i) k += snprintf(out + k, n - k, "%02X", deviceId_[i]);
    if (k < static_cast<int>(n)) k += snprintf(out + k, n - k, ":");
    for (int i = 0; i < 33 && k < static_cast<int>(n); ++i) k += snprintf(out + k, n - k, "%02X", pub_[i]);
  }

 private:
  static void mbedtls_platform_zeroize_compat(void* p, size_t n) {
    volatile uint8_t* v = static_cast<volatile uint8_t*>(p);
    while (n--) *v++ = 0;
  }

  bool generate(uint8_t priv[32]) {
    mbedtls_ecp_group grp;
    mbedtls_mpi d;
    mbedtls_ecp_point q;
    mbedtls_ecp_group_init(&grp);
    mbedtls_mpi_init(&d);
    mbedtls_ecp_point_init(&q);
    int rc = mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1);
    if (rc == 0) rc = mbedtls_ecp_gen_keypair(&grp, &d, &q, espRng, nullptr);
    if (rc == 0) rc = mbedtls_mpi_write_binary(&d, priv, 32);
    mbedtls_ecp_point_free(&q);
    mbedtls_mpi_free(&d);
    mbedtls_ecp_group_free(&grp);
    return rc == 0;
  }

  bool derivePublic(const uint8_t priv[32]) {
    mbedtls_ecp_group grp;
    mbedtls_mpi d;
    mbedtls_ecp_point q;
    mbedtls_ecp_group_init(&grp);
    mbedtls_mpi_init(&d);
    mbedtls_ecp_point_init(&q);
    size_t olen = 0;
    int rc = mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1);
    if (rc == 0) rc = mbedtls_mpi_read_binary(&d, priv, 32);
    if (rc == 0) rc = mbedtls_ecp_check_privkey(&grp, &d);
    if (rc == 0) rc = mbedtls_ecp_mul(&grp, &q, &d, &grp.G, espRng, nullptr);
    if (rc == 0) {
      rc = mbedtls_ecp_point_write_binary(&grp, &q, MBEDTLS_ECP_PF_COMPRESSED, &olen, pub_,
                                          sizeof pub_);
    }
    mbedtls_ecp_point_free(&q);
    mbedtls_mpi_free(&d);
    mbedtls_ecp_group_free(&grp);
    return rc == 0 && olen == 33;
  }

  Preferences prefs_;
  uint8_t deviceId_[8] = {0};
  uint8_t pub_[33] = {0};
};

}  // namespace opencylinder
