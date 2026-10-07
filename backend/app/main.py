from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import FileResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import storage
from .auth import get_optional_tenant
from .config import CORS_ALLOWED_ORIGINS, FORCE_HTTPS, HOSTED_MODE
from .licensing import LicenseState, check_license, trial_uploads_left, verify_license, workspace_uploads_left
from .logging_config import configure_logging
from .middleware import SecurityHeadersMiddleware, limiter
from .routers import accounts, actions, billing, churn, leads

configure_logging()

# When frontend/dist exists (`npm run build`), this same process serves it
# too -- one process, one port, nothing else to run. See run-prod.sh. In dev
# mode (npm run dev on its own Vite server) dist won't exist, so this is
# simply skipped and only the API is served here, exactly as before.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    license_info = verify_license()
    if license_info:
        logger.info("Licensed to {} ({} plan)", license_info.customer_email, license_info.plan)
    else:
        logger.info("No valid LICENSE_KEY set — running in trial mode.")
    yield


app = FastAPI(title="AI Lead Generation & Scoring Agent", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware order matters: the first one added here ends up outermost
# (sees a request first, a response last), the last one added is innermost
# (closest to route handling) -- see app/middleware.py's docstring.
if FORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    # Every route in this app is GET or POST -- see routers/*.py.
    allow_methods=["GET", "POST"],
    # Authorization: tenant API key. Content-Type: JSON bodies + multipart
    # uploads.
    allow_headers=["Authorization", "Content-Type"],
    # Browsers hide all response headers from JS by default except a small
    # built-in safelist -- these carry the trial upload cap so the frontend
    # can tell the user why their file got truncated.
    expose_headers=["X-Trial-Limited-Rows", "X-Trial-Total-Rows"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)

app.include_router(leads.router)
app.include_router(actions.router)
app.include_router(actions.alerts_router)
app.include_router(billing.router)
app.include_router(churn.router)
app.include_router(accounts.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/license")
def license_status(tenant: storage.Tenant | None = Depends(get_optional_tenant)):
    return {"hosted": HOSTED_MODE, **_license_status(tenant)}


def _license_status(tenant: storage.Tenant | None) -> dict:
    # Hosted mode: report the visitor's own workspace, never the seller's
    # deployment license.
    if tenant is None:
        return {"licensed": False, "reason": "no_workspace", "customer_email": None, "plan": None,
                "tier": "starter", "trial_uploads_left": None}
    if tenant.plan == storage.STARTER_PLAN:
        uploads_left = workspace_uploads_left(tenant.id)
        return {"licensed": False, "reason": "trial" if uploads_left > 0 else "trial_expired",
                "customer_email": tenant.email, "plan": None, "tier": "starter",
                "trial_uploads_left": uploads_left}
    if tenant.plan is not None:
        # expires_at is set only once the subscription was cancelled.
        return {"licensed": True, "customer_email": tenant.email or tenant.name, "plan": "subscription",
                "tier": tenant.plan, "expires_at": tenant.plan_expires_at}

    check = check_license()
    if check.state == LicenseState.VALID:
        return {
            "licensed": True,
            "customer_email": check.info.customer_email,
            "plan": check.info.plan,
            "tier": check.info.tier,
            "expires_at": check.info.expires_at,
        }
    # INVALID/EXPIRED still carry customer_email/plan when the key at least
    # parsed, so the frontend can say "your license for X expired" instead
    # of generic trial messaging -- a buyer who already paid should never
    # see the same "buy a license" copy as someone who never did. NONE means
    # the free Starter tier -- permanent, no time limit, gated only by the
    # lifetime upload allowance below; "trial_expired" once that's used up.
    uploads_left = trial_uploads_left() if check.state == LicenseState.NONE else None
    reason = check.state.value
    if check.state == LicenseState.NONE:
        reason = "trial" if uploads_left > 0 else "trial_expired"
    return {
        "licensed": False,
        "reason": reason,
        "customer_email": check.info.customer_email if check.info else None,
        "plan": check.info.plan if check.info else None,
        "tier": check.info.tier if check.info else "starter",
        "trial_uploads_left": uploads_left,
    }


def frontend_file(dist: Path, full_path: str) -> Path:
    """The built asset at full_path, or index.html for client-side routes.

    full_path arrives percent-decoded, so "..%2F" becomes "../" -- resolve it
    and refuse anything that lands outside the build, or a crafted URL could
    read .env, the database, or the source code.
    """
    root = dist.resolve()
    candidate = (root / full_path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return root / "index.html"


if FRONTEND_DIST.is_dir():
    # Registered last so every /api/* route above already matched first --
    # this only ever runs for paths none of those routers claimed. Serves a
    # built asset by exact path if one exists, otherwise falls back to
    # index.html so client-side routes (e.g. /purchase-complete) still work
    # on a hard refresh.
    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        return FileResponse(frontend_file(FRONTEND_DIST, full_path))
