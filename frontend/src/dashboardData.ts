import type { MessageKey } from "./locales/en";
import type { ScoreBreakdown, ScoredLead } from "./types";

// The numbers behind the scoring overview, shared by the on-screen dashboard
// (components/ScoreDashboard.tsx) and its PowerPoint export (dashboardExport.ts)
// so the two can never disagree.

// Matches backend/app/config.py's SCORING_WEIGHTS -- each dimension's raw
// score_breakdown value is out of this max, not out of 100, so a bar's fill
// is normalized to percent-of-its-own-max rather than compared on a shared
// 0-100 scale it was never scored on.
export const DIMENSION_MAX: Record<keyof ScoreBreakdown, number> = {
  industry_match: 25,
  company_size_fit: 25,
  revenue_fit: 15,
  tech_stack_match: 15,
  geography_fit: 10,
  hiring_signal: 10,
};

export const DIMENSION_LABELS: Record<keyof ScoreBreakdown, MessageKey> = {
  industry_match: "dim.industry_match",
  company_size_fit: "dim.company_size_fit",
  revenue_fit: "dim.revenue_fit",
  tech_stack_match: "dim.tech_stack_match",
  geography_fit: "dim.geography_fit",
  hiring_signal: "dim.hiring_signal",
};

export const DIMENSION_ORDER = Object.keys(DIMENSION_MAX) as (keyof ScoreBreakdown)[];

// Matches backend/app/config.py's BUCKET_THRESHOLDS.
export const HOT_CUTOFF = 75;
export const WARM_CUTOFF = 50;

export function pct(part: number, whole: number): number {
  return whole === 0 ? 0 : Math.round((part / whole) * 100);
}

export interface DashboardStats {
  total: number;
  hot: number;
  warm: number;
  cold: number;
  avgCombined: number;
  avgAccountFit: number;
  /** Average points per dimension, in DIMENSION_ORDER. */
  dimensions: { key: keyof ScoreBreakdown; value: number; max: number }[];
  /** Best to worst by combined score. */
  ranked: ScoredLead[];
}

export function dashboardStats(leads: ScoredLead[]): DashboardStats {
  const total = leads.length;
  const count = (bucket: string) => leads.filter((l) => l.bucket === bucket).length;
  const avg = (get: (l: ScoredLead) => number) => (total === 0 ? 0 : leads.reduce((sum, l) => sum + get(l), 0) / total);
  return {
    total,
    hot: count("hot"),
    warm: count("warm"),
    cold: count("cold"),
    avgCombined: avg((l) => l.combined_score),
    avgAccountFit: avg((l) => l.account_fit_score),
    dimensions: DIMENSION_ORDER.map((key) => ({ key, value: avg((l) => l.score_breakdown[key]), max: DIMENSION_MAX[key] })),
    ranked: [...leads].sort((a, b) => b.combined_score - a.combined_score),
  };
}
