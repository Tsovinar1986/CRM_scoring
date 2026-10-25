import { useEffect, useState } from "react";
import { fetchLicenseStatus, getTenantApiKey } from "../api";
import { useI18n } from "../i18n";
import { isNativeApp } from "../nativeApp";
import type { LicenseStatus, ScoredLead } from "../types";

interface Step {
  label: string;
  hint: string;
  done: boolean;
  // In-page anchor for the section that completes this step.
  href?: string;
  action?: string;
}

interface Props {
  leads: ScoredLead[];
  onSelectLead: (lead: ScoredLead) => void;
}

// A signed-in workspace's home: a welcome line, a setup checklist with a
// progress bar (signup -> first upload -> first CRM push -> paid plan), and
// the few hot leads still waiting to be acted on. Once every step is done the
// checklist steps aside and only the "act on these" list remains.
export function GettingStarted({ leads, onSelectLead }: Props) {
  const { t } = useI18n();
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const hasWorkspace = Boolean(getTenantApiKey());

  useEffect(() => {
    if (!hasWorkspace) return;
    fetchLicenseStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [hasWorkspace]);

  if (!hasWorkspace || !status) return null;

  const steps: Step[] = [
    { label: t("start.createWorkspace"), hint: t("start.signedIn"), done: true },
    {
      label: t("start.uploadFirst"),
      hint: t("start.uploadHint"),
      done: leads.length > 0,
      href: "#upload",
      action: t("start.uploadAction"),
    },
    {
      label: t("start.pushLead"),
      hint: t("start.pushHint"),
      done: leads.some((l) => l.crm_pushed),
    },
    // The native apps don't sell plans (store billing rules).
    ...(isNativeApp()
      ? []
      : [
          {
            label: t("start.upgrade"),
            hint: t("start.upgradeHint"),
            done: status.licensed,
            href: "#plans",
            action: t("start.seePlans"),
          },
        ]),
  ];
  const doneCount = steps.filter((s) => s.done).length;
  const complete = doneCount === steps.length;
  const progress = Math.round((doneCount / steps.length) * 100);

  const toActOn = leads
    .filter((l) => l.bucket === "hot" && !l.crm_pushed)
    .sort((a, b) => b.combined_score - a.combined_score)
    .slice(0, 3);

  if (complete && toActOn.length === 0) return null;

  return (
    <div className="rounded-xl border border-border bg-panel p-5 shadow-sm">
      <h2 className="font-display text-lg font-semibold text-heading">
        {status.customer_email ? t("start.welcomeEmail", { email: status.customer_email }) : t("start.welcome")}
      </h2>

      {!complete && (
        <>
          <div className="mt-3 max-w-sm">
            <div className="mb-1 flex justify-between text-xs text-text/75">
              <span>{t("start.setup")}</span>
              <span className="tabular-nums">{t("start.progress", { done: doneCount, total: steps.length })}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          <ol className="mt-4 grid gap-2 sm:grid-cols-2">
            {steps.map((step, i) => (
              <li
                key={step.label}
                className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 ${
                  step.done ? "border-border bg-bg" : "border-accent/40 bg-accent-soft"
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                    step.done ? "bg-accent text-white" : "border border-accent text-accent"
                  }`}
                >
                  {step.done ? "✓" : i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className={`text-sm font-medium ${step.done ? "text-text/60 line-through" : "text-heading"}`}>
                    {step.label}
                    <span className="sr-only">{step.done ? t("start.done") : ""}</span>
                  </div>
                  {!step.done && <div className="text-xs text-text/75">{step.hint}</div>}
                </div>
                {!step.done && step.href && (
                  <a href={step.href} className="shrink-0 text-xs font-medium text-accent hover:underline">
                    {step.action}
                  </a>
                )}
              </li>
            ))}
          </ol>
        </>
      )}

      {toActOn.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-medium text-heading">{t("start.hotToActOn")}</h3>
          <ul className="mt-2 divide-y divide-border">
            {toActOn.map((lead) => (
              <li key={lead.id}>
                <button
                  type="button"
                  onClick={() => onSelectLead(lead)}
                  className="flex w-full items-center justify-between gap-3 py-2 text-left hover:text-heading"
                >
                  <span className="min-w-0 truncate text-sm">
                    <span className="font-medium text-heading">{lead.company_name}</span>{" "}
                    <span className="text-text/60">{lead.domain}</span>
                  </span>
                  <span className="shrink-0 rounded-md bg-hot-soft px-2 py-0.5 text-xs font-semibold tabular-nums text-hot">
                    {Math.round(lead.combined_score)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
