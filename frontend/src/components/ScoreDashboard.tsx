import { useI18n } from "../i18n";
import type { MessageKey } from "../locales/en";
import type { ScoreBreakdown, ScoredLead } from "../types";
import { BarChart, DonutChart, RankedLineChart } from "./charts";

// Matches backend/app/config.py's SCORING_WEIGHTS -- each dimension's raw
// score_breakdown value is out of this max, not out of 100, so a bar's fill
// is normalized to percent-of-its-own-max rather than compared on a shared
// 0-100 scale it was never scored on.
const DIMENSION_MAX: Record<keyof ScoreBreakdown, number> = {
  industry_match: 25,
  company_size_fit: 25,
  revenue_fit: 15,
  tech_stack_match: 15,
  geography_fit: 10,
  hiring_signal: 10,
};

const DIMENSION_LABELS: Record<keyof ScoreBreakdown, MessageKey> = {
  industry_match: "dim.industry_match",
  company_size_fit: "dim.company_size_fit",
  revenue_fit: "dim.revenue_fit",
  tech_stack_match: "dim.tech_stack_match",
  geography_fit: "dim.geography_fit",
  hiring_signal: "dim.hiring_signal",
};

const DIMENSION_ORDER = Object.keys(DIMENSION_MAX) as (keyof ScoreBreakdown)[];

// Matches backend/app/config.py's BUCKET_THRESHOLDS.
const HOT_CUTOFF = 75;
const WARM_CUTOFF = 50;

const BUCKET_STYLES = [
  { key: "hot", label: "bucket.hot", color: "var(--color-chart-hot)" },
  { key: "warm", label: "bucket.warm", color: "var(--color-chart-warm)" },
  { key: "cold", label: "bucket.cold", color: "var(--color-chart-cold)" },
] as const;

function pct(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 100);
}

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
  const { t } = useI18n();
  if (leads.length === 0) return null;
  const BUCKETS = BUCKET_STYLES.map((b) => ({ ...b, label: t(b.label) }));

  const total = leads.length;
  const count = (bucket: string) => leads.filter((l) => l.bucket === bucket).length;
  const hot = count("hot");
  const warm = count("warm");
  const cold = count("cold");
  const avgCombined = leads.reduce((sum, l) => sum + l.combined_score, 0) / total;
  const avgAccountFit = leads.reduce((sum, l) => sum + l.account_fit_score, 0) / total;

  const slices = BUCKETS.map((b) => ({ ...b, value: count(b.key) }));
  const bars = DIMENSION_ORDER.map((key) => ({
    key,
    label: t(DIMENSION_LABELS[key]),
    value: leads.reduce((sum, l) => sum + l.score_breakdown[key], 0) / total,
    max: DIMENSION_MAX[key],
  }));
  const bucketOf = (b: string) => BUCKETS.find((x) => x.key === b) ?? BUCKETS[2];
  const ranked = [...leads]
    .sort((a, b) => b.combined_score - a.combined_score)
    .map((l) => ({
      id: l.id,
      label: l.company_name,
      value: l.combined_score,
      bucketLabel: bucketOf(l.bucket).label,
      bucketColor: bucketOf(l.bucket).color,
    }));

  return (
    <div className="rounded-xl border border-border bg-panel p-5 shadow-sm">
      <h2 className="font-display text-lg font-semibold text-heading">{t("dash.title")}</h2>

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
