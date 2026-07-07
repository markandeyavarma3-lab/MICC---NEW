import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderPage } from "../test/renderPage";
import { mockEvents } from "../test/mockData";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return { ...actual, api: vi.fn(() => Promise.resolve(mockEvents)) };
});

import Events from "./Events";

describe("Events page", () => {
  it("renders the event scoreboard without crashing", async () => {
    renderPage(<Events />);
    await waitFor(() => expect(screen.getByText("Event shadow scoreboard")).toBeInTheDocument());
    expect(screen.getByText("TCS")).toBeInTheDocument();
  });
});
