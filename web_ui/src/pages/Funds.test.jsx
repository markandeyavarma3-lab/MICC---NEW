import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../test/renderPage";
import { mockFunds } from "../test/mockData";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return { ...actual, api: vi.fn(() => Promise.resolve(mockFunds)) };
});

import Funds from "./Funds";

describe("Funds page", () => {
  it("renders the fund table without crashing", async () => {
    renderPage(<Funds />);
    await waitFor(() => expect(screen.getByText("Test Fund")).toBeInTheDocument());
  });
});
