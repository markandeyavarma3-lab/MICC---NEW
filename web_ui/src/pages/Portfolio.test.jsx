import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../test/renderPage";

const mockPortfolio = {
  summary: { open_count: 1, open_unsized_count: 0, deployed: 100000, unrealized_total: 5000,
             closed_count: 1, win_rate: 1, avg_realized_return: 0.05 },
  open: [{ trade_id: 1, symbol: "TCS", thesis_type: "momentum", timeframe_class: "swing",
           entry_date: "2026-06-01", entry_price: 100, stop: 90, target: 120, size_shares: 10,
           current_price: 105, price_as_of: "2026-07-06", unrealized_pct: 0.05, notional: 1000, unrealized_value: 50 }],
  closed: [{ trade_id: 2, symbol: "INFY", thesis_type: "momentum", timeframe_class: "swing",
             entry_date: "2026-05-01", entry_price: 100, exit_date: "2026-06-01", exit_price: 110,
             exit_reason: "target", realized_return: 0.10 }],
};

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return { ...actual, api: vi.fn(() => Promise.resolve(mockPortfolio)) };
});

import Portfolio from "./Portfolio";

describe("Portfolio page", () => {
  it("renders summary stats, open positions, and closed trades without crashing", async () => {
    renderPage(<Portfolio />);
    await waitFor(() => expect(screen.getByText("Portfolio")).toBeInTheDocument());
    expect(screen.getByText("TCS")).toBeInTheDocument();
    expect(screen.getByText("INFY")).toBeInTheDocument();
    expect(screen.getAllByText("Open positions").length).toBeGreaterThan(0);
  });
});
