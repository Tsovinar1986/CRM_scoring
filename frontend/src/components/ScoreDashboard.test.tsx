import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreDashboard } from "./ScoreDashboard";
import type { ScoredLead } from "../types";

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
  makeLead({ id: "c", company_name: "Gamma", combined_score: 55, bucket: "warm" }),
  makeLead({ id: "d", company_name: "Delta", combined_score: 20, bucket: "cold" }),
];

describe("ScoreDashboard", () => {
  it("renders nothing without leads", () => {
    const { container } = render(<ScoreDashboard leads={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("draws a donut, a bar chart and a line chart, each described for screen readers", () => {
    render(<ScoreDashboard leads={leads} />);
    expect(screen.getByRole("img", { name: /^Lead mix: Hot 1 \(25%\), Warm 2 \(50%\), Cold 1 \(25%\)/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Average score breakdown: Industry fit 20\.0 of 25/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Scores ranked best to worst for 4 leads, from 90 down to 20/ })).toBeInTheDocument();
  });

  it("shows every bucket's count in the legend, not by color alone", () => {
    render(<ScoreDashboard leads={leads} />);
    expect(screen.getByText("(50%)")).toBeInTheDocument();
    expect(screen.getAllByText("(25%)")).toHaveLength(2);
  });

  it("shows a slice's value in a tooltip on keyboard focus", () => {
    render(<ScoreDashboard leads={leads} />);
    fireEvent.focus(screen.getByLabelText("Warm: 2 leads, 50%"));
    expect(screen.getByRole("status")).toHaveTextContent("2 leadsWarm · 50%");
  });

  it("steps through ranked leads with the arrow keys", () => {
    render(<ScoreDashboard leads={leads} />);
    const line = screen.getByRole("img", { name: /^Scores ranked/ });
    fireEvent.focus(line);
    expect(screen.getByRole("status")).toHaveTextContent("#1 · Alpha");
    fireEvent.keyDown(line, { key: "ArrowRight" });
    expect(screen.getByRole("status")).toHaveTextContent("#2 · Beta");
  });

  it("handles a batch where every lead is in one bucket", () => {
    render(<ScoreDashboard leads={[makeLead({ id: "x" }), makeLead({ id: "y" })]} />);
    expect(screen.getByRole("img", { name: /Hot 2 \(100%\), Warm 0 \(0%\), Cold 0 \(0%\)/ })).toBeInTheDocument();
  });
});
