# PlatformIO pre-build script: stamps the firmware version into the build.
#
#   FW_VERSION  semantic version from firmware/VERSION   e.g. "0.1.0"
#   FW_GIT      `git describe` of the checkout           e.g. "fw-v0.1.0-3-g1a2b3c4-dirty"
#
# The firmware prints both at boot, so any running board can tell exactly
# which source it was built from. "-dirty" means uncommitted changes.

import subprocess
from pathlib import Path

Import("env")  # noqa: F821  (provided by PlatformIO/SCons)

project_dir = Path(env["PROJECT_DIR"])  # noqa: F821
version = (project_dir / "VERSION").read_text().strip()

try:
    git = subprocess.check_output(
        ["git", "describe", "--tags", "--match", "fw-v*", "--always", "--dirty"],
        cwd=project_dir,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
except (OSError, subprocess.CalledProcessError):
    git = "unknown"

env.Append(  # noqa: F821
    CPPDEFINES=[
        ("FW_VERSION", env.StringifyMacro(version)),  # noqa: F821
        ("FW_GIT", env.StringifyMacro(git)),  # noqa: F821
    ]
)
print(f"OpenCylinder firmware {version} ({git})")
