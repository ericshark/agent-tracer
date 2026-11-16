import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LandingPage } from "../pages/Landing";

vi.mock("../state/auth", () => ({ useAuth: () => ({ user: null, loading: false }) }));

describe("LandingPage", () => {
  it("shows the hero and sign-in / get-started links", () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/agents/);
    const signIn = screen.getAllByRole("link", { name: "Sign in" })[0];
    expect(signIn.getAttribute("href")).toBe("/login");
    const start = screen.getAllByRole("link", { name: /Get started/ })[0];
    expect(start.getAttribute("href")).toBe("/login?mode=register");
  });
});
