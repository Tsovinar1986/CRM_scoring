import { useEffect, useState } from "react";
import {
  cancelWorkspaceSubscription,
  fetchBillingConfig,
  fetchLicenseStatus,
  getTenantApiKey,
  setTenantApiKey,
  startFreeTrial,
} from "../api";
import type { BillingConfig, BillingInterval, LicenseStatus, PaidTier } from "../types";
import { useI18n } from "../i18n";
import { isNativeApp } from "../nativeApp";
import { Subscribe } from "./Subscribe";

type Selection = { tier: PaidTier; interval: BillingInterval };

const btnPrimary =
  "rounded-md bg-accent px-4 py-2 text-sm font-medium text-white shadow-sm transition-all hover:-translate-y-px hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-sm";
const btnSecondary =
  "rounded-md border border-accent/40 bg-accent-soft px-4 py-2 text-sm font-medium text-accent transition-all hover:-translate-y-px hover:bg-accent/20 active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0";

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 8v4.5l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AlertIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M10.9 4.6 2.9 18a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3l-8-13.4a2 2 0 0 0-3.4 0Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M12 10v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" />
    </svg>
  );
}

function CheckBadgeIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="m9 12 2 2 4-4M12 3.5l1.9 1.1 2.2-.2 1.1 1.9 1.9 1.1-.2 2.2 1.1 1.9-1.9 1.1-1.1 1.9-2.2-.2L12 14.5l-1.9-1.1-2.2.2-1.1-1.9-1.9-1.1.2-2.2-1.1-1.9 1.9-1.1 1.1-1.9 2.2.2Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface Props {
  // Called after a free trial starts or a workspace is upgraded, so the app
  // reloads the workspace (and this banner) with the new state.
  onWorkspaceChange?: () => void;
}

export function LicenseBanner({ onWorkspaceChange }: Props = {}) {
  const { t, lang } = useI18n();
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [billing, setBilling] = useState<BillingConfig | null>(null);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [startingTrial, setStartingTrial] = useState(false);
  const [trialError, setTrialError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  async function cancelSubscription() {
    if (!window.confirm(t("banner.confirmCancel"))) {
      return;
    }
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelWorkspaceSubscription();
      onWorkspaceChange?.();
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : t("banner.errCancel"));
    } finally {
      setCancelling(false);
    }
  }

  async function beginTrial() {
    setStartingTrial(true);
    setTrialError(null);
    try {
      const auth = await startFreeTrial();
      setTenantApiKey(auth.api_key);
      onWorkspaceChange?.();
    } catch (err) {
      setTrialError(err instanceof Error ? err.message : t("auth.errTrial"));
      setStartingTrial(false);
    }
  }

  useEffect(() => {
    fetchLicenseStatus()
      .then(setStatus)
      .catch(() =>
        setStatus({
          licensed: false,
          reason: "trial",
          customer_email: null,
          plan: null,
          tier: "starter",
          trial_uploads_left: null,
        })
      );
    fetchBillingConfig()
      .then(setBilling)
      .catch(() => setBilling({ checkout_available: false, environment: "test" }));
  }, []);

  function isSelected(tier: PaidTier, interval: BillingInterval) {
    return selected?.tier === tier && selected.interval === interval;
  }

  if (status === null) return null;

  // On a self-hosted install the license belongs to whoever runs it, not to
  // a self-serve workspace using it -- those never see license messaging.
  // The hosted deployment reports each workspace's own plan, so show it.
  if (!status.hosted && getTenantApiKey()) return null;

  if (!status.licensed && status.reason === "no_workspace") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/30 bg-accent-soft px-5 py-4 text-sm shadow-sm">
        <div>
          <p className="font-medium text-heading">{t("banner.tryFree")}</p>
          <p className="text-text/80">{t("banner.tryFreeText")}</p>
          {trialError && <p className="mt-1 text-hot">{trialError}</p>}
        </div>
        <button className={btnPrimary} disabled={startingTrial} onClick={beginTrial}>
          {startingTrial ? t("banner.starting") : t("auth.startTrial")}
        </button>
      </div>
    );
  }

  if (status.licensed) {
    // A hosted workspace's own subscription: expires_at is only set once it
    // was cancelled (access runs to the end of the paid period).
    const hostedSubscription = status.hosted && status.plan === "subscription";
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-panel px-5 py-3 text-sm shadow-sm">
        <CheckBadgeIcon className="h-4 w-4 shrink-0 text-accent" />
        <span className="text-text">
          {t("banner.licensedTo", { email: status.customer_email ?? "", tier: status.tier })}
          {status.expires_at && (
            <span className="text-text/75">
              {t(hostedSubscription ? "banner.cancelledUntil" : "banner.renews", {
                date: new Date(status.expires_at * 1000).toLocaleDateString(lang),
              })}
            </span>
          )}
        </span>
        {hostedSubscription && !status.expires_at && (
          <button
            className="ml-auto text-xs text-text/70 underline hover:text-heading disabled:opacity-50"
            disabled={cancelling}
            onClick={cancelSubscription}
          >
            {cancelling ? t("banner.cancelling") : t("banner.cancelSubscription")}
          </button>
        )}
        {cancelError && <p className="w-full text-hot">{cancelError}</p>}
      </div>
    );
  }

  // A buyer who already paid but has a stale/expired key must never see the
  // same "you're on a trial" copy as someone who's never purchased -- that
  // reads as "your payment didn't go through" and risks a double-charge.
  // Someone whose free trial window has simply run out (never paid) also
  // needs its own copy, distinct from "still evaluating."
  const native = isNativeApp();
  const { message, showBuyButtons } =
    native
      ? // The native apps don't sell plans (store billing rules), so no buy buttons or upgrade prompts.
        {
          message:
            status.reason === "expired"
              ? t("banner.expiredNative")
              : status.reason === "invalid"
                ? t("banner.invalidNative")
                : status.reason === "trial_expired"
                  ? t("banner.trialEndedNative")
                  : status.trial_uploads_left != null
                    ? t("banner.starterLeftNative", { n: status.trial_uploads_left })
                    : t("banner.starterTier"),
          showBuyButtons: false,
        }
      : status.reason === "expired"
      ? {
          message: status.customer_email ? t("banner.expiredFor", { email: status.customer_email }) : t("banner.expired"),
          showBuyButtons: true,
        }
      : status.reason === "invalid"
        ? {
            message: t("banner.invalid"),
            showBuyButtons: false,
          }
        : status.reason === "trial_expired"
          ? {
              message: status.hosted ? t("banner.trialEndedHosted") : t("banner.trialEnded"),
              showBuyButtons: true,
            }
          : {
              message:
                status.trial_uploads_left != null
                  ? t("banner.starterLeft", { n: status.trial_uploads_left })
                  : t("banner.starterTier"),
              showBuyButtons: true,
            };

  const isError = status.reason === "invalid" || status.reason === "trial_expired";

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-5 py-3 text-sm shadow-sm ${
        isError ? "border-hot/30 bg-hot-soft text-hot" : "border-warm/30 bg-warm-soft text-warm"
      }`}
    >
      <span className="flex items-center gap-2.5">
        {isError ? (
          <AlertIcon className="h-4 w-4 shrink-0" />
        ) : (
          <ClockIcon className="h-4 w-4 shrink-0" />
        )}
        {message}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        {showBuyButtons && (
          <>
            <button className={btnPrimary} aria-pressed={isSelected("pro", "monthly")} onClick={() => setSelected({ tier: "pro", interval: "monthly" })}>
              {t("banner.proMonthly")}
            </button>
            <button className={btnPrimary} aria-pressed={isSelected("pro", "annual")} onClick={() => setSelected({ tier: "pro", interval: "annual" })}>
              {t("banner.proAnnual")}
            </button>
            <button
              className={btnSecondary}
              aria-pressed={isSelected("advanced", "monthly")}
              onClick={() => setSelected({ tier: "advanced", interval: "monthly" })}
            >
              {t("banner.advancedMonthly")}
            </button>
            <button
              className={btnSecondary}
              aria-pressed={isSelected("advanced", "annual")}
              onClick={() => setSelected({ tier: "advanced", interval: "annual" })}
            >
              {t("banner.advancedAnnual")}
            </button>
            {billing?.checkout_available && <span className="text-xs text-text/70">{t("banner.secureCheckout")}</span>}
          </>
        )}
      </div>
      {showBuyButtons && selected && billing && (
        <Subscribe
          key={`${selected.tier}-${selected.interval}`}
          config={billing}
          tier={selected.tier}
          interval={selected.interval}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
