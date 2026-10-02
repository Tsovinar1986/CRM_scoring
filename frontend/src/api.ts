import type {
  Account,
  BillingConfig,
  LicenseStatus,
  ScoredLead,
  SubscribeRequest,
  SubscriptionActivation,
  TenantAuth,
} from "./types";

// Same-origin by default -- works unmodified both in merged production mode
// (backend serves the built frontend, so "same origin" IS the backend) and
// in dev mode (vite.config.ts proxies /api to localhost:8081). Only set
// VITE_API_BASE_URL if the API genuinely lives on a different origin than
// wherever this frontend is served from.
const BASE = `${import.meta.env.VITE_API_BASE_URL ?? ""}/api`;

const TENANT_KEY_STORAGE_KEY = "tenant_api_key";

// Only relevant for a seller running one shared instance for multiple
// customers (backend/scripts/create_tenant.py). A single self-hosted buyer
// never sets this -- every request then falls back to the backend's
// default tenant, exactly the original zero-config behavior.
export function getTenantApiKey(): string | null {
  return localStorage.getItem(TENANT_KEY_STORAGE_KEY);
}

export function setTenantApiKey(key: string): void {
  localStorage.setItem(TENANT_KEY_STORAGE_KEY, key);
}

export function clearTenantApiKey(): void {
  localStorage.removeItem(TENANT_KEY_STORAGE_KEY);
}

function authHeaders(): Record<string, string> {
  const key = getTenantApiKey();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

export class LicenseRequiredError extends Error {}
export class TenantAuthError extends Error {}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const message = body.detail ?? "Request failed";
    if (res.status === 402) throw new LicenseRequiredError(message);
    if (res.status === 401) throw new TenantAuthError(message);
    throw new Error(message);
  }
  return res.json();
}

export interface UploadResult {
  leads: ScoredLead[];
  // Set when a trial upload got capped to fewer rows than the file
  // contained (see backend/app/routers/leads.py's TRIAL_MAX_LEADS_PER_UPLOAD).
  trialLimitedRows: number | null;
  trialTotalRows: number | null;
}

export async function uploadLeads(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/leads/upload`, { method: "POST", headers: authHeaders(), body: form });
  const leads = await handle<ScoredLead[]>(res);
  const limitedRows = res.headers.get("X-Trial-Limited-Rows");
  const totalRows = res.headers.get("X-Trial-Total-Rows");
  return {
    leads,
    trialLimitedRows: limitedRows ? Number(limitedRows) : null,
    trialTotalRows: totalRows ? Number(totalRows) : null,
  };
}

export async function fetchLeads(): Promise<ScoredLead[]> {
  const res = await fetch(`${BASE}/leads`, { headers: authHeaders() });
  return handle(res);
}

export async function pushToCrm(
  leadId: string,
  crm: string
): Promise<{ status: string; detail: string }> {
  const res = await fetch(`${BASE}/leads/${leadId}/crm-push?crm=${crm}`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handle(res);
}

// Deployment-wide on a self-hosted install; on the hosted deployment it
// reports the current workspace's own trial/subscription, hence the header.
export async function fetchLicenseStatus(): Promise<LicenseStatus> {
  const res = await fetch(`${BASE}/license`, { headers: authHeaders() });
  return handle(res);
}

// Hosted deployment only: stops future charges; the workspace keeps its plan
// until access_until (epoch seconds), the end of the period already paid for.
export async function cancelWorkspaceSubscription(): Promise<{ status: "cancelled"; access_until: number | null }> {
  const res = await fetch(`${BASE}/billing/subscription/cancel`, { method: "POST", headers: authHeaders() });
  return handle(res);
}

// Hosted deployment only: a private Starter workspace, no signup needed.
export async function startFreeTrial(): Promise<TenantAuth> {
  const res = await fetch(`${BASE}/accounts/trial`, { method: "POST" });
  return handle(res);
}

export async function fetchBillingConfig(): Promise<BillingConfig> {
  const res = await fetch(`${BASE}/billing/config`);
  return handle(res);
}

// Short-lived token Braintree's Drop-in needs to tokenize the buyer's card.
export async function fetchBraintreeClientToken(): Promise<string> {
  const res = await fetch(`${BASE}/billing/braintree/client-token`);
  const body = await handle<{ client_token: string }>(res);
  return body.client_token;
}

// Sends the tokenized card (never the card number itself) to start the
// subscription. Returns the license key; "duplicate" means a webhook got
// there first and the key arrives by email instead.
export async function subscribeWithBraintree(request: SubscribeRequest): Promise<SubscriptionActivation> {
  // The workspace header lets the hosted deployment upgrade that workspace.
  const res = await fetch(`${BASE}/billing/braintree/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(request),
  });
  return handle(res);
}

// Self-serve workspace signup/login -- an alternative to the seller
// manually running scripts/create_tenant.py. None of these send the tenant
// Authorization header (there's no tenant yet to authenticate as).
export async function signup(name: string, email: string, password: string): Promise<TenantAuth> {
  const res = await fetch(`${BASE}/accounts/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  return handle(res);
}

export async function login(email: string, password: string): Promise<TenantAuth> {
  const res = await fetch(`${BASE}/accounts/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handle(res);
}

export async function forgotPassword(email: string): Promise<{ detail: string }> {
  const res = await fetch(`${BASE}/accounts/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return handle(res);
}

export async function resetPassword(token: string, password: string): Promise<TenantAuth> {
  const res = await fetch(`${BASE}/accounts/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  return handle(res);
}

// Account settings for the signed-in workspace (404 on the self-hosted
// default workspace, which isn't an account).
export async function fetchAccount(): Promise<Account> {
  const res = await fetch(`${BASE}/accounts/me`, { headers: authHeaders() });
  return handle(res);
}

export async function renameAccount(name: string): Promise<{ name: string }> {
  const res = await fetch(`${BASE}/accounts/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name }),
  });
  return handle(res);
}

// Returns a fresh key -- the old one (and any other device) is signed out.
export async function changePassword(currentPassword: string, newPassword: string): Promise<TenantAuth> {
  const res = await fetch(`${BASE}/accounts/me/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return handle(res);
}

// Permanent. Cancels any paid subscription first; password is null for a
// free-trial workspace, which has no login.
export async function deleteAccount(password: string | null): Promise<{ status: "deleted" }> {
  const res = await fetch(`${BASE}/accounts/me`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ password }),
  });
  return handle(res);
}
