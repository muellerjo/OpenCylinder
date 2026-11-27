/* OpenCylinder — Zephyr skeleton for the nRF54L15 (milestone M1).
 * Prints the banner, then looks for the ST25R3916 on I2C and reads its
 * IC identity register. Card detection via ST RFAL comes next.
 * UNTESTED: written before the board and the toolchain were available. */

#include <zephyr/device.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#if defined(OC_VARIANT_OFFLINE) && defined(CONFIG_BT)
#error "offline variant must not contain the Bluetooth stack"
#endif

#define ST25R3916_I2C_ADDR    0x50  /* 7-bit address, default */
#define ST25R3916_REG_IC_ID   0x3F  /* IC identity register */
#define ST25R3916_READ_MODE   0x40  /* register read: 0b01 << 6 | address */

static const struct device *const nfc_i2c = DEVICE_DT_GET(DT_ALIAS(nfc_i2c));

int main(void)
{
	k_msleep(1500); /* give the USB serial bridge time to attach */
	printk("OpenCylinder fw %s+%s.%s (%s)\n", FW_VERSION, OC_BOARD_NAME,
	       OC_VARIANT_NAME, FW_GIT);
	printk("Zephyr skeleton (M1): looking for the ST25R3916 on I2C\n");

	if (!device_is_ready(nfc_i2c)) {
		printk("ERROR: I2C bus not ready\n");
		return 0;
	}

	const uint8_t cmd = ST25R3916_READ_MODE | ST25R3916_REG_IC_ID;
	uint8_t id = 0;
	int rc = i2c_write_read(nfc_i2c, ST25R3916_I2C_ADDR, &cmd, 1, &id, 1);
	if (rc != 0) {
		printk("ST25R3916 not found at 0x%02x (rc %d) - check wiring\n",
		       ST25R3916_I2C_ADDR, rc);
	} else {
		/* ic_type in bits 7..3, ic_rev in bits 2..0 */
		printk("ST25R3916 found: IC identity 0x%02x (type %u, rev %u)\n",
		       id, id >> 3, id & 0x07);
	}

	while (1) {
		k_msleep(1000);
	}
	return 0;
}
