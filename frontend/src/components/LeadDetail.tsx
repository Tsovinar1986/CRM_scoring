import { useState } from "react";
import { pushToCrm } from "../api";
import { useI18n, type Translate } from "../i18n";
import type { MessageKey } from "../locales/en";
import type { ScoredLead } from "../types";

interface Props {
  lead: ScoredLead;
  onClose: () => void;
  onUpdate: (lead: ScoredLead) => void;
}

const BREAKDOWN_LABELS: Record<string, MessageKey> = {
  industry_match: "dim.industry_match",
  company_size_fit: "dim.company_size_fit",
  revenue_fit: "dim.revenue_fit",
  tech_stack_match: "dim.tech_stack_match",
  geography_fit: "dim.geography_fit",
  hiring_signal: "dim.hiring_signal",
};

// Which CRM/enrichment field each score row is actually computed from --
// mirrors backend/app/services/scoring.py's score_lead() exactly, so a
// buyer can see *why* a number is what it is, not just that it is.
function breakdownSource(key: string, lead: ScoredLead, t: Translate): string {
  switch (key) {
    case "industry_match":
      return `${t("lead.industry")}: ${lead.industry || "—"}`;
    case "company_size_fit":
      return `${t("lead.employees")}: ${lead.employee_count != null ? lead.employee_count.toLocaleString() : "—"}`;
    case "revenue_fit":
      return `${t("lead.revenue")}: ${lead.revenue_usd != null ? `$${lead.revenue_usd.toLocaleString()}` : "—"}`;
    case "tech_stack_match":
      return `${t("lead.techStack")}: ${lead.tech_stack.length ? lead.tech_stack.join(", ") : "—"}`;
    case "geography_fit":
      return `${t("lead.geography")}: ${lead.geography || "—"}`;
    case "hiring_signal":
      return `${t("lead.hiring")}: ${t(lead.is_hiring ? "lead.yes" : "lead.no")}`;
    default:
      return "";
  }
}

const BAR_CLASSES: Record<string, string> = {
  hot: "bg-hot",
  warm: "bg-warm",
  cold: "bg-cold",
};

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function LeadDetail({ lead, onClose, onUpdate }: Props) {
  const { t } = useI18n();
  const [busy, setBusy] = useState<"crm" | null>(null);
  const [crmStatus, setCrmStatus] = useState<string | null>(null);

  async function handleCrmPush() {
    setBusy("crm");
    try {
      const res = await pushToCrm(lead.id, "salesforce");
      setCrmStatus(res.detail);
      onUpdate({ ...lead, crm_pushed: true });
    } finally {
      setBusy(null);
    }
  }

  const badgeClass =
    lead.bucket === "hot" ? "bg-hot-soft text-hot" : lead.bucket === "warm" ? "bg-warm-soft text-warm" : "bg-cold-soft text-cold";

  return (
    <div
      className="animate-scrim-in fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="animate-drawer-in relative flex h-full w-full max-w-[480px] flex-col overflow-y-auto bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-border bg-gradient-to-b from-accent-soft/60 to-transparent px-7 pb-5 pt-7">
          <button
            className="absolute right-6 top-6 rounded-md p-1.5 text-text/75 transition-colors hover:bg-border/60 hover:text-heading"
            onClick={onClose}
            aria-label={t("common.close")}
          >
            <CloseIcon className="h-5 w-5" />
          </button>
          <h2 className="font-display pr-10 text-2xl font-semibold leading-tight text-heading">
            {lead.company_name}
          </h2>
          <p className="mt-1 text-sm text-text/75">{lead.domain}</p>
          <span
            className={`mt-3 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${badgeClass}`}
          >
            {t(`bucket.${lead.bucket}` as MessageKey).toUpperCase()}
          </span>
        </div>

        <div className="flex-1 px-7 pb-7">
          <section>
            <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-text/70">{t("lead.firmographics")}</h3>
            <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 gap-x-2.5 text-sm">
              <dt className="text-text/75">{t("lead.industry")}</dt>
              <dd className="text-heading">{lead.industry}</dd>
              <dt className="text-text/75">{t("lead.employees")}</dt>
              <dd className="text-heading">{lead.employee_count?.toLocaleString()}</dd>
              <dt className="text-text/75">{t("lead.revenue")}</dt>
              <dd className="text-heading">{lead.revenue_usd ? `$${lead.revenue_usd.toLocaleString()}` : "—"}</dd>
              <dt className="text-text/75">{t("lead.geography")}</dt>
              <dd className="text-heading">{lead.geography}</dd>
              <dt className="text-text/75">{t("lead.contact")}</dt>
              <dd className="text-heading">
                {lead.contact_name} ({lead.contact_title})
              </dd>
              <dt className="text-text/75">{t("lead.techStack")}</dt>
              <dd className="text-heading">{lead.tech_stack.join(", ") || "—"}</dd>
              <dt className="text-text/75">{t("lead.hiring")}</dt>
              <dd className="text-heading">{t(lead.is_hiring ? "lead.yes" : "lead.no")}</dd>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-text/70">{t("lead.scoreBreakdown")}</h3>
            <div className="flex flex-col gap-2.5">
              {Object.entries(lead.score_breakdown).map(([key, value], i) => (
                <div className="grid grid-cols-[130px_1fr_30px] items-start gap-2 text-xs" key={key}>
                  <div className="flex flex-col">
                    <span className="text-text">{BREAKDOWN_LABELS[key] ? t(BREAKDOWN_LABELS[key]) : key}</span>
                    <span className="text-[11px] text-text/60">{breakdownSource(key, lead, t)}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-border">
                    <div
                      className={`animate-grow-x h-full origin-left rounded-full ${BAR_CLASSES[lead.bucket]}`}
                      style={{
                        width: `${Math.min(100, (value / 20) * 100)}%`,
                        animationDelay: `${i * 60}ms`,
                      }}
                    />
                  </div>
                  <span className="mt-1 tabular-nums text-text/75">{value}</span>
                </div>
              ))}
            </div>
            <p className="mt-3 rounded-lg bg-bg px-3 py-2.5 text-sm text-text">
              {t("lead.fitScore")} <strong className="text-heading">{lead.fit_score}</strong> · {t("lead.accountFit")}{" "}
              <strong className="text-heading">{lead.account_fit_score}</strong> · {t("lead.combined")}{" "}
              <strong className="text-heading">{lead.combined_score}</strong>
            </p>
          </section>

          <section>
            <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-text/70">{t("lead.rationale")}</h3>
            <p className="text-sm leading-relaxed text-text">{lead.llm_rationale}</p>
          </section>

          <section>
            <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-text/70">{t("lead.crm")}</h3>
            <button
              className="rounded-md border border-accent/40 bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent transition-all hover:-translate-y-px hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
              disabled={busy === "crm"}
              onClick={handleCrmPush}
            >
              {busy === "crm" ? t("lead.pushing") : lead.crm_pushed ? t("lead.pushAgain") : t("lead.push")}
            </button>
            {crmStatus && <p className="mt-2 text-sm text-text/75">{crmStatus}</p>}
          </section>
        </div>
      </div>
    </div>
  );
}
