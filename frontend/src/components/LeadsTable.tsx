import { downloadLeadsCsv } from "../csvExport";
import { useI18n } from "../i18n";
import type { MessageKey } from "../locales/en";
import type { ScoredLead } from "../types";

interface Props {
  leads: ScoredLead[];
  selectedId: string | null;
  bucketFilter: "all" | "hot" | "warm" | "cold";
  onSelect: (lead: ScoredLead) => void;
  onBucketFilterChange: (bucket: "all" | "hot" | "warm" | "cold") => void;
}

const BUCKET_LABELS: Record<string, MessageKey> = {
  hot: "bucket.hot",
  warm: "bucket.warm",
  cold: "bucket.cold",
};

const COLUMNS: MessageKey[] = [
  "table.company",
  "table.industry",
  "table.contact",
  "table.fit",
  "table.llm",
  "table.combined",
  "table.bucket",
];

const CHIP_ACTIVE_CLASSES: Record<string, string> = {
  all: "border-accent bg-accent-soft text-accent",
  hot: "border-hot bg-hot-soft text-hot",
  warm: "border-warm bg-warm-soft text-warm",
  cold: "border-cold bg-cold-soft text-cold",
};

const BADGE_CLASSES: Record<string, string> = {
  hot: "bg-hot-soft text-hot",
  warm: "bg-warm-soft text-warm",
  cold: "bg-cold-soft text-cold",
};

const DOT_CLASSES: Record<string, string> = {
  hot: "bg-hot",
  warm: "bg-warm",
  cold: "bg-cold",
};

const BAR_CLASSES: Record<string, string> = {
  hot: "bg-hot",
  warm: "bg-warm",
  cold: "bg-cold",
};

function InboxIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M4 12.5 6.2 5h11.6l2.2 7.5M4 12.5V18a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5.5M4 12.5h4.7a1 1 0 0 1 .95.68L10.35 16h3.3l.7-2.82a1 1 0 0 1 .95-.68H20"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LeadsTable({
  leads,
  selectedId,
  bucketFilter,
  onSelect,
  onBucketFilterChange,
}: Props) {
  const { t } = useI18n();
  const filtered =
    bucketFilter === "all" ? leads : leads.filter((l) => l.bucket === bucketFilter);

  const counts = leads.reduce(
    (acc, l) => {
      acc[l.bucket] = (acc[l.bucket] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  return (
    <div className="rounded-xl border border-border bg-panel p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold text-heading">
          {t("table.ranked", { n: filtered.length })}
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          {(["all", "hot", "warm", "cold"] as const).map((b) => (
            <button
              key={b}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-all hover:-translate-y-px ${
                bucketFilter === b
                  ? CHIP_ACTIVE_CLASSES[b]
                  : "border-border text-text hover:border-accent/40"
              }`}
              onClick={() => onBucketFilterChange(b)}
            >
              {b === "all" ? t("table.all") : t(BUCKET_LABELS[b])}
              {b !== "all" ? ` (${counts[b] ?? 0})` : ""}
            </button>
          ))}
          <button
            className="rounded-full border border-border px-3 py-1 text-xs font-medium text-text transition-all hover:-translate-y-px hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
            disabled={filtered.length === 0}
            onClick={() =>
              downloadLeadsCsv(
                filtered,
                bucketFilter === "all" ? "scored-leads.csv" : `scored-leads-${bucketFilter}.csv`
              )
            }
          >
            {t("table.downloadCsv")}
          </button>
        </div>
      </div>

      {leads.length === 0 ? (
        <div className="mt-6 flex flex-col items-center gap-2 py-8 text-center">
          <InboxIcon className="h-8 w-8 text-text/40" />
          <p className="text-sm text-text/75">{t("table.empty")}</p>
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {COLUMNS.map((h) => (
                  <th
                    key={h}
                    className="whitespace-nowrap border-b border-border px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-text/70"
                  >
                    {t(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((lead) => (
                <tr
                  key={lead.id}
                  className={`cursor-pointer border-l-2 transition-colors hover:bg-accent-soft ${
                    lead.id === selectedId ? "border-l-accent bg-accent-soft" : "border-l-transparent"
                  }`}
                  onClick={() => onSelect(lead)}
                >
                  <td className="border-b border-border px-3 py-3 align-top">
                    <div className="flex flex-col">
                      <strong className="font-medium text-heading">{lead.company_name}</strong>
                      <span className="text-xs text-text/75">{lead.domain}</span>
                    </div>
                  </td>
                  <td className="border-b border-border px-3 py-3 align-top">{lead.industry}</td>
                  <td className="border-b border-border px-3 py-3 align-top">
                    <div className="flex flex-col">
                      <span>{lead.contact_name ?? "—"}</span>
                      <span className="text-xs text-text/75">{lead.contact_title}</span>
                    </div>
                  </td>
                  <td className="border-b border-border px-3 py-3 align-top tabular-nums">
                    {lead.fit_score.toFixed(0)}
                  </td>
                  <td className="border-b border-border px-3 py-3 align-top tabular-nums">
                    {lead.account_fit_score.toFixed(0)}
                  </td>
                  <td className="border-b border-border px-3 py-3 align-top">
                    <div className="flex items-center gap-2">
                      <strong className="tabular-nums font-semibold text-heading">
                        {lead.combined_score.toFixed(0)}
                      </strong>
                      <div className="h-1 w-12 overflow-hidden rounded-full bg-border">
                        <div
                          className={`animate-grow-x h-full origin-left rounded-full ${BAR_CLASSES[lead.bucket]}`}
                          style={{ width: `${Math.min(100, lead.combined_score)}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="border-b border-border px-3 py-3 align-top">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${BADGE_CLASSES[lead.bucket]}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${DOT_CLASSES[lead.bucket]}`} />
                      {t(BUCKET_LABELS[lead.bucket])}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
