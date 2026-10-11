import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LicenseBanner } from "./LicenseBanner";
import * as api from "../api";
import * as braintree from "../braintree";
import { configured, fakeDropin } from "../test/braintreeFixtures";

vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof api>();
  return {
    ...actual,
    fetchLicenseStatus: vi.fn(),
    fetchBillingConfig: vi.fn(),
    fetchBraintreeClientToken: vi.fn(),
    subscribeWithBraintree: vi.fn(),
    startFreeTrial: vi.fn(),
    cancelWorkspaceSubscription: vi.fn(),
  };
});

vi.mock("../braintree", () => ({ loadDropin: vi.fn() }));

const trial = {
  licensed: false as const, reason: "trial" as const, customer_email: null, plan: null, tier: "starter" as const, trial_uploads_left: 5,
};

describe("LicenseBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Most tests don't care about checkout -- default it "off" unless a test
    // explicitly opts in.
    vi.mocked(api.fetchBillingConfig).mockResolvedValue({ environment: "sandbox", checkout_available: false });
    vi.mocked(api.fetchBraintreeClientToken).mockResolvedValue("client-token");
  });

  it("renders nothing until the license status has loaded", () => {
    vi.mocked(api.fetchLicenseStatus).mockReturnValue(new Promise(() => {}));
    const { container } = render(<LicenseBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows Starter messaging with uploads left and Pro/Advanced buy buttons when no license was ever set", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      licensed: false, reason: "trial", customer_email: null, plan: null, tier: "starter", trial_uploads_left: 6,
    });

    render(<LicenseBanner />);

    expect(await screen.findByText(/starter \(free\)/i)).toBeInTheDocument();
    expect(screen.getByText(/6 of 10 uploads left/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pro — \$20\/mo/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pro annual/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /advanced — \$40\/mo/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /advanced annual/i })).toBeInTheDocument();
  });

  it("shows the customer/tier when licensed", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      licensed: true, customer_email: "buyer@example.com", plan: "monthly", tier: "pro", expires_at: null,
    });

    render(<LicenseBanner />);

    expect(await screen.findByText(/buyer@example.com/)).toBeInTheDocument();
    expect(screen.getByText(/pro plan/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /\$20\/mo/i })).not.toBeInTheDocument();
  });

  it("shows a distinct message once Starter's upload allowance runs out with no purchase", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      licensed: false, reason: "trial_expired", customer_email: null, plan: null, tier: "starter", trial_uploads_left: 0,
    });

    render(<LicenseBanner />);

    expect(await screen.findByText(/trial has ended/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pro — \$20\/mo/i })).toBeInTheDocument();
    expect(screen.queryByText(/starter \(free\)/i)).not.toBeInTheDocument();
  });

  it("shows a renew CTA (not Starter copy) when a paid license has expired", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      licensed: false, reason: "expired", customer_email: "buyer@example.com", plan: "monthly", tier: "pro", trial_uploads_left: null,
    });

    render(<LicenseBanner />);

    expect(await screen.findByText(/expired/i)).toBeInTheDocument();
    expect(screen.getByText(/buyer@example.com/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pro — \$20\/mo/i })).toBeInTheDocument();
    expect(screen.queryByText(/starter \(free\)/i)).not.toBeInTheDocument();
  });

  it("shows a config-check message (no buy buttons) for an invalid key, not a Starter/payment prompt", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      licensed: false, reason: "invalid", customer_email: null, plan: null, tier: "starter", trial_uploads_left: null,
    });

    render(<LicenseBanner />);

    expect(await screen.findByText(/couldn't be verified/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /\$20\/mo/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/starter \(free\)/i)).not.toBeInTheDocument();
  });

  it("renders the card form for the chosen plan and shows the key after paying", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(trial);
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    const fake = fakeDropin();
    vi.mocked(braintree.loadDropin).mockResolvedValue(fake.namespace);
    vi.mocked(api.subscribeWithBraintree).mockResolvedValue({
      status: "ok", email: "buyer@example.com", tier: "advanced", plan: "annual", license_key: "LK-123",
    });

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /advanced annual/i }));

    expect(await screen.findByText(/advanced — \$384\/year/i)).toBeInTheDocument();
    await waitFor(() => expect(fake.options()?.authorization).toBe("client-token"));
    await userEvent.click(await screen.findByRole("button", { name: /subscribe — \$384\/year/i }));

    expect(api.subscribeWithBraintree).toHaveBeenCalledWith({
      tier: "advanced", interval: "annual", payment_method_nonce: "nonce-1", device_data: "dd",
    });
    expect(await screen.findByText("LK-123")).toBeInTheDocument();
    expect(screen.getByText("buyer@example.com")).toBeInTheDocument();
  });

  it("says checkout isn't configured instead of loading Braintree when it's unavailable", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(trial);

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /pro — \$20\/mo/i }));

    expect(await screen.findByText("Checkout isn't configured on this deployment.")).toBeInTheDocument();
    expect(braintree.loadDropin).not.toHaveBeenCalled();
  });

  it("shows a load error when Drop-in's script can't load", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(trial);
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    vi.mocked(braintree.loadDropin).mockRejectedValue(new Error("Couldn't load the payment form."));

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /pro annual/i }));

    expect(await screen.findByText("Couldn't load the payment form.")).toBeInTheDocument();
  });

  it("keeps the form open with the reason when the card is declined", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(trial);
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    vi.mocked(braintree.loadDropin).mockResolvedValue(fakeDropin().namespace);
    vi.mocked(api.subscribeWithBraintree).mockRejectedValue(new Error("Your card was declined. Please try a different card."));

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /pro — \$20\/mo/i }));
    const pay = await screen.findByRole("button", { name: /subscribe — \$20\/month/i });
    await waitFor(() => expect(pay).toBeEnabled());
    await userEvent.click(pay);

    expect(await screen.findByText(/your card was declined/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /subscribe — \$20\/month/i })).toBeEnabled();
  });

  it("doesn't charge when the card form is incomplete", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(trial);
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    vi.mocked(braintree.loadDropin).mockResolvedValue(fakeDropin(new Error("No payment method is available.")).namespace);

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /pro — \$20\/mo/i }));
    const pay = await screen.findByRole("button", { name: /subscribe — \$20\/month/i });
    await waitFor(() => expect(pay).toBeEnabled());
    await userEvent.click(pay);

    expect(await screen.findByText("Please complete your card details.")).toBeInTheDocument();
    expect(api.subscribeWithBraintree).not.toHaveBeenCalled();
  });

  it("offers a one-click free trial to a new visitor on the hosted deployment", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      hosted: true, licensed: false, reason: "no_workspace", customer_email: null, plan: null, tier: "starter", trial_uploads_left: null,
    });
    vi.mocked(api.startFreeTrial).mockResolvedValue({ tenant_id: "t1", name: "Free trial", api_key: "trial-key" });
    const onWorkspaceChange = vi.fn();

    render(<LicenseBanner onWorkspaceChange={onWorkspaceChange} />);
    await userEvent.click(await screen.findByRole("button", { name: /start free trial/i }));

    expect(api.getTenantApiKey()).toBe("trial-key");
    expect(onWorkspaceChange).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /pro — \$20\/mo/i })).not.toBeInTheDocument();
  });

  it("shows why a free trial couldn't start", async () => {
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      hosted: true, licensed: false, reason: "no_workspace", customer_email: null, plan: null, tier: "starter", trial_uploads_left: null,
    });
    vi.mocked(api.startFreeTrial).mockRejectedValue(new Error("Rate limit exceeded"));

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /start free trial/i }));

    expect(await screen.findByText("Rate limit exceeded")).toBeInTheDocument();
    expect(api.getTenantApiKey()).toBeNull();
  });

  it("shows a hosted trial workspace its own uploads left", async () => {
    api.setTenantApiKey("trial-key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({ ...trial, hosted: true, trial_uploads_left: 7 });

    render(<LicenseBanner />);

    expect(await screen.findByText(/7 of 10 uploads left/i)).toBeInTheDocument();
  });

  it("asks a hosted trial that ran out to subscribe, not to self-host", async () => {
    api.setTenantApiKey("trial-key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({ ...trial, hosted: true, reason: "trial_expired", trial_uploads_left: 0 });

    render(<LicenseBanner />);

    expect(await screen.findByText("Your free trial has ended — subscribe to keep scoring leads.")).toBeInTheDocument();
  });

  it("stays hidden for a workspace on a self-hosted install", async () => {
    api.setTenantApiKey("client-key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue(trial);

    const { container } = render(<LicenseBanner />);

    await waitFor(() => expect(api.fetchLicenseStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("upgrades a hosted workspace in place after paying", async () => {
    api.setTenantApiKey("trial-key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({ ...trial, hosted: true });
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    vi.mocked(braintree.loadDropin).mockResolvedValue(fakeDropin().namespace);
    vi.mocked(api.subscribeWithBraintree).mockResolvedValue({
      status: "ok", email: "Jane Doe", tier: "pro", plan: "monthly", license_key: "LK", workspace_upgraded: true,
    });
    const onWorkspaceChange = vi.fn();

    render(<LicenseBanner onWorkspaceChange={onWorkspaceChange} />);
    await userEvent.click(await screen.findByRole("button", { name: /pro — \$20\/mo/i }));
    const pay = await screen.findByRole("button", { name: /subscribe — \$20\/month/i });
    await waitFor(() => expect(pay).toBeEnabled());
    await userEvent.click(pay);

    expect(await screen.findByText(/this workspace is now on pro/i)).toBeInTheDocument();
    expect(screen.queryByText("LK")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onWorkspaceChange).toHaveBeenCalled();
  });

  it("lets a hosted subscriber cancel, keeping access until the paid period ends", async () => {
    api.setTenantApiKey("key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      hosted: true, licensed: true, customer_email: "Jane Doe", plan: "subscription", tier: "pro", expires_at: null,
    });
    vi.mocked(api.cancelWorkspaceSubscription).mockResolvedValue({ status: "cancelled", access_until: 1790000000 });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onWorkspaceChange = vi.fn();

    render(<LicenseBanner onWorkspaceChange={onWorkspaceChange} />);
    await userEvent.click(await screen.findByRole("button", { name: /cancel subscription/i }));

    expect(api.cancelWorkspaceSubscription).toHaveBeenCalled();
    expect(onWorkspaceChange).toHaveBeenCalled();
  });

  it("doesn't cancel if the subscriber changes their mind", async () => {
    api.setTenantApiKey("key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      hosted: true, licensed: true, customer_email: "Jane Doe", plan: "subscription", tier: "pro", expires_at: null,
    });
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<LicenseBanner />);
    await userEvent.click(await screen.findByRole("button", { name: /cancel subscription/i }));

    expect(api.cancelWorkspaceSubscription).not.toHaveBeenCalled();
  });

  it("shows when a cancelled hosted subscription ends, with no cancel button", async () => {
    api.setTenantApiKey("key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({
      hosted: true, licensed: true, customer_email: "Jane Doe", plan: "subscription", tier: "pro", expires_at: 1790000000,
    });

    render(<LicenseBanner />);

    expect(await screen.findByText(/cancelled, active until/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel subscription/i })).not.toBeInTheDocument();
  });
});

describe("LicenseBanner in the native apps", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.fetchBillingConfig).mockResolvedValue(configured);
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (iPhone) CRMScoringApp/1.0");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows uploads left but no buy buttons or upgrade prompt", async () => {
    api.setTenantApiKey("trial-key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({ ...trial, hosted: true, trial_uploads_left: 7 });

    render(<LicenseBanner />);

    expect(await screen.findByText("Starter (free) — 7 of 10 uploads left.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pro|advanced/i })).not.toBeInTheDocument();
  });

  it("tells a trial that ran out it ended, without asking to subscribe", async () => {
    api.setTenantApiKey("trial-key");
    vi.mocked(api.fetchLicenseStatus).mockResolvedValue({ ...trial, hosted: true, reason: "trial_expired", trial_uploads_left: 0 });

    render(<LicenseBanner />);

    expect(await screen.findByText("Your free trial has ended.")).toBeInTheDocument();
    expect(screen.queryByText(/subscribe/i)).not.toBeInTheDocument();
  });
});
