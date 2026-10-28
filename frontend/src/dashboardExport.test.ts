import JSZip from "jszip";
import { describe, expect, it } from "vitest";
import { buildDashboardDeck } from "./dashboardExport";
import { translator } from "./i18n";
import type { ScoredLead } from "./types";

function makeLead(overrides: Partial<ScoredLead>): ScoredLead {
  return {
    id: "1", company_name: "Acme", domain: "acme.com", contact_name: "Jane", contact_title: "VP",
    industry: "SaaS", employee_count: 200, revenue_usd: 20_000_000, geography: "United States",
    source: "csv_upload", tech_stack: ["AWS"], is_hiring: true, enrichment_source: "mock", fit_score: 80,
    score_breakdown: {
      industry_match: 20, company_size_fit: 25, revenue_fit: 15,
      tech_stack_match: 9, geography_fit: 10, hiring_signal: 0,
    },
    account_fit_score: 80, llm_rationale: "strong fit", combined_score: 80, bucket: "hot", crm_pushed: false,
    ...overrides,
  };
}

const leads = [
  makeLead({ id: "a", company_name: "Alpha", combined_score: 90, bucket: "hot" }),
  makeLead({ id: "b", company_name: "Beta", combined_score: 60, bucket: "warm" }),
  makeLead({ id: "c", company_name: "Gamma", combined_score: 20, bucket: "cold" }),
];

async function open(lang: "en" | "ru") {
  const deck = await buildDashboardDeck(leads, translator(lang), lang);
  const zip = await JSZip.loadAsync(await deck.arrayBuffer());
  const names = Object.keys(zip.files);
  const slides = names.filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n)).sort((a, b) => parseInt(a.match(/\d+/)![0]) - parseInt(b.match(/\d+/)![0]));
  const text = await Promise.all(slides.map((n) => zip.file(n)!.async("string")));
  return { text };
}

describe("buildDashboardDeck", () => {
  it("makes an overview, three charts drawn from shapes and the top leads", async () => {
    const { text } = await open("en");
    expect(text).toHaveLength(5);
    expect(text[0]).toContain("Scoring overview");
    expect(text[0]).toContain("Total leads");
    expect(text[1]).toContain("Lead mix");
    expect(text[4]).toContain("Top leads");
    expect(text[4].indexOf("Alpha")).toBeLessThan(text[4].indexOf("Gamma"));
    expect(text[1]).toContain('prstGeom prst="blockArc"');
    expect(text[2]).toContain("Industry match");
    expect(text[3]).toContain("Hot ≥ 75");
  });

  it("is written in the app's language", async () => {
    const { text } = await open("ru");
    expect(text[0]).toContain("Обзор");
    expect(text[4]).toContain("Лучшие лиды");
  });
});
