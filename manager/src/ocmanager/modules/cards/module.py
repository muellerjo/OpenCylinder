from ...core.modules import Module, NavItem
from . import models  # noqa: F401
from .api import router as api
from .ui import router as ui

MODULE = Module(
    name="cards", title="Card issuing (encoder)", api=api, ui=ui, requires=["sites", "people", "locks"],
    nav=[NavItem("Cards & bundles", "/t/{tenant}/s/{site}/cards", "site", "site.read", 80)],
)
