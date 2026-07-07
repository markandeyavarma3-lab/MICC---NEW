import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../test/renderPage";
import { mockRegime, mockRisk, mockBest, mockIdeas, mockStrategies, mockHealth } from "../test/mockData";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  const byPath = {
    "/api/regime": mockRegime, "/api/risk": mockRisk, "/api/best": mockBest,
    "/api/ideas": mockIdeas, "/api/strategies": mockStrategies, "/api/health": mockHealth,
  };
  return { ...actual, api: vi.fn((path) => Promise.resolve(byPath[path])) };
});

import Overview from "./Overview";

describe("Overview page", () => {
  it("renders the regime state and headline stats without crashing", async () => {
    renderPage(<Overview />);
    await waitFor(() => expect(screen.getByText("RISK-ON")).toBeInTheDocument());
    expect(screen.getByText("Sharpe (OOS)")).toBeInTheDocument();
  });
});
