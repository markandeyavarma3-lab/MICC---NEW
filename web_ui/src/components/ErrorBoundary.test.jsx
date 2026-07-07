import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ErrorBoundary from "./ErrorBoundary";

function Bomb() {
  throw new Error("kaboom");
}

describe("ErrorBoundary", () => {
  it("renders children normally when nothing throws", () => {
    render(<ErrorBoundary><div>fine</div></ErrorBoundary>);
    expect(screen.getByText("fine")).toBeInTheDocument();
  });

  it("catches a render error and shows the fallback instead of crashing the whole tree", () => {
    // React logs the error to console.error -- expected, silence it for this test.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Bomb /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("kaboom");
    spy.mockRestore();
  });

  it("clears the error and re-renders children when 'Try again' is clicked", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("temporary");
      return <div>recovered</div>;
    }
    const { rerender } = render(<ErrorBoundary><Flaky /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    rerender(<ErrorBoundary><Flaky /></ErrorBoundary>);
    expect(screen.getByText("recovered")).toBeInTheDocument();
    spy.mockRestore();
  });
});
