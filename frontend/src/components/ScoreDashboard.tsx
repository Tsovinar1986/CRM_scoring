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

const DIMENSION_LABELS: Record<keyof ScoreBreakdown, string> = {
  industry_match: "Industry fit",
  company_size_fit: "Company size fit",
  revenue_fit: "Revenue fit",
  tech_stack_match: "Tech stack match",
  geography_fit: "Geography fit",
  hiring_signal: "Hiring signal",
};

const DIMENSION_ORDER = Object.keys(DIMENSION_MAX) as (keyof ScoreBreakdown)[];

// Matches backend/app/config.py's BUCKET_THRESHOLDS.
const HOT_CUTOFF = 75;
const WARM_CUTOFF = 50;

const BUCKETS = [
  { key: "hot", label: "Hot", color: "var(--color-chart-hot)" },
  { key: "warm", label: "Warm", color: "var(--color-chart-warm)" },
  { key: "cold", label: "Cold", color: "var(--color-chart-cold)" },
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
  if (leads.length === 0) return null;

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
    label: DIMENSION_LABELS[key],
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
      <h2 className="font-display text-lg font-semibold text-heading">Scoring overview</h2>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile label="Total leads" value={String(total)} />
        <KpiTile label="Hot" value={String(hot)} sub={`${pct(hot, total)}%`} swatch="var(--color-chart-hot)" />
        <KpiTile label="Warm" value={String(warm)} sub={`${pct(warm, total)}%`} swatch="var(--color-chart-warm)" />
        <KpiTile label="Cold" value={String(cold)} sub={`${pct(cold, total)}%`} swatch="var(--color-chart-cold)" />
        <KpiTile label="Avg score" value={avgCombined.toFixed(0)} sub="/ 100" />
        <KpiTile label="Avg account fit" value={`${avgAccountFit.toFixed(0)}%`} sub="LLM" />
      </div>

      <div className="mt-6 grid gap-x-8 gap-y-6 lg:grid-cols-[auto_1fr]">
        <figure>
          <figcaption className="text-sm font-medium text-heading">Lead mix</figcaption>
          <div className="mt-3">
            <DonutChart slices={slices} centerLabel="leads" />
          </div>
        </figure>

        <figure className="min-w-0">
          <figcaption className="text-sm font-medium text-heading">Average score breakdown</figcaption>
          <p className="text-xs text-text/70">Points per dimension, averaged across this batch.</p>
          <div className="mt-3">
            <BarChart bars={bars} color="var(--color-accent)" />
          </div>
        </figure>
      </div>

      <figure className="mt-6 min-w-0">
        <figcaption className="text-sm font-medium text-heading">Scores ranked</figcaption>
        <p className="text-xs text-text/70">Every lead from best to worst — see where the batch drops below each cutoff.</p>
        <div className="mt-3">
          <RankedLineChart
            points={ranked}
            color="var(--color-accent)"
            thresholds={[
              { label: `Hot ≥ ${HOT_CUTOFF}`, value: HOT_CUTOFF, color: "var(--color-chart-hot)" },
              { label: `Warm ≥ ${WARM_CUTOFF}`, value: WARM_CUTOFF, color: "var(--color-chart-warm)" },
            ]}
          />
        </div>
      </figure>
    </div>
  );
}
