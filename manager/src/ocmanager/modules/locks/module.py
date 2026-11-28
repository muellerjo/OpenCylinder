from ...core.modules import Module, NavItem
from . import models  # noqa: F401
from .api import router as api
from .service import register_hooks
from .ui import router as ui

register_hooks()

MODULE = Module(
    name="locks", title="Lock registry", api=api, ui=ui, requires=["sites"],
    nav=[NavItem("Locks", "/t/{tenant}/s/{site}/locks", "site", "site.read", 35)],
)
