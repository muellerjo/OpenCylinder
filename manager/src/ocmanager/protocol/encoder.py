"""Proxmark3 (Iceman client) command plans for the dev encoder.

A plan is a list of Steps. It can be shown (copy into the pm3 client), or run
by the local Proxmark3 driver (ocmanager.modules.encoder). Same commands as
examples/hospital/write_*.py. Dev cards only: factory-default card master key.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass

from .an10922 import diversify
from .bundle import BUNDLE_FILE_SIZE, COMMISSIONING_FILE_SIZE
from .commissioning import AID as COMMISSIONING_AID

ZERO = "00" * 16
RIGHTS = "--amode encrypt --rrights key1 --wrights key0 --rwrights key0 --chrights key0"


@dataclass
class Step:
    desc: str
    cmd: str
    expect: str = "ok"          # ok | fail | any
    verify: str | None = None   # hex that must appear in the output

    def as_dict(self):
        return asdict(self)

    def __getitem__(self, key):            # scripts use step["cmd"], step["expect"], ...
        return getattr(self, key)


def _chkey(aid: str, no: int, new: str) -> str:
    return (f"hf mfdes changekey --aid {aid} -n 0 -t aes -k {ZERO} --newkeyno {no} "
            f"--oldalgo aes --oldkey {ZERO} --newalgo aes --newkey {new} --newver 01")


def user_app_steps(aid: str, file0: bytes, file1_used: bytes, k0: str, k1: str, k2: str) -> list[Step]:
    """Keys, files, records and checks inside a freshly created site application.
    k0/k1 = this card's diversified issuer/read key, k2 = site UID key (hex)."""
    a0, a1, a2 = (f"-n {n} -t aes -k {k}" for n, k in ((0, k0), (1, k1), (2, k2)))
    s = [
        Step("A3  set key 1 (site read key, diversified)", _chkey(aid, 1, k1)),
        Step("A3  set key 2 (UID key, site-wide)", _chkey(aid, 2, k2)),
        Step("A3  set key 0 (issuer key, diversified) — last", _chkey(aid, 0, k0)),
        Step(f"A4  application list contains {aid}", "hf mfdes getaids", verify=aid),
        Step("B1  create file 0 (header, 16 bytes)",
             f"hf mfdes createfile --aid {aid} {a0} --fid 00 --size 000010 {RIGHTS}"),
        Step("B1  create file 1 (access list, 128 bytes)",
             f"hf mfdes createfile --aid {aid} {a0} --fid 01 --size 000080 {RIGHTS}"),
        Step("B2  write header with issuer key",
             f"hf mfdes write --aid {aid} {a0} -m encrypt --fid 00 -d {file0.hex().upper()}"),
    ]
    if file1_used:
        s.append(Step("B2  write access list with issuer key",
                      f"hf mfdes write --aid {aid} {a0} -m encrypt --fid 01 -d {file1_used.hex().upper()}"))
    s.append(Step("C1  read header with READ key (like a lock)",
                  f"hf mfdes read --aid {aid} {a1} -m encrypt --fid 00", verify=file0.hex().upper()))
    if file1_used:
        s.append(Step("C1  read access list with READ key",
                      f"hf mfdes read --aid {aid} {a1} -m encrypt --fid 01 -l {len(file1_used):06X}",
                      verify=file1_used.hex().upper()))
    s += [
        Step("C2  write with READ key must be REFUSED (key separation)",
             f"hf mfdes write --aid {aid} {a1} -m encrypt --fid 00 -d {'00' * 16}", expect="fail"),
        Step("C3  read with UID key must be REFUSED (no file rights)",
             f"hf mfdes read --aid {aid} {a2} -m encrypt --fid 00", expect="fail"),
    ]
    return s


def format_and_create_steps(aid: str) -> list[Step]:
    return [
        Step("A1  format card (delete all applications)", "hf mfdes formatpicc"),
        Step(f"A2  create application {aid} with 3 AES keys",
             f"hf mfdes createapp --aid {aid} --ks1 0B --dstalgo aes --numkeys 3"),
    ]


def dam_create_step(aid: str, slot: int, grant: dict) -> Step:
    """EV2/EV3: create the site application DELEGATED in a DAM slot with the card owner's
    grant (EncK, DAMMAC) — no format, other sites' applications stay."""
    quota = int(grant["quota_blocks"])
    return Step(f"A2  create DELEGATED application {aid} (DAM slot {slot}, quota {quota} "
                "blocks) with the owner's grant",
                f"hf mfdes createdelegateapp --aid {aid} --damslot {slot:04X} --damslotver 00 "
                f"--quota {quota:04X} --ks1 {grant['ks1']} --ks2 {grant['ks2']} -t 2TDEA "
                f"-k {grant['dam_auth_key']} --enck {grant['enck']} --dammac {grant['dammac']}")


def kdf_check_steps(aid: str, read_master_hex: str, kdf_input_hex: str) -> list[Step]:
    """Bench self-check against the Proxmark's own AN10922. Puts the MASTER read key on the
    command line — dev keys only, never for a real site (the manager leaves it out)."""
    return [
        Step("D1  Proxmark's own AN10922 (master read key + --kdf) authenticates",
             f"hf mfdes auth --aid {aid} -n 1 -t aes -k {read_master_hex} --kdf AN10922 -i {kdf_input_hex}"),
        Step("D2  undiversified master read key must be REFUSED",
             f"hf mfdes auth --aid {aid} -n 1 -t aes -k {read_master_hex}", expect="fail"),
    ]


def card_keys(uid: bytes, aid: str, master0: bytes, master1: bytes) -> tuple[str, str]:
    """Per-card keys 0 and 1 (hex) — AN10922 with M = UID || AID (wire order)."""
    m = uid + bytes.fromhex(aid)[::-1]
    return diversify(master0, m).hex().upper(), diversify(master1, m).hex().upper()


def user_card_plan(aid: str, uid: bytes, file0: bytes, file1_used: bytes,
                   issuer_master: bytes, read_master: bytes, uid_key: bytes) -> list[Step]:
    """Format the card, create the site application, write + verify."""
    k0, k1 = card_keys(uid, aid, issuer_master, read_master)
    return format_and_create_steps(aid) + user_app_steps(aid, file0, file1_used, k0, k1, uid_key.hex().upper())


def admin_card_plan(admin_aid: str, uid: bytes, header: bytes, bundle: bytes,
                    admin_issuer_master: bytes, admin_read_master: bytes,
                    app_exists: bool = False) -> list[Step]:
    """Admin application next to any user application (write_admin_card.py)."""
    if len(bundle) > BUNDLE_FILE_SIZE:
        raise ValueError(f"bundle too large: {len(bundle)} > {BUNDLE_FILE_SIZE} bytes")
    k0, k1 = card_keys(uid, admin_aid, admin_issuer_master, admin_read_master)
    a0, a1 = f"-n 0 -t aes -k {k0}", f"-n 1 -t aes -k {k1}"
    create = [
        Step(f"A1  delete old admin application {admin_aid} (may not exist)",
             f"hf mfdes deleteapp --aid {admin_aid}", expect="any"),
        Step(f"A2  create admin application {admin_aid} with 2 AES keys",
             f"hf mfdes createapp --aid {admin_aid} --ks1 0B --dstalgo aes --numkeys 2"),
        Step("A3  set key 1 (admin read key, diversified)", _chkey(admin_aid, 1, k1)),
        Step("A3  set key 0 (admin issuer key, diversified) — last", _chkey(admin_aid, 0, k0)),
        Step("B1  create file 0 (admin header, 16 bytes)",
             f"hf mfdes createfile --aid {admin_aid} {a0} --fid 00 --size 000010 {RIGHTS}"),
        Step(f"B1  create file 1 (bundle, {BUNDLE_FILE_SIZE} bytes)",
             f"hf mfdes createfile --aid {admin_aid} {a0} --fid 01 --size {BUNDLE_FILE_SIZE:06X} {RIGHTS}"),
    ]
    return ([] if app_exists else create) + [
        Step("B2  write admin header",
             f"hf mfdes write --aid {admin_aid} {a0} -m encrypt --fid 00 -d {header.hex().upper()}"),
        Step("B2  write signed bundle",
             f"hf mfdes write --aid {admin_aid} {a0} -m encrypt --fid 01 -d {bundle.hex().upper()}"),
        Step("C1  read bundle back with admin READ key",
             f"hf mfdes read --aid {admin_aid} {a1} -m encrypt --fid 01 -l {len(bundle):06X}",
             verify=bundle.hex().upper()),
    ]


def commissioning_card_plan(bundle: bytes, app_exists: bool = False) -> list[Step]:
    if len(bundle) > COMMISSIONING_FILE_SIZE:
        raise ValueError(f"bundle too large: {len(bundle)} > {COMMISSIONING_FILE_SIZE} bytes")
    aid, auth = COMMISSIONING_AID, f"-n 0 -t aes -k {ZERO}"
    steps = [] if app_exists else [
        Step(f"create commissioning application {aid}",
             f"hf mfdes createapp --aid {aid} --ks1 0B --dstalgo aes --numkeys 1"),
        Step(f"create file 0 ({COMMISSIONING_FILE_SIZE} bytes, plain, free read)",
             f"hf mfdes createfile --aid {aid} {auth} --fid 00 --size {COMMISSIONING_FILE_SIZE:06X} "
             "--amode plain --rrights free --wrights key0 --rwrights key0 --chrights key0"),
    ]
    return steps + [
        Step("write commissioning bundle",
             f"hf mfdes write --aid {aid} {auth} -m plain --fid 00 -d {bundle.hex().upper()}"),
        Step("read back (free read)", f"hf mfdes read --aid {aid} --fid 00 --no-auth -l {len(bundle):06X}",
             verify=bundle.hex().upper()),
    ]


# ------------------------------------------------------------ pm3 runner

ANSI = re.compile(r"\x1b\[[0-9;]*m")
ERROR_MARKERS = ("[!!]", "[-]", "[!] ")
ERROR_WORDS = re.compile(r"error|fail|can't|cannot|not found|denied|timeout", re.I)
UID_RE = re.compile(r"UID:\s*((?:[0-9A-Fa-f]{2}\s){6}[0-9A-Fa-f]{2})\b")


def run_pm3(pm3: str, port: str | None, cmd: str, timeout: int = 60) -> str:
    argv = [pm3] + ([port] if port else []) + ["-c", cmd]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return ANSI.sub("", p.stdout + p.stderr)


def looks_failed(out: str) -> bool:
    for line in out.splitlines():
        if (line.startswith(ERROR_MARKERS) or (line.startswith("[") and ERROR_WORDS.search(line))) \
                and "Session log" not in line:
            return True
    return False


def data_hex(out: str) -> str:
    """Hex bytes of a Proxmark file dump (the `| XX XX .. |` data columns), joined."""
    cols = re.findall(r"\|\s*((?:[0-9A-Fa-f]{2}\s+)+)\|", out)
    return "".join(c.replace(" ", "") for c in cols).upper()


def verified(out: str, expected_hex: str) -> bool:
    dump = data_hex(out)
    return expected_hex.upper() in dump or expected_hex.upper() in re.sub(r"\s", "", out).upper()


def step_ok(step: Step, out: str) -> bool:
    failed = looks_failed(out) or (step.verify is not None and not verified(out, step.verify))
    return step.expect == "any" or (failed if step.expect == "fail" else not failed)


CMD_MARK = re.compile(r"pm3 --> (.*)$")
AID_LINE = re.compile(r"\b([0-9A-Fa-f]{6})\b")


def run_pm3_batch(pm3: str, port: str | None, cmds: list[str], timeout: int = 90) -> list[str]:
    """Several commands in ONE client session ("a; b; c") — one USB connect instead of
    one per command. Returns the output of each command (split at the client's
    `pm3 --> <cmd>` echo lines)."""
    out = run_pm3(pm3, port, "; ".join(cmds), timeout=timeout)
    parts: list[list[str]] = []
    for line in out.splitlines():
        if CMD_MARK.search(line):
            parts.append([])
        elif parts:
            parts[-1].append(line)
    res = ["\n".join(p) for p in parts]
    return res + [""] * (len(cmds) - len(res))


def parse_aids(getaids_out: str) -> list[str]:
    """AIDs from `hf mfdes getaids` (lines after '--- AID list')."""
    aids, on = [], False
    for line in getaids_out.splitlines():
        if "AID list" in line:
            on = True
            continue
        if on and line.startswith("[+]"):
            aids += [a.upper() for a in AID_LINE.findall(line[3:])]
    return aids


def read_cmd(aid: str, fid: int, key_no: int | None = None, key_hex: str | None = None,
             length: int | None = None) -> str:
    """hf mfdes read: encrypted with a key, or plain with --no-auth (free read files)."""
    auth = f"-n {key_no} -t aes -k {key_hex} -m encrypt" if key_hex else "--no-auth"
    ln = f" -l {length:06X}" if length else ""
    return f"hf mfdes read --aid {aid} {auth} --fid {fid:02X}{ln}"
