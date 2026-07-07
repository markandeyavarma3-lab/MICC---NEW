import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../test/renderPage";
import { mockRisk, mockIdeas } from "../test/mockData";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  const byPath = { "/api/risk": mockRisk, "/api/ideas": mockIdeas };
  return { ...actual, api: vi.fn((path) => Promise.resolve(byPath[path])) };
});

import Risk from "./Risk";

describe("Risk page", () => {
  it("renders the risk state stats without crashing", async () => {
    renderPage(<Risk />);
    await waitFor(() => expect(screen.getByText("Risk state")).toBeInTheDocument());
    expect(screen.getByText("Drawdown")).toBeInTheDocument();
  });
});
