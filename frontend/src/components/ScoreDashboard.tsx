import { useState } from "react";
import { dashboardStats, DIMENSION_LABELS, HOT_CUTOFF, pct, WARM_CUTOFF } from "../dashboardData";
import { useI18n } from "../i18n";
import type { ScoredLead } from "../types";
import { BarChart, DonutChart, RankedLineChart } from "./charts";

const BUCKET_STYLES = [
  { key: "hot", label: "bucket.hot", color: "var(--color-chart-hot)" },
  { key: "warm", label: "bucket.warm", color: "var(--color-chart-warm)" },
  { key: "cold", label: "bucket.cold", color: "var(--color-chart-cold)" },
] as const;

interface KpiTileProps {
  label: string;
  value: string;
  sub?: string;
  // Bucket identity rides a swatch beside the label; the number stays in text ink.
  swatch?: string;
}

function KpiTile({ label, value, sub, swatch }: KpiTileProps) {
  return (
    <div className="rounded-lg border border-border bg-bg px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-xs text-text/75">
        {swatch && <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ backgroundColor: swatch }} />}
        {label}
      </div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className="font-display text-xl font-semibold text-heading">{value}</span>
        {sub && <span className="text-xs text-text/60">{sub}</span>}
      </div>
    </div>
  );
}

interface Props {
  leads: ScoredLead[];
}

// Shown right after scoring (App.tsx, between UploadPanel and LeadsTable):
// KPI tiles for the headline numbers, then one chart per question -- what's
// the Hot/Warm/Cold mix (donut), which scoring dimensions are strong or weak
// (bars), and how fast quality drops off down the ranked list (line).
export function ScoreDashboard({ leads }: Props) {
  const { t, lang } = useI18n();
  const [exporting, setExporting] = useState(false);
  const [exportFailed, setExportFailed] = useState(false);
  if (leads.length === 0) return null;
  const BUCKETS = BUCKET_STYLES.map((b) => ({ ...b, label: t(b.label) }));

  const { total, hot, warm, cold, avgCombined, avgAccountFit, dimensions, ranked: byScore } = dashboardStats(leads);
  const count = (bucket: string) => leads.filter((l) => l.bucket === bucket).length;
  const slices = BUCKETS.map((b) => ({ ...b, value: count(b.key) }));
  const bars = dimensions.map((d) => ({ key: d.key, label: t(DIMENSION_LABELS[d.key]), value: d.value, max: d.max }));
  const bucketOf = (b: string) => BUCKETS.find((x) => x.key === b) ?? BUCKETS[2];
  const ranked = byScore.map((l) => ({
    id: l.id,
    label: l.company_name,
    value: l.combined_score,
    bucketLabel: bucketOf(l.bucket).label,
    bucketColor: bucketOf(l.bucket).color,
  }));

  async function downloadDeck() {
    setExporting(true);
    setExportFailed(false);
    try {
      const { downloadDashboardDeck } = await import("../dashboardExport");
      await downloadDashboardDeck(leads, t, lang);
    } catch {
      setExportFailed(true);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-panel p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold text-heading">{t("dash.title")}</h2>
        <button
          type="button"
          className="rounded-full border border-border px-3 py-1 text-xs font-medium text-text transition-all hover:-translate-y-px hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
          disabled={exporting}
          onClick={downloadDeck}
        >
          {exporting ? t("dash.preparing") : t("dash.downloadPptx")}
        </button>
      </div>
      {exportFailed && (
        <p role="alert" className="mt-2 text-xs text-accent">
          {t("dash.downloadFailed")}
        </p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile label={t("dash.totalLeads")} value={String(total)} />
        <KpiTile label={t("bucket.hot")} value={String(hot)} sub={`${pct(hot, total)}%`} swatch="var(--color-chart-hot)" />
        <KpiTile label={t("bucket.warm")} value={String(warm)} sub={`${pct(warm, total)}%`} swatch="var(--color-chart-warm)" />
        <KpiTile label={t("bucket.cold")} value={String(cold)} sub={`${pct(cold, total)}%`} swatch="var(--color-chart-cold)" />
        <KpiTile label={t("dash.avgScore")} value={avgCombined.toFixed(0)} sub="/ 100" />
        <KpiTile label={t("dash.avgAccountFit")} value={`${avgAccountFit.toFixed(0)}%`} sub="LLM" />
      </div>

      <div className="mt-6 grid gap-x-8 gap-y-6 lg:grid-cols-[auto_1fr]">
        <figure>
          <figcaption className="text-sm font-medium text-heading">{t("dash.leadMix")}</figcaption>
          <div className="mt-3">
            <DonutChart slices={slices} centerLabel={t("dash.leads")} />
          </div>
        </figure>

        <figure className="min-w-0">
          <figcaption className="text-sm font-medium text-heading">{t("dash.avgBreakdown")}</figcaption>
          <p className="text-xs text-text/70">{t("dash.avgBreakdownSub")}</p>
          <div className="mt-3">
            <BarChart bars={bars} color="var(--color-chart-series)" />
          </div>
        </figure>
      </div>

      <figure className="mt-6 min-w-0">
        <figcaption className="text-sm font-medium text-heading">{t("dash.ranked")}</figcaption>
        <p className="text-xs text-text/70">{t("dash.rankedSub")}</p>
        <div className="mt-3">
          <RankedLineChart
            points={ranked}
            color="var(--color-chart-series)"
            thresholds={[
              { label: t("dash.cutoff", { bucket: t("bucket.hot"), value: HOT_CUTOFF }), value: HOT_CUTOFF, color: "var(--color-chart-hot)" },
              { label: t("dash.cutoff", { bucket: t("bucket.warm"), value: WARM_CUTOFF }), value: WARM_CUTOFF, color: "var(--color-chart-warm)" },
            ]}
          />
        </div>
      </figure>
    </div>
  );
}
