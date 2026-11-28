from ...core.modules import Module, NavItem
from . import models  # noqa: F401  (registers tables)
from .api import router as api
from .ui import router as ui

MODULE = Module(
    name="sites", title="Sites & building structure", api=api, ui=ui,
    nav=[
        NavItem("Sites", "/t/{tenant}", "tenant", "site.read", 10),
        NavItem("Overview", "/t/{tenant}/s/{site}", "site", "site.read", 10),
        NavItem("Zones", "/t/{tenant}/s/{site}/zones", "site", "site.read", 20),
        NavItem("Doors", "/t/{tenant}/s/{site}/doors", "site", "site.read", 30),
        NavItem("Time profiles", "/t/{tenant}/s/{site}/profiles", "site", "site.read", 40),
    ],
)
