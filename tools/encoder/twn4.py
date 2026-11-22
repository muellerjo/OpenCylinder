"""Minimal driver for an Elatec TWN4 running the Simple Protocol firmware.

Protocol (Elatec "TWN4 Simple Protocol"): ASCII mode, every byte sent as two
hex characters, each command/response line ends with a carriage return.
Response layout: [status 00][result bool][payload...]
Variable-length arrays in the payload are prefixed with their length byte.
"""

import serial


class TWN4Error(Exception):
    pass


class TWN4:
    def __init__(self, port="/dev/ttyACM0", baud=9600, timeout=1.0):
        self.ser = serial.Serial(port, baud, timeout=timeout)

    # --- transport -------------------------------------------------------

    def command(self, hex_cmd):
        """Send one command line, return the raw response bytes."""
        self.ser.reset_input_buffer()
        self.ser.write(hex_cmd.encode("ascii") + b"\r")
        line = self.ser.read_until(b"\r").strip()
        if not line:
            raise TWN4Error(f"no answer to {hex_cmd}")
        resp = bytes.fromhex(line.decode("ascii"))
        if resp[0] != 0:
            raise TWN4Error(f"{hex_cmd}: reader error 0x{resp[0]:02X}")
        return resp

    def _payload(self, hex_cmd):
        """Run a command that returns [00][bool][payload]; None if bool is false."""
        resp = self.command(hex_cmd)
        if len(resp) < 2 or resp[1] == 0:
            return None
        return resp[2:]

    # --- system ----------------------------------------------------------

    def version(self):
        resp = self.command("0004FF")          # GetVersionString
        return resp[2:].decode("ascii", errors="replace")

    # --- RF / ISO14443A --------------------------------------------------

    def search_tag(self):
        """Return (tag_type, uid_bytes) or None if no card is present."""
        p = self._payload("050010")             # SearchTag, max 16 ID bytes
        if p is None:
            return None
        tag_type, _bit_count, id_len = p[0], p[1], p[2]
        return tag_type, p[3:3 + id_len]

    def atqa(self):
        p = self._payload("1204")               # ISO14443A_GetATQA
        return p[:2] if p else None

    def sak(self):
        p = self._payload("1205")               # ISO14443A_GetSAK
        return p[0] if p else None

    def ats(self):
        p = self._payload("120020")             # ISO14443A_GetATS
        return p[1:1 + p[0]] if p else None

    # --- MIFARE Ultralight / NTAG ----------------------------------------

    def ultralight_read(self, page):
        """Read 16 bytes (4 pages) starting at `page`."""
        p = self._payload(f"0C00{page:02X}")    # MifareUltralight_ReadPage
        return p[:16] if p else None

    # --- DESFire ---------------------------------------------------------

    def desfire_version(self):
        """Raw GetVersion data: hardware info, software info, UID, batch, date."""
        return self._payload("0F1200")          # DESFire_GetVersion

    def desfire_app_ids(self, max_count=0x1C):
        """List application IDs (works if the card allows free directory listing)."""
        p = self._payload(f"0F0000{max_count:02X}")   # DESFire_GetApplicationIDs
        if p is None:
            return None
        count = p[0]
        data = p[1:1 + 4 * count]               # UInt32, LSB first
        return [int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data), 4)]
