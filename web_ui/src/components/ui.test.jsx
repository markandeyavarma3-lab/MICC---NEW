import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { LazyMotion, domMax } from "framer-motion";
import { useApi, Table, FreshnessBar, ErrorState } from "./ui";

// Table (animated rows) and ErrorState both use m.* components, which need a
// LazyMotion ancestor to actually animate -- same provider App.jsx mounts.
function withMotion(ui) {
  return <LazyMotion features={domMax}>{ui}</LazyMotion>;
}

function Probe({ fetcher }) {
  const { data, err, fetchedAt } = useApi(fetcher);
  if (err) return <div>error: {err.message}</div>;
  if (!data) return <div>loading</div>;
  return <div>data: {JSON.stringify(data)} · fetchedAt: {fetchedAt ? "set" : "null"}</div>;
}

describe("useApi", () => {
  it("goes loading -> data on a successful fetch", async () => {
    render(<Probe fetcher={() => Promise.resolve({ n: 1 })} />);
    expect(screen.getByText("loading")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/data:/)).toBeInTheDocument());
    expect(screen.getByText(/fetchedAt: set/)).toBeInTheDocument();
  });

  it("goes loading -> error on a rejected fetch", async () => {
    render(<Probe fetcher={() => Promise.reject(new Error("boom"))} />);
    await waitFor(() => expect(screen.getByText("error: boom")).toBeInTheDocument());
  });

  it("refetches every mounted instance when a global micc:refresh event fires", async () => {
    let calls = 0;
    const fetcher = () => {
      calls += 1;
      return Promise.resolve({ n: calls });
    };
    render(<Probe fetcher={fetcher} />);
    await waitFor(() => expect(screen.getByText(/"n":1/)).toBeInTheDocument());

    act(() => window.dispatchEvent(new Event("micc:refresh")));
    await waitFor(() => expect(screen.getByText(/"n":2/)).toBeInTheDocument());
    expect(calls).toBe(2);
  });
});

describe("Table", () => {
  const cols = ["Name", "Value"];
  const rows = [{ name: "beta", value: 2 }, { name: "alpha", value: 1 }];
  const render_ = (r) => [r.name, r.value];

  it("filters rows by searchKeys", () => {
    render(withMotion(
      <Table cols={cols} rows={rows} render={render_} searchKeys={[(r) => r.name]} />
    ));
    fireEvent.change(screen.getByLabelText("Search table"), { target: { value: "alp" } });
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.queryByText("beta")).not.toBeInTheDocument();
  });

  it("sorts rows when a sortable header is clicked, toggling direction on repeat clicks", () => {
    render(withMotion(
      <Table cols={cols} rows={rows} render={render_}
             sortAccessors={[(r) => r.name, null]} />
    ));
    const header = screen.getByRole("button", { name: /Name/ });
    const bodyOrder = () => screen.getAllByRole("row").slice(1).map((r) => r.textContent);

    fireEvent.click(header);
    expect(bodyOrder()[0]).toMatch(/^alpha/);

    fireEvent.click(header);
    expect(bodyOrder()[0]).toMatch(/^beta/);
  });

  it("shows a 'no matches' row when a search filters everything out", () => {
    render(withMotion(<Table cols={cols} rows={rows} render={render_} searchKeys={[(r) => r.name]} />));
    fireEvent.change(screen.getByLabelText("Search table"), { target: { value: "zzz" } });
    expect(screen.getByText("no matches")).toBeInTheDocument();
  });
});

describe("FreshnessBar", () => {
  it("shows 'Refresh' before any fetch has been reported, and dispatches micc:refresh on click", () => {
    const onRefresh = vi.fn();
    window.addEventListener("micc:refresh", onRefresh);
    render(<FreshnessBar />);
    expect(screen.getByRole("button")).toHaveTextContent("Refresh");
    fireEvent.click(screen.getByRole("button"));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    window.removeEventListener("micc:refresh", onRefresh);
  });
});

describe("ErrorState", () => {
  it("renders the error message and calls retry on click", () => {
    const retry = vi.fn();
    render(withMotion(<ErrorState error={new Error("network down")} retry={retry} />));
    expect(screen.getByText("network down")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
