"""Proxmark3 (Iceman client) command plans for the dev encoder.

A plan is a list of Steps. It can be shown (copy into the pm3 client), or run
by the local Proxmark3 driver (ocmanager.modules.encoder). Same commands as
examples/hospital/write_*.py. Dev cards only: factory-default card master key.
"""

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


def _chkey(aid: str, no: int, new: str) -> str:
    return (f"hf mfdes changekey --aid {aid} -n 0 -t aes -k {ZERO} --newkeyno {no} "
            f"--oldalgo aes --oldkey {ZERO} --newalgo aes --newkey {new} --newver 01")


def user_card_plan(aid: str, uid: bytes, file0: bytes, file1_used: bytes,
                   issuer_master: bytes, read_master: bytes, uid_key: bytes) -> list[Step]:
    """Format the card, create the site application, write + verify (write_test_card.py)."""
    m = uid + bytes.fromhex(aid)[::-1]
    k0 = diversify(issuer_master, m).hex().upper()
    k1 = diversify(read_master, m).hex().upper()
    k2 = uid_key.hex().upper()
    a0, a1, a2 = (f"-n {n} -t aes -k {k}" for n, k in ((0, k0), (1, k1), (2, k2)))
    s = [
        Step("A1  format card (delete all applications)", "hf mfdes formatpicc"),
        Step(f"A2  create application {aid} with 3 AES keys",
             f"hf mfdes createapp --aid {aid} --ks1 0B --dstalgo aes --numkeys 3"),
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


def admin_card_plan(admin_aid: str, uid: bytes, header: bytes, bundle: bytes,
                    admin_issuer_master: bytes, admin_read_master: bytes,
                    app_exists: bool = False) -> list[Step]:
    """Admin application next to any user application (write_admin_card.py)."""
    if len(bundle) > BUNDLE_FILE_SIZE:
        raise ValueError(f"bundle too large: {len(bundle)} > {BUNDLE_FILE_SIZE} bytes")
    m = uid + bytes.fromhex(admin_aid)[::-1]
    k0 = diversify(admin_issuer_master, m).hex().upper()
    k1 = diversify(admin_read_master, m).hex().upper()
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


def verified(out: str, expected_hex: str) -> bool:
    cols = re.findall(r"\|\s*((?:[0-9A-Fa-f]{2}\s+)+)\|", out)
    dump = "".join(c.replace(" ", "") for c in cols).upper()
    return expected_hex.upper() in dump or expected_hex.upper() in re.sub(r"\s", "", out).upper()


def step_ok(step: Step, out: str) -> bool:
    failed = looks_failed(out) or (step.verify is not None and not verified(out, step.verify))
    return step.expect == "any" or (failed if step.expect == "fail" else not failed)
