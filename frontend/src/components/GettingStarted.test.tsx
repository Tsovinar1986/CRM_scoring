import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GettingStarted } from "./GettingStarted";
import * as api from "../api";
import type { ScoredLead } from "../types";

vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof api>();
  return { ...actual, fetchLicenseStatus: vi.fn() };
});

const starter = {
  hosted: true, licensed: false as const, reason: "trial" as const, customer_email: "tina@example.com",
  plan: null, tier: "starter" as const, trial_uploads_left: 10,
};
const subscribed = {
  hosted: true, licensed: true as const, customer_email: "tina@example.com", plan: "subscription",
  tier: "pro" as const, expires_at: null,
};

function makeLead(overrides: Partial<ScoredLead>): ScoredLead {
  return {
    id: "1", company_name: "Acme", domain: "acme.com", contact_name: "Jane", contact_title: "VP",
    industry: "SaaS", employee_count: 200, revenue_usd: 20_000_000, geography: "United States",
    source: "csv_upload", tech_stack: ["AWS"], is_hiring: true, enrichment_source: "mock", fit_score: 80,
    score_breakdown: {
      industry_match: 25, company_size_fit: 25, revenue_fit: 15,
      tech_stack_match: 15, geography_fit: 10, hiring_signal: 10,
    },
    account_fit_score: 80, llm_rationale: "strong fit", combined_score: 80, bucket: "hot", crm_pushed: false,
    ...overrides,
  };
}

describe("GettingStarted", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders nothing without a signed-in workspace", () => {
    const { container } = render(<GettingStarted leads={[]} onSelectLead={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(api.fetchLicenseStatus).not.toHaveBeenCalled();
  });

  it("shows setup progress for a new Starter workspace", async () => {
    localStorage.setItem("tenant_api_key", "k");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(starter);
    render(<GettingStarted leads={[]} onSelectLead={vi.fn()} />);

    expect(await screen.findByText("Welcome, tina@example.com")).toBeInTheDocument();
    expect(screen.getByText("1 of 4")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload" })).toHaveAttribute("href", "#upload");
    expect(screen.getByRole("link", { name: "See plans" })).toHaveAttribute("href", "#plans");
  });

  it("lists unpushed hot leads, best first, and opens one on click", async () => {
    localStorage.setItem("tenant_api_key", "k");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(starter);
    const onSelectLead = vi.fn();
    const leads = [
      makeLead({ id: "a", company_name: "Alpha", combined_score: 75 }),
      makeLead({ id: "b", company_name: "Beta", combined_score: 92 }),
      makeLead({ id: "c", company_name: "Gamma", crm_pushed: true }),
      makeLead({ id: "d", company_name: "Delta", bucket: "cold", combined_score: 20 }),
    ];
    render(<GettingStarted leads={leads} onSelectLead={onSelectLead} />);

    const buttons = await screen.findAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Beta acme.com92", "Alpha acme.com75"]);
    expect(screen.getByText("3 of 4")).toBeInTheDocument();

    await userEvent.click(buttons[0]);
    expect(onSelectLead).toHaveBeenCalledWith(leads[1]);
  });

  it("disappears once setup is complete and no hot leads are waiting", async () => {
    localStorage.setItem("tenant_api_key", "k");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(subscribed);
    const { container } = render(
      <GettingStarted leads={[makeLead({ crm_pushed: true })]} onSelectLead={vi.fn()} />
    );

    await vi.waitFor(() => expect(api.fetchLicenseStatus).toHaveBeenCalled());
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
