import { describe, it, expect, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderPage } from "../test/renderPage";
import { mockIdeas } from "../test/mockData";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return { ...actual, api: vi.fn(() => Promise.resolve(mockIdeas)) };
});

import Ideas from "./Ideas";

describe("Ideas page", () => {
  it("renders idea cards and opens the thesis drawer on click", async () => {
    renderPage(<Ideas />);
    await waitFor(() => expect(screen.getByText("RELIANCE")).toBeInTheDocument());

    fireEvent.click(screen.getByText("RELIANCE").closest(".cursor-pointer"));
    expect(await screen.findByRole("dialog", { name: /RELIANCE thesis/ })).toBeInTheDocument();
  });
});
