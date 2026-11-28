from ...core.modules import Module, NavItem
from . import models  # noqa: F401
from .api import router as api
from .service import register_hooks
from .ui import router as ui

register_hooks()

MODULE = Module(
    name="people", title="Cardholders, roles, blacklist", api=api, ui=ui, requires=["sites"],
    nav=[
        NavItem("People & cards", "/t/{tenant}/s/{site}/people", "site", "site.read", 50),
        NavItem("Roles", "/t/{tenant}/s/{site}/roles", "site", "site.read", 60),
        NavItem("Blacklist", "/t/{tenant}/s/{site}/blacklist", "site", "site.read", 70),
    ],
)
