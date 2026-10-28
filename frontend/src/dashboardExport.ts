import { dashboardStats, DIMENSION_LABELS, HOT_CUTOFF, pct, WARM_CUTOFF } from "./dashboardData";
import { saveFile } from "./fileSave";
import type { Lang, Translate } from "./i18n";
import type { ScoredLead } from "./types";

// The scoring overview as a PowerPoint deck: the same numbers as
// components/ScoreDashboard.tsx. The charts are drawn from plain shapes (arcs,
// bars, lines) rather than PowerPoint chart objects: Keynote drops chart
// objects on import, while shapes look the same in PowerPoint, Keynote and
// Google Slides and every piece stays editable. pptxgenjs is loaded only when
// someone asks for the deck.

const PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation";

// The app's light palette (index.css), without the "#".
const C = {
  bg: "F6F1E6",
  panel: "FFFCF5",
  border: "E6DBC3",
  text: "6B6152",
  heading: "211B12",
  accent: "B3401F",
  hot: "B3401F",
  warm: "B98A00",
  cold: "2F6DB5",
  series: "6B6152",
};
const BUCKET_COLOR: Record<string, string> = { hot: C.hot, warm: C.warm, cold: C.cold };
const TOP_LEADS = 10;

export async function buildDashboardDeck(leads: ScoredLead[], t: Translate, lang: Lang): Promise<Blob> {
  const { default: PptxGenJS } = await import("pptxgenjs");
  const stats = dashboardStats(leads);
  const pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
  pptx.title = t("dash.title");
  pptx.company = "CRM Scoring";

  // Georgia has no Armenian letters; Arial does on every platform.
  const display = lang === "hy" ? "Arial" : "Georgia";
  const body = "Arial";
  const date = new Date().toLocaleDateString(lang === "hy" ? "hy-AM" : lang, { year: "numeric", month: "long", day: "numeric" });
  const bucket = (key: string) => t(key === "hot" ? "bucket.hot" : key === "warm" ? "bucket.warm" : "bucket.cold");

  function newSlide(title: string, subtitle?: string) {
    const slide = pptx.addSlide();
    slide.background = { color: C.bg };
    slide.addText(title, { x: 0.6, y: 0.4, w: 12.1, h: 0.7, fontFace: display, fontSize: 28, bold: true, color: C.heading });
    if (subtitle) slide.addText(subtitle, { x: 0.6, y: 1.05, w: 12.1, h: 0.4, fontFace: body, fontSize: 13, color: C.text });
    slide.addText(t("export.madeWith"), { x: 0.6, y: 6.95, w: 12.1, h: 0.3, fontFace: body, fontSize: 9, color: C.text, align: "right" });
    return slide;
  }
  // 1. Headline numbers.
  const cover = newSlide(t("dash.title"), t("export.subtitle", { n: stats.total, date }));
  const tiles: { label: string; value: string; sub?: string; color?: string }[] = [
    { label: t("dash.totalLeads"), value: String(stats.total) },
    { label: t("bucket.hot"), value: String(stats.hot), sub: `${pct(stats.hot, stats.total)}%`, color: C.hot },
    { label: t("bucket.warm"), value: String(stats.warm), sub: `${pct(stats.warm, stats.total)}%`, color: C.warm },
    { label: t("bucket.cold"), value: String(stats.cold), sub: `${pct(stats.cold, stats.total)}%`, color: C.cold },
    { label: t("dash.avgScore"), value: stats.avgCombined.toFixed(0), sub: "/ 100" },
    { label: t("dash.avgAccountFit"), value: `${stats.avgAccountFit.toFixed(0)}%`, sub: "LLM" },
  ];
  tiles.forEach((tile, i) => {
    const x = 0.6 + (i % 3) * 4.1;
    const y = 2.0 + Math.floor(i / 3) * 2.2;
    cover.addShape(pptx.ShapeType.roundRect, { x, y, w: 3.85, h: 1.9, fill: { color: C.panel }, line: { color: C.border, width: 1 }, rectRadius: 0.12 });
    if (tile.color) cover.addShape(pptx.ShapeType.rect, { x: x + 0.3, y: y + 0.38, w: 0.16, h: 0.16, fill: { color: tile.color }, line: { color: tile.color } });
    cover.addText(tile.label, { x: x + (tile.color ? 0.5 : 0.25), y: y + 0.25, w: 3.2, h: 0.4, fontFace: body, fontSize: 13, color: C.text });
    cover.addText(
      [
        { text: tile.value, options: { fontFace: display, fontSize: 40, bold: true, color: C.heading } },
        ...(tile.sub ? [{ text: `  ${tile.sub}`, options: { fontFace: body, fontSize: 14, color: C.text } }] : []),
      ],
      { x: x + 0.25, y: y + 0.75, w: 3.4, h: 0.9, valign: "middle" },
    );
  });

  // 2. Hot / Warm / Cold mix: a ring of arcs starting at 12 o'clock.
  const mix = newSlide(t("dash.leadMix"), t("export.subtitle", { n: stats.total, date }));
  const ring = { x: 1.4, y: 1.8, d: 4.6 };
  const slices = (["hot", "warm", "cold"] as const).filter((key) => stats[key] > 0);
  if (slices.length === 1) {
    const color = BUCKET_COLOR[slices[0]];
    mix.addShape(pptx.ShapeType.donut, { x: ring.x, y: ring.y, w: ring.d, h: ring.d, fill: { color }, line: { color } });
  } else {
    // PowerPoint angles run clockwise from 3 o'clock.
    let angle = 270;
    for (const key of slices) {
      const sweep = (stats[key] / stats.total) * 360;
      mix.addShape(pptx.ShapeType.blockArc, {
        x: ring.x, y: ring.y, w: ring.d, h: ring.d,
        fill: { color: BUCKET_COLOR[key] },
        line: { color: C.bg, width: 2 },
        angleRange: [angle % 360, (angle + sweep) % 360],
        arcThicknessRatio: 0.4,
      });
      angle += sweep;
    }
  }
  mix.addText(
    [
      { text: String(stats.total), options: { fontFace: display, fontSize: 40, bold: true, color: C.heading, breakLine: true } },
      { text: t("dash.leads"), options: { fontFace: body, fontSize: 14, color: C.text } },
    ],
    { x: ring.x + 1.05, y: ring.y + 1.55, w: ring.d - 2.1, h: 1.5, align: "center", valign: "middle" },
  );
  mix.addTable(
    [
      [t("table.bucket"), t("dash.leads"), "%"].map((text) => ({ text, options: { bold: true, color: C.heading, fill: { color: C.panel } } })),
      ...(["hot", "warm", "cold"] as const).map((key) => [
        { text: bucket(key), options: { bold: true, color: BUCKET_COLOR[key] } },
        { text: String(stats[key]), options: { color: C.heading } },
        { text: `${pct(stats[key], stats.total)}%`, options: { color: C.text } },
      ]),
    ],
    { x: 7.6, y: 2.6, w: 5.0, colW: [2.2, 1.4, 1.4], fontFace: body, fontSize: 16, rowH: 0.6, border: { type: "solid", pt: 0.75, color: C.border }, valign: "middle" },
  );

  // 3. Average points per dimension, each bar against its own maximum.
  const breakdown = newSlide(t("dash.avgBreakdown"), t("export.breakdownSub"));
  const bars = { labelW: 3.2, x: 0.6 + 3.2 + 0.25, w: 6.6, top: 1.9, row: 0.78, h: 0.34 };
  stats.dimensions.forEach((d, i) => {
    const y = bars.top + i * bars.row;
    const share = Math.max(0, Math.min(1, d.value / d.max));
    breakdown.addText(t(DIMENSION_LABELS[d.key]), { x: 0.6, y: y - 0.08, w: bars.labelW, h: bars.h + 0.16, fontFace: body, fontSize: 14, color: C.heading, align: "right", valign: "middle" });
    // The full track is the dimension's maximum; the fill is the average.
    breakdown.addShape(pptx.ShapeType.rect, { x: bars.x, y, w: bars.w, h: bars.h, fill: { color: C.border }, line: { color: C.border, width: 0 } });
    if (share > 0) breakdown.addShape(pptx.ShapeType.rect, { x: bars.x, y, w: bars.w * share, h: bars.h, fill: { color: C.series }, line: { color: C.series, width: 0 } });
    breakdown.addText(
      [
        { text: `${d.value.toFixed(1)} / ${d.max}`, options: { bold: true, color: C.heading } },
        { text: `  ${Math.round(share * 100)}%`, options: { color: C.text } },
      ],
      { x: bars.x + bars.w + 0.2, y: y - 0.08, w: 2.0, h: bars.h + 0.16, fontFace: body, fontSize: 14, valign: "middle" },
    );
  });

  // 4. Every lead, best to worst, against the bucket cutoffs.
  const ranked = newSlide(t("dash.ranked"), t("dash.rankedSub"));
  const plot = { x: 1.2, y: 1.8, w: 9.6, h: 4.5 };
  const py = (v: number) => plot.y + (1 - Math.max(0, Math.min(100, v)) / 100) * plot.h;
  const hline = (v: number, color: string, width: number) =>
    ranked.addShape(pptx.ShapeType.line, { x: plot.x, y: py(v), w: plot.w, h: 0, line: { color, width } });
  for (const v of [0, 25, 50, 75, 100]) {
    hline(v, C.border, 0.75);
    ranked.addText(String(v), { x: plot.x - 0.6, y: py(v) - 0.15, w: 0.5, h: 0.3, fontFace: body, fontSize: 11, color: C.text, align: "right" });
  }
  for (const [value, color] of [[HOT_CUTOFF, C.hot], [WARM_CUTOFF, C.warm]] as const) {
    hline(value, color, 1.25);
    ranked.addText(t("dash.cutoff", { bucket: value === HOT_CUTOFF ? t("bucket.hot") : t("bucket.warm"), value }), {
      x: plot.x + plot.w + 0.15, y: py(value) - 0.17, w: 1.9, h: 0.34, fontFace: body, fontSize: 12, color: C.heading,
    });
  }
  // Very long lists are thinned to an even sample: the shape of the curve is
  // the point here, and the deck stays small.
  const step = Math.max(1, Math.ceil(stats.ranked.length / 300));
  const points = stats.ranked.filter((_, i) => i % step === 0 || i === stats.ranked.length - 1);
  const px = (i: number) => plot.x + (points.length <= 1 ? plot.w / 2 : (i / (points.length - 1)) * plot.w);
  for (let i = 1; i < points.length; i++) {
    const [x1, y1, x2, y2] = [px(i - 1), py(points[i - 1].combined_score), px(i), py(points[i].combined_score)];
    ranked.addShape(pptx.ShapeType.line, {
      x: x1, y: Math.min(y1, y2), w: x2 - x1, h: Math.abs(y2 - y1),
      flipV: y2 < y1, // rising segment: bottom-left to top-right
      line: { color: C.series, width: 2 },
    });
  }
  if (points.length <= 40) {
    points.forEach((l, i) => {
      const color = BUCKET_COLOR[l.bucket] ?? C.series;
      ranked.addShape(pptx.ShapeType.ellipse, { x: px(i) - 0.07, y: py(l.combined_score) - 0.07, w: 0.14, h: 0.14, fill: { color }, line: { color: C.bg, width: 1.5 } });
    });
  }
  ranked.addText(t("export.rank"), { x: plot.x, y: plot.y + plot.h + 0.15, w: plot.w, h: 0.35, fontFace: body, fontSize: 12, color: C.text, align: "center" });

  // 5. The leads to call first.
  const top = stats.ranked.slice(0, TOP_LEADS);
  const shortRationale = (text: string) => (text.length > 150 ? `${text.slice(0, 147).trimEnd()}…` : text);
  const leadsSlide = newSlide(t("export.topLeads"), t("export.topLeadsSub", { shown: top.length, n: stats.total }));
  leadsSlide.addTable(
    [
      ["#", t("table.company"), t("table.industry"), t("table.combined"), t("table.bucket"), t("export.rationale")].map((text) => ({
        text,
        options: { bold: true, color: C.heading, fill: { color: C.panel } },
      })),
      ...top.map((l, i) => [
        { text: String(i + 1), options: { color: C.text } },
        { text: l.company_name, options: { bold: true, color: C.heading } },
        { text: l.industry ?? "", options: { color: C.text } },
        { text: l.combined_score.toFixed(0), options: { bold: true, color: C.heading } },
        { text: bucket(l.bucket), options: { bold: true, color: BUCKET_COLOR[l.bucket] ?? C.text } },
        { text: shortRationale(l.llm_rationale), options: { color: C.text, fontSize: 9 } },
      ]),
    ],
    {
      x: 0.6, y: 1.6, w: 12.1,
      colW: [0.45, 2.3, 1.7, 1.05, 0.9, 5.7],
      fontFace: body,
      fontSize: 11,
      border: { type: "solid", pt: 0.5, color: C.border },
      valign: "middle",
      autoPage: true,
      autoPageRepeatHeader: true,
      newSlideStartY: 0.6,
    },
  );

  return (await pptx.write({ outputType: "blob" })) as Blob;
}

export async function downloadDashboardDeck(leads: ScoredLead[], t: Translate, lang: Lang): Promise<void> {
  const deck = await buildDashboardDeck(leads, t, lang);
  await saveFile(`crm-scoring-overview-${new Date().toISOString().slice(0, 10)}.pptx`, deck, PPTX_MIME);
}
