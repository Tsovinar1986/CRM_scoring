"""Self-serve tenant signup/login/password-reset -- an alternative to
manually running scripts/create_tenant.py by hand. Only relevant to a
seller running one shared multi-tenant instance; a single self-hosted buyer
never needs any of this (see auth.py's DEFAULT_TENANT_ID fallback).

Login/signup hand back a tenant's API key (the same credential used
everywhere else via `Authorization: Bearer <key>`) rather than issuing a
separate session token -- this app has exactly one credential type. Since
only the key's hash is ever stored (storage.py), login can't recover the
original key issued at signup; it issues a fresh one instead (see
storage.rotate_api_key), which invalidates whichever key was active before.
That's a real tradeoff -- logging in on a second device signs the first one
out -- documented rather than hidden, since it's the kind of thing that's
confusing to hit by surprise.

On a self-hosted install, signup is gated to an Advanced-tier license (see
app/licensing.py; HOSTED_MODE signups are free Starter workspaces instead) --
onboarding new client workspaces is exactly what "best for agencies running
it across multiple clients" (docs/index.html's Advanced card) promises,
so it's the one real capability difference from Pro today. Login is
deliberately NOT gated the same way: a tenant an agency already onboarded
must keep working even if the agency's own license later lapses or expires
mid-cycle -- only creating new workspaces requires a current Advanced
license, not using ones that already exist.
"""

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, EmailStr, Field

from .. import storage
from ..config import APP_BASE_URL, HOSTED_MODE, PASSWORD_RESET_TTL_MINUTES, RATE_LIMIT_AUTH, RATE_LIMIT_TRIAL
from ..licensing import verify_license
from ..middleware import limiter
from ..services.password import hash_password, validate_password_strength, verify_password
from ..services.reset_email import send_password_reset_email

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(max_length=200)


class TenantAuthResponse(BaseModel):
    tenant_id: str
    name: str
    api_key: str


@router.post("/signup", response_model=TenantAuthResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def signup(request: Request, payload: SignupRequest):
    # On the hosted deployment a signup is just a Starter workspace with a
    # login, upgraded later by paying for that workspace -- the Advanced gate
    # only applies to a self-hosted agency onboarding its own clients.
    if not HOSTED_MODE:
        license_info = verify_license()
        if license_info is None or license_info.tier != "advanced":
            raise HTTPException(
                status_code=402,
                detail="Onboarding new client workspaces requires an Advanced license on this deployment.",
            )
    if storage.get_tenant_by_email(payload.email) is not None:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tenant, api_key = storage.create_tenant(
        payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        # On the public hosted deployment a signup is just a free trial with
        # a login -- metered until it subscribes (see config.HOSTED_MODE).
        plan=storage.STARTER_PLAN if HOSTED_MODE else None,
    )
    logger.info("New self-serve signup: {} ({})", tenant.name, payload.email)
    return TenantAuthResponse(tenant_id=tenant.id, name=tenant.name, api_key=api_key)


@router.post("/trial", response_model=TenantAuthResponse)
@limiter.limit(RATE_LIMIT_TRIAL)
def start_trial(request: Request):
    """One-click private Starter workspace for crmscoring.com's "Get started
    free" -- no email or password. Hosted mode only: a self-hosted install
    already has its own free tier on the default workspace."""
    if not HOSTED_MODE:
        raise HTTPException(status_code=404, detail="Free trials aren't offered on this deployment.")
    tenant, api_key = storage.create_tenant("Free trial", plan=storage.STARTER_PLAN)
    logger.info("New free trial workspace {}", tenant.id)
    return TenantAuthResponse(tenant_id=tenant.id, name=tenant.name, api_key=api_key)


@router.post("/login", response_model=TenantAuthResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def login(request: Request, payload: LoginRequest):
    auth = storage.get_tenant_auth_by_email(payload.email)
    # Same error either way -- don't let a different message for "no such
    # account" vs. "wrong password" leak which emails have accounts.
    if auth is None or not verify_password(payload.password, auth[1]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    tenant, _ = auth
    api_key = storage.rotate_api_key(tenant.id)
    return TenantAuthResponse(tenant_id=tenant.id, name=tenant.name, api_key=api_key)


@router.post("/forgot-password")
@limiter.limit(RATE_LIMIT_AUTH)
def forgot_password(request: Request, payload: ForgotPasswordRequest):
    tenant = storage.get_tenant_by_email(payload.email)
    if tenant is not None:
        token = storage.create_password_reset(tenant.id, ttl_seconds=PASSWORD_RESET_TTL_MINUTES * 60)
        reset_url = f"{APP_BASE_URL}/reset-password?token={token}"
        send_password_reset_email(payload.email, reset_url, PASSWORD_RESET_TTL_MINUTES)
    # Always the same response whether or not the email has an account --
    # avoids leaking which emails are registered.
    return {"detail": "If that email has an account, a reset link is on its way."}


@router.post("/reset-password", response_model=TenantAuthResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def reset_password(request: Request, payload: ResetPasswordRequest):
    tenant_id = storage.consume_password_reset(payload.token)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="That reset link is invalid or has expired.")
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage.update_tenant_password(tenant_id, hash_password(payload.password))
    api_key = storage.rotate_api_key(tenant_id)
    tenant = storage.get_tenant_by_id(tenant_id)
    name = tenant.name if tenant else ""
    return TenantAuthResponse(tenant_id=tenant_id, name=name, api_key=api_key)
