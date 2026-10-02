import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

// Small hand-rolled SVG charts for the scoring overview -- three forms, each
// matched to its job: a donut for the Hot/Warm/Cold share (part-to-whole,
// three slices), horizontal bars for per-dimension averages (magnitude), and
// a line for scores ranked best -> worst (shape of the batch). Marks follow
// one spec: 2px lines, bars <= 14px with a 4px rounded data-end, a 2px panel
// gap between touching fills, hairline solid gridlines, and text that always
// wears text tokens (never the series color). Every mark has a hover AND
// keyboard-focus tooltip; every value is also visible as text or in the
// leads table below, so the tooltip never gates anything.

/** Tracks an element's rendered width so SVGs draw at 1:1 instead of scaling text. */
function useWidth(ref: RefObject<HTMLElement | null>, fallback: number): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (el.clientWidth) setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width) setWidth(entry.contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

interface TipState {
  x: number;
  y: number;
  content: ReactNode;
}

// Value leads, label follows; keyed with a short line in the mark's color.
function Tooltip({ tip }: { tip: TipState | null }) {
  if (!tip) return null;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+10px)] whitespace-nowrap rounded-lg border border-border bg-panel px-3 py-2 text-xs shadow-md"
      style={{ left: tip.x, top: tip.y }}
    >
      {tip.content}
    </div>
  );
}

function TipRow({ color, value, label }: { color: string; value: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className="inline-block h-0.5 w-3 rounded-full" style={{ backgroundColor: color }} />
      <span className="font-semibold text-heading">{value}</span>
      <span className="text-text/75">{label}</span>
    </div>
  );
}

// --- Donut ---------------------------------------------------------------

export interface Slice {
  key: string;
  label: string;
  value: number;
  color: string;
}

function arcPath(cx: number, cy: number, r: number, inner: number, start: number, end: number): string {
  const large = end - start > Math.PI ? 1 : 0;
  const p = (radius: number, angle: number) =>
    `${cx + radius * Math.sin(angle)} ${cy - radius * Math.cos(angle)}`;
  return [
    `M ${p(r, start)}`,
    `A ${r} ${r} 0 ${large} 1 ${p(r, end)}`,
    `L ${p(inner, end)}`,
    `A ${inner} ${inner} 0 ${large} 0 ${p(inner, start)}`,
    "Z",
  ].join(" ");
}

export function DonutChart({ slices, centerLabel }: { slices: Slice[]; centerLabel: string }) {
  const [tip, setTip] = useState<TipState | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  const size = 168;
  const cx = size / 2;
  const r = size / 2 - 4;
  const inner = r * 0.62;
  const pct = (v: number) => (total === 0 ? 0 : Math.round((v / total) * 100));

  let angle = 0;
  const arcs = slices
    .filter((s) => s.value > 0)
    .map((s) => {
      const start = angle;
      angle += (s.value / total) * Math.PI * 2;
      return { ...s, start, end: angle };
    });

  function show(s: Slice, x: number, y: number) {
    setActive(s.key);
    setTip({
      x,
      y,
      content: <TipRow color={s.color} value={`${s.value} leads`} label={`${s.label} · ${pct(s.value)}%`} />,
    });
  }
  function hide() {
    setActive(null);
    setTip(null);
  }

  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative" onPointerLeave={hide}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={`Lead mix: ${slices.map((s) => `${s.label} ${s.value} (${pct(s.value)}%)`).join(", ")}`}
        >
          {arcs.length === 1 ? (
            // One bucket holds every lead: a full ring (an arc can't span 360°).
            <circle
              cx={cx}
              cy={cx}
              r={(r + inner) / 2}
              fill="none"
              stroke={arcs[0].color}
              strokeWidth={r - inner}
              tabIndex={0}
              onPointerMove={(e) => show(arcs[0], e.nativeEvent.offsetX, e.nativeEvent.offsetY)}
              onFocus={() => show(arcs[0], cx, 8)}
              onBlur={hide}
              className="outline-none"
            />
          ) : (
            arcs.map((a) => {
              const mid = (a.start + a.end) / 2;
              return (
                <path
                  key={a.key}
                  d={arcPath(cx, cx, r, inner, a.start, a.end)}
                  fill={a.color}
                  // 2px panel-colored gap between touching slices.
                  stroke="var(--color-panel)"
                  strokeWidth={2}
                  opacity={active && active !== a.key ? 0.55 : 1}
                  tabIndex={0}
                  aria-label={`${a.label}: ${a.value} leads, ${pct(a.value)}%`}
                  className="cursor-default outline-none transition-opacity focus-visible:opacity-100"
                  onPointerMove={(e) => show(a, e.nativeEvent.offsetX, e.nativeEvent.offsetY)}
                  onFocus={() => show(a, cx + (r - 6) * Math.sin(mid), cx - (r - 6) * Math.cos(mid))}
                  onBlur={hide}
                />
              );
            })
          )}
          <text x={cx} y={cx - 2} textAnchor="middle" className="fill-heading font-sans text-2xl font-semibold">
            {total}
          </text>
          <text x={cx} y={cx + 16} textAnchor="middle" className="fill-text font-sans text-xs opacity-75">
            {centerLabel}
          </text>
        </svg>
        <Tooltip tip={tip} />
      </div>

      {/* Legend: identity never rests on color alone. */}
      <ul className="flex flex-col gap-2">
        {slices.map((s) => (
          <li key={s.key} className="flex items-center gap-2.5 text-sm">
            <span aria-hidden="true" className="inline-block h-3 w-3 rounded-[3px]" style={{ backgroundColor: s.color }} />
            <span className="w-12 font-medium text-heading">{s.label}</span>
            <span className="tabular-nums text-text">{s.value}</span>
            <span className="tabular-nums text-text/60">({pct(s.value)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Horizontal bars -----------------------------------------------------

export interface Bar {
  key: string;
  label: string;
  value: number;
  max: number;
}

export function BarChart({ bars, color }: { bars: Bar[]; color: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref, 420);
  const [tip, setTip] = useState<TipState | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const labelW = 124;
  const valueW = 64;
  const plotW = Math.max(40, width - labelW - valueW);
  const rowH = 30;
  const barH = 14;
  const height = bars.length * rowH;

  function show(b: Bar, x: number, y: number) {
    setActive(b.key);
    setTip({
      x,
      y,
      content: (
        <TipRow
          color={color}
          value={`${b.value.toFixed(1)} / ${b.max}`}
          label={`${b.label} · ${Math.round((b.value / b.max) * 100)}% of max`}
        />
      ),
    });
  }
  function hide() {
    setActive(null);
    setTip(null);
  }

  return (
    <div ref={ref} className="relative" onPointerLeave={hide}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Average score breakdown: ${bars.map((b) => `${b.label} ${b.value.toFixed(1)} of ${b.max}`).join(", ")}`}
      >
        {/* Baseline, hairline. */}
        <line x1={labelW} x2={labelW} y1={0} y2={height} stroke="var(--color-border)" strokeWidth={1} />
        {bars.map((b, i) => {
          const y = i * rowH + (rowH - barH) / 2;
          const w = Math.max(0, Math.min(1, b.value / b.max)) * plotW;
          const cy = y + barH / 2;
          return (
            <g
              key={b.key}
              tabIndex={0}
              className="outline-none"
              onPointerMove={(e) => show(b, e.nativeEvent.offsetX, i * rowH)}
              onFocus={() => show(b, labelW + w, i * rowH)}
              onBlur={hide}
            >
              {/* Hit target: the whole row, not just the painted bar. */}
              <rect x={0} y={i * rowH} width={width} height={rowH} fill="transparent" />
              <text x={labelW - 10} y={cy} dy="0.35em" textAnchor="end" className="fill-text font-sans text-xs">
                {b.label}
              </text>
              {w > 0 && (
                // 4px rounded data-end, square at the baseline.
                <path
                  d={`M ${labelW} ${y} H ${labelW + Math.max(w - 4, 0)} Q ${labelW + w} ${y} ${labelW + w} ${y + 4} V ${y + barH - 4} Q ${labelW + w} ${y + barH} ${labelW + Math.max(w - 4, 0)} ${y + barH} H ${labelW} Z`}
                  fill={color}
                  opacity={active && active !== b.key ? 0.55 : 1}
                  className="transition-opacity"
                />
              )}
              <text x={labelW + w + 8} y={cy} dy="0.35em" className="fill-text font-sans text-xs tabular-nums">
                {b.value.toFixed(1)}
                <tspan className="opacity-60">/{b.max}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  );
}

// --- Ranked line ---------------------------------------------------------

export interface RankedPoint {
  id: string;
  label: string;
  value: number;
  bucketLabel: string;
  bucketColor: string;
}

export interface Threshold {
  label: string;
  value: number;
  color: string;
}

export function RankedLineChart({
  points,
  thresholds,
  color,
}: {
  points: RankedPoint[];
  thresholds: Threshold[];
  color: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref, 640);
  const [hover, setHover] = useState<number | null>(null);
  const height = 220;
  const pad = { top: 12, right: 76, bottom: 30, left: 36 };
  const plotW = Math.max(40, width - pad.left - pad.right);
  const plotH = height - pad.top - pad.bottom;
  const n = points.length;

  const x = (i: number) => pad.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => pad.top + (1 - Math.max(0, Math.min(100, v)) / 100) * plotH;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(p.value)}`).join(" ");
  const showDots = n <= 40;

  function nearest(px: number): number {
    if (n <= 1) return 0;
    const i = Math.round(((px - pad.left) / plotW) * (n - 1));
    return Math.max(0, Math.min(n - 1, i));
  }

  const hovered = hover !== null ? points[hover] : null;

  return (
    <div ref={ref} className="relative">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Scores ranked best to worst for ${n} leads, from ${points[0]?.value.toFixed(0)} down to ${points[n - 1]?.value.toFixed(0)}.`}
        tabIndex={0}
        className="outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        onPointerMove={(e) => setHover(nearest(e.nativeEvent.offsetX))}
        onPointerLeave={() => setHover(null)}
        onFocus={() => setHover((h) => h ?? 0)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") setHover((h) => Math.min(n - 1, (h ?? -1) + 1));
          if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? 1) - 1));
        }}
      >
        {/* Recessive grid: hairline, solid, clean ticks. */}
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={pad.left + plotW} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeWidth={1} />
            <text x={pad.left - 8} y={y(t)} dy="0.35em" textAnchor="end" className="fill-text font-sans text-[11px] tabular-nums opacity-70">
              {t}
            </text>
          </g>
        ))}

        {/* Bucket cutoffs: a short colored key + text-token label at the right edge. */}
        {thresholds.map((t) => (
          <g key={t.label}>
            <line x1={pad.left} x2={pad.left + plotW} y1={y(t.value)} y2={y(t.value)} stroke={t.color} strokeWidth={1} opacity={0.7} />
            <text x={pad.left + plotW + 8} y={y(t.value)} dy="0.35em" className="fill-text font-sans text-[11px]">
              {t.label}
            </text>
          </g>
        ))}

        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {showDots &&
          points.map((p, i) => (
            <circle key={p.id} cx={x(i)} cy={y(p.value)} r={4} fill={p.bucketColor} stroke="var(--color-panel)" strokeWidth={2} />
          ))}

        {hovered && hover !== null && (
          <g>
            {/* Crosshair snaps to the nearest lead. */}
            <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + plotH} stroke="var(--color-text)" strokeWidth={1} opacity={0.35} />
            <circle cx={x(hover)} cy={y(hovered.value)} r={5} fill={hovered.bucketColor} stroke="var(--color-panel)" strokeWidth={2} />
          </g>
        )}

        <text x={pad.left} y={height - 6} className="fill-text font-sans text-[11px] opacity-70">
          Best
        </text>
        <text x={pad.left + plotW} y={height - 6} textAnchor="end" className="fill-text font-sans text-[11px] opacity-70">
          Lead rank → worst
        </text>
      </svg>
      {hovered && hover !== null && (
        <Tooltip
          tip={{
            x: x(hover),
            y: y(hovered.value),
            content: (
              <div className="flex flex-col gap-0.5">
                <TipRow color={hovered.bucketColor} value={hovered.value.toFixed(0)} label={hovered.bucketLabel} />
                <div className="text-text/75">
                  #{hover + 1} · {hovered.label}
                </div>
              </div>
            ),
          }}
        />
      )}
    </div>
  );
}
