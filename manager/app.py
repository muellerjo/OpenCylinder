#!/usr/bin/env python3
"""Start the OpenCylinder Manager:   python manager/app.py   ->  http://127.0.0.1:8243

First start: the browser asks for your admin user (and can load the example hospital).
Data lives in manager/data/ (git-ignored). Options: --port N, --host 0.0.0.0
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

try:
    import fastapi  # noqa: F401
    import uvicorn
except ImportError:
    venv_py = HERE / ".venv" / "bin" / "python"
    if venv_py.exists() and Path(sys.prefix).resolve() != (HERE / ".venv").resolve():
        os.execv(str(venv_py), [str(venv_py), __file__, *sys.argv[1:]])   # use manager/.venv
    sys.exit("missing packages — run once:\n"
             f"  python3 -m venv {HERE}/.venv && {HERE}/.venv/bin/pip install -r {HERE}/requirements.txt")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8243)
    ap.add_argument("--reset-password", metavar="USER", nargs="?", const="",
                    help="set a new password for USER (without USER: list the users)")
    a = ap.parse_args()
    if a.reset_password is not None:
        import getpass

        from sqlalchemy import select

        from ocmanager.app import create_app
        from ocmanager.core.models import Operator
        from ocmanager.core.security import hash_password
        app = create_app()
        with app.state.db.sessionmaker() as db:
            users = db.scalars(select(Operator).order_by(Operator.username)).all()
            op = next((u for u in users if u.username == a.reset_password.lower()), None)
            if op is None:
                sys.exit("users: " + (", ".join(u.username for u in users) or "(none — just start, setup runs)")
                         + "\nusage: python3 manager/app.py --reset-password USER")
            pw = getpass.getpass(f"new password for {op.username} (min. 10): ")
            if pw != getpass.getpass("repeat: "):
                sys.exit("passwords differ")
            try:
                op.password_hash = hash_password(pw)
            except ValueError as e:
                sys.exit(str(e))
            op.active = True
            op.session_version += 1
            from ocmanager.core.audit import record
            record(db, "account.password_reset_cli", op.username)
            db.commit()
        print(f"password of {op.username} changed — start again: python3 manager/app.py")
        sys.exit(0)
    print(f"OpenCylinder Manager on http://{a.host}:{a.port}  (data: {HERE / 'data'})")
    uvicorn.run("ocmanager.app:create_app", factory=True, host=a.host, port=a.port)
