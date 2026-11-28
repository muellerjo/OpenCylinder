"""Feature modules — the unit of extension.

A module is a Python package that exposes `MODULE: Module`. Built-in modules
live in ocmanager.modules.*; third-party packages register more through the
entry-point group "ocmanager.modules":

    [project.entry-points."ocmanager.modules"]
    myfeature = "my_package.module:MODULE"

Each module contributes (all optional): ORM models (imported for their side
effect on Base.metadata), a JSON API router (mounted under /api/v1), a UI
router (HTML pages), navigation entries, and a startup hook. Modules depend
on core/ and on each other's *service* functions only, never on each other's
routes or templates.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import entry_points

from fastapi import APIRouter

BUILTIN = ["auth", "platform", "sites", "people", "locks", "cards", "access", "audit"]


@dataclass
class NavItem:
    label: str
    path: str          # format string: {tenant}, {site} are filled in
    scope: str         # "platform" | "tenant" | "site"
    perm: str | None = None
    order: int = 100


@dataclass
class Module:
    name: str
    title: str
    api: APIRouter | None = None
    ui: APIRouter | None = None
    nav: list[NavItem] = field(default_factory=list)
    on_startup: Callable | None = None
    requires: list[str] = field(default_factory=list)


def load_modules(selection: str = "*") -> list[Module]:
    wanted = None if selection.strip() == "*" else {s.strip() for s in selection.split(",")}
    mods: list[Module] = []
    for name in BUILTIN:
        if wanted is None or name in wanted or name in ("auth", "platform", "sites"):
            mods.append(import_module(f"ocmanager.modules.{name}.module").MODULE)
    for ep in entry_points(group="ocmanager.modules"):
        if wanted is None or ep.name in wanted:
            mods.append(ep.load())
    names = {m.name for m in mods}
    for m in mods:
        missing = [r for r in m.requires if r not in names]
        if missing:
            raise RuntimeError(f"module {m.name} needs {missing}")
    return mods
