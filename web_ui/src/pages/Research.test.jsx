import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../test/renderPage";
import { mockVerdicts, mockReview } from "../test/mockData";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  const byPath = { "/api/verdicts": mockVerdicts, "/api/review": mockReview };
  return { ...actual, api: vi.fn((path) => Promise.resolve(byPath[path])) };
});

import Research from "./Research";

describe("Research page", () => {
  it("renders the verdict ledger without crashing", async () => {
    renderPage(<Research />);
    await waitFor(() => expect(screen.getByText("The verdict ledger")).toBeInTheDocument());
    expect(screen.getAllByText("amihud").length).toBeGreaterThan(0);
  });
});
