import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthPage } from "./AuthPage";
import * as api from "../api";

vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof api>();
  return { ...actual, login: vi.fn(), signup: vi.fn(), forgotPassword: vi.fn(), startFreeTrial: vi.fn() };
});

const auth = { tenant_id: "t1", name: "Acme", api_key: "key-1" };

describe("AuthPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("logs in and stores the workspace key", async () => {
    vi.mocked(api.login).mockResolvedValue(auth);
    const onSignedIn = vi.fn();
    render(<AuthPage onSignedIn={onSignedIn} />);

    await userEvent.type(screen.getByLabelText("Email"), "tina@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "Secret-pass1!");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(api.login).toHaveBeenCalledWith("tina@example.com", "Secret-pass1!");
    expect(api.getTenantApiKey()).toBe("key-1");
    expect(onSignedIn).toHaveBeenCalled();
  });

  it("shows the server's error and stays on the page when login fails", async () => {
    vi.mocked(api.login).mockRejectedValue(new Error("Incorrect email or password."));
    const onSignedIn = vi.fn();
    render(<AuthPage onSignedIn={onSignedIn} />);

    await userEvent.type(screen.getByLabelText("Email"), "tina@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("creates an account from the sign-up form", async () => {
    vi.mocked(api.signup).mockResolvedValue(auth);
    const onSignedIn = vi.fn();
    render(<AuthPage onSignedIn={onSignedIn} />);

    await userEvent.click(screen.getByRole("button", { name: "Create an account" }));
    const submit = screen.getByRole("button", { name: "Create account" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Company or workspace name"), "Tina");
    await userEvent.type(screen.getByLabelText("Email"), "tina@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "Secret-pass1!");
    await userEvent.click(submit);

    expect(api.signup).toHaveBeenCalledWith("Tina", "tina@example.com", "Secret-pass1!");
    expect(onSignedIn).toHaveBeenCalled();
  });

  it("starts a free trial without an account", async () => {
    vi.mocked(api.startFreeTrial).mockResolvedValue(auth);
    const onSignedIn = vi.fn();
    render(<AuthPage onSignedIn={onSignedIn} />);

    await userEvent.click(screen.getByRole("button", { name: "Start free trial" }));

    expect(api.getTenantApiKey()).toBe("key-1");
    expect(onSignedIn).toHaveBeenCalled();
  });

  it("sends a password reset link", async () => {
    vi.mocked(api.forgotPassword).mockResolvedValue({ detail: "ok" });
    render(<AuthPage onSignedIn={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Forgot password?" }));
    await userEvent.type(screen.getByLabelText("Email"), "tina@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(api.forgotPassword).toHaveBeenCalledWith("tina@example.com");
    expect(await screen.findByText("Check your inbox")).toBeInTheDocument();
  });
});
