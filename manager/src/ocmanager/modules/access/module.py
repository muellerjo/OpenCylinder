from ...core.modules import Module, NavItem
from .ui import api, router

MODULE = Module(
    name="access", title="Access matrix", api=api, ui=router, requires=["sites", "people"],
    nav=[NavItem("Access matrix", "/t/{tenant}/s/{site}/access", "site", "site.read", 75)],
)
