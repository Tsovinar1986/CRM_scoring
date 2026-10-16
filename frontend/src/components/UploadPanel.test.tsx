import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UploadPanel } from "./UploadPanel";
import * as api from "../api";
import { configured } from "../test/billingFixtures";

vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof api>();
  return {
    ...actual,
    uploadLeads: vi.fn(),
    fetchBillingConfig: vi.fn(),
    startStripeCheckout: vi.fn(),
  };
});

function selectFile() {
  const file = new File(["company_name,domain\nAcme,acme.com"], "leads.csv", { type: "text/csv" });
  const input = document.querySelector("input[type=file]") as HTMLInputElement;
  return userEvent.upload(input, file);
}

describe("UploadPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchBillingConfig).mockResolvedValue({ environment: "test", checkout_available: false });
  });

  it("calls onUploaded with the scored leads on success", async () => {
    const leads = [{ id: "1", company_name: "Acme" }] as never;
    vi.mocked(api.uploadLeads).mockResolvedValue({ leads, trialLimitedRows: null, trialTotalRows: null });
    const onUploaded = vi.fn();

    render(<UploadPanel onUploaded={onUploaded} />);
    await selectFile();

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(leads));
  });

  it("shows a trial-limit notice when the upload was capped", async () => {
    const leads = [{ id: "1", company_name: "Acme" }] as never;
    vi.mocked(api.uploadLeads).mockResolvedValue({ leads, trialLimitedRows: 10, trialTotalRows: 45 });

    render(<UploadPanel onUploaded={vi.fn()} />);
    await selectFile();

    expect(await screen.findByText(/first 10 of 45 rows/i)).toBeInTheDocument();
  });

  it("shows a generic error message for a non-license failure", async () => {
    vi.mocked(api.uploadLeads).mockRejectedValue(new Error("File must include a domain column."));

    render(<UploadPanel onUploaded={vi.fn()} />);
    await selectFile();

    expect(await screen.findByText("File must include a domain column.")).toBeInTheDocument();
  });

  it("shows a distinct upgrade CTA for a 402 LicenseRequiredError, not the generic error", async () => {
    vi.mocked(api.uploadLeads).mockRejectedValue(new api.LicenseRequiredError("No valid license found."));

    render(<UploadPanel onUploaded={vi.fn()} />);
    await selectFile();

    expect(await screen.findByText(/trial has expired/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\$20\/mo/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /buy annual/i })).toBeInTheDocument();
    expect(screen.queryByText("No valid license found.")).not.toBeInTheDocument();
  });

  it("opens Stripe checkout for the Pro annual plan on the license-expired CTA", async () => {
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    vi.mocked(api.uploadLeads).mockRejectedValue(new api.LicenseRequiredError("No valid license found."));
    vi.mocked(api.startStripeCheckout).mockResolvedValue({ url: "https://checkout.stripe.com/c/pay/cs_test_1" });
    const assign = vi.fn();
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign });

    render(<UploadPanel onUploaded={vi.fn()} />);
    await selectFile();

    await userEvent.click(await screen.findByRole("button", { name: /buy annual/i }));
    expect(await screen.findByText(/pro — \$192\/year/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /continue to secure checkout/i }));

    expect(api.startStripeCheckout).toHaveBeenCalledWith("pro", "annual");
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://checkout.stripe.com/c/pay/cs_test_1"));
    vi.restoreAllMocks();
  });
});
