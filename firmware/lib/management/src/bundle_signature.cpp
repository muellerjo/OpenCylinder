// ECDSA P-256 / SHA-256 verification of management bundles (mbedTLS).
// Excluded from host tests (no mbedTLS on the host); covered on the bench.

#include <mbedtls/bignum.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/ecp.h>
#include <mbedtls/sha256.h>

#include "management.h"

namespace opencylinder {

bool verifyBundleSignature(const uint8_t* bundle, size_t len, const uint8_t publicKey[65]) {
  if (len <= kBundleSignatureSize || publicKey[0] != 0x04) return false;
  const size_t signedLen = len - kBundleSignatureSize;
  const uint8_t* sig = bundle + signedLen;

  uint8_t hash[32];
  mbedtls_sha256_context sha;
  mbedtls_sha256_init(&sha);
  int rc = mbedtls_sha256_starts_ret(&sha, 0);
  if (rc == 0) rc = mbedtls_sha256_update_ret(&sha, bundle, signedLen);
  if (rc == 0) rc = mbedtls_sha256_finish_ret(&sha, hash);
  mbedtls_sha256_free(&sha);
  if (rc != 0) return false;

  mbedtls_ecp_group grp;
  mbedtls_ecp_point q;
  mbedtls_mpi r, s;
  mbedtls_ecp_group_init(&grp);
  mbedtls_ecp_point_init(&q);
  mbedtls_mpi_init(&r);
  mbedtls_mpi_init(&s);

  rc = mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1);
  if (rc == 0) rc = mbedtls_ecp_point_read_binary(&grp, &q, publicKey, 65);
  if (rc == 0) rc = mbedtls_ecp_check_pubkey(&grp, &q);
  if (rc == 0) rc = mbedtls_mpi_read_binary(&r, sig, 32);
  if (rc == 0) rc = mbedtls_mpi_read_binary(&s, sig + 32, 32);
  if (rc == 0) rc = mbedtls_ecdsa_verify(&grp, hash, sizeof hash, &q, &r, &s);

  mbedtls_mpi_free(&r);
  mbedtls_mpi_free(&s);
  mbedtls_ecp_point_free(&q);
  mbedtls_ecp_group_free(&grp);
  return rc == 0;
}

}  // namespace opencylinder
