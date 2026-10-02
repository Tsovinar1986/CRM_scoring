export interface ScoreBreakdown {
  industry_match: number;
  company_size_fit: number;
  revenue_fit: number;
  tech_stack_match: number;
  geography_fit: number;
  hiring_signal: number;
}

export interface ScoredLead {
  id: string;
  company_name: string;
  domain: string;
  contact_name: string | null;
  contact_title: string | null;
  industry: string | null;
  employee_count: number | null;
  revenue_usd: number | null;
  geography: string | null;
  source: string;
  tech_stack: string[];
  is_hiring: boolean;
  enrichment_source: string;
  fit_score: number;
  score_breakdown: ScoreBreakdown;
  account_fit_score: number;
  llm_rationale: string;
  combined_score: number;
  bucket: "hot" | "warm" | "cold";
  crm_pushed: boolean;
}

export type LicenseTier = "starter" | "pro" | "advanced";

// hosted: the seller's public deployment (backend HOSTED_MODE), where each
// visitor gets a private free-trial workspace instead of the default one.
export type LicenseStatus = { hosted?: boolean } & (
  | {
      licensed: false;
      // no_workspace: hosted deployment, visitor hasn't started a trial yet.
      reason: "trial" | "trial_expired" | "invalid" | "expired" | "no_workspace";
      customer_email: string | null;
      plan: string | null;
      tier: LicenseTier;
      trial_uploads_left: number | null;
    }
  | { licensed: true; customer_email: string; plan: string; tier: LicenseTier; expires_at: number | null }
);

export type BillingInterval = "monthly" | "annual";
export type PlanTier = "starter" | "pro" | "advanced";

export type PaidTier = "pro" | "advanced";
export type PlanKey = `${PaidTier}_${BillingInterval}`;

export interface BillingConfig {
  checkout_available: boolean;
  // Braintree plan id per paid tier/interval. Starter is free.
  plans?: Partial<Record<PlanKey, string | null>>;
  currency?: string;
  environment: "sandbox" | "production";
  price_monthly?: string | null;
  price_annual?: string | null;
  price_advanced_monthly?: string | null;
  price_advanced_annual?: string | null;
}

export interface SubscribeRequest {
  tier: PaidTier;
  interval: BillingInterval;
  // Optional -- checkout doesn't ask for it; renewal keys are emailed only if set.
  email?: string;
  // From Braintree Drop-in's requestPaymentMethod() -- a one-time token for
  // the card, never the card details themselves.
  payment_method_nonce: string;
  device_data?: string;
}

export type SubscriptionActivation =
  | {
      status: "ok";
      email: string;
      tier: PaidTier;
      plan: BillingInterval;
      license_key: string;
      // Hosted deployment: the buyer's own workspace was upgraded in place.
      workspace_upgraded?: boolean;
    }
  | { status: "duplicate" };

export interface TenantAuth {
  tenant_id: string;
  name: string;
  api_key: string;
}

export interface Account {
  name: string;
  email: string | null;
  // null = unmetered (provisioned by the seller); "starter" = free tier.
  plan: PlanTier | null;
  created_at: number;
  uploads_used: number;
  uploads_limit: number | null;
  has_subscription: boolean;
  // Set once a cancelled subscription is running out its paid period.
  plan_expires_at: number | null;
  has_password: boolean;
}
