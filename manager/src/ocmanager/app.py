"""Application factory.

  uvicorn --factory ocmanager.app:create_app      (or: ocm serve)

Everything is served from this process: HTML pages (Jinja2 + htmx), static
assets and the JSON API under /api/v1 (OpenAPI schema at /api/openapi.json).
No CDN, no external service — works on an air-gapped PC.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import Settings, get_settings
from .core.db import Database
from .core.modules import load_modules
from .core.security import NotAuthenticated, csrf_protect
from .core.vault import Vault, load_or_create_key_file
from .core.web import WEB, page, redirect

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.mode == "local" and not settings.pm3_path:
        # local PC: use a Proxmark3 client in the usual place without any setting
        import shutil
        from pathlib import Path
        found = shutil.which("pm3") or next((str(p) for p in [Path.home() / "proxmark3" / "pm3"] if p.is_file()),
                                            None)
        settings.pm3_path = found

    app = FastAPI(title="OpenCylinder Manager", version=__version__,
                  docs_url=None, redoc_url=None,            # Swagger/ReDoc load from CDNs -> off
                  openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.db = Database(settings.db_url)
    app.state.vault = Vault.from_settings(settings.master_key, settings.data_dir)
    app.state.modules = load_modules(settings.modules)
    app.state.db.create_all()

    secret = settings.session_secret or load_or_create_key_file(settings.data_dir / "session.key", 32).hex()
    app.add_middleware(SessionMiddleware, secret_key=secret, session_cookie="ocm_session",
                       max_age=settings.session_max_age, same_site="strict",
                       https_only=settings.secure_cookies)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/static"):
            resp.headers["Cache-Control"] = "no-store"
        if settings.secure_cookies:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        return resp

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(csrf_protect)])
    for m in app.state.modules:
        if m.api is not None:
            api.include_router(m.api)
        if m.ui is not None:
            app.include_router(m.ui, dependencies=[Depends(csrf_protect)], include_in_schema=False)
        if m.on_startup:
            m.on_startup(app)
    app.include_router(api)

    @app.get("/api/v1/health", tags=["meta"])
    def health():
        return {"status": "ok", "version": __version__, "mode": settings.mode,
                "modules": [m.name for m in app.state.modules]}

    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

    def is_api(request: Request) -> bool:
        return request.url.path.startswith("/api/")

    @app.exception_handler(NotAuthenticated)
    async def not_auth(request: Request, _exc):
        if is_api(request):
            return JSONResponse({"detail": "not authenticated"}, status_code=401)
        return redirect(f"/login?next={quote(request.url.path)}", request)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if is_api(request):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        return error_page(request, exc.status_code, exc.detail)

    def error_page(request: Request, code: int, detail):
        # The request's DB session is gone (rolled back); reload the operator for the layout.
        from .core.models import Operator
        with app.state.db.sessionmaker() as db:
            uid = request.session.get("uid")
            request.state.operator = db.get(Operator, uid) if uid else None
            return page(request, "error.html", status=code, code=code, detail=detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if is_api(request):
            return JSONResponse({"detail": exc.errors()}, status_code=422)
        msg = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
        return error_page(request, 422, msg)

    return app
