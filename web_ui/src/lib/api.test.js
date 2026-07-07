import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, fmt } from "./api";

describe("api()", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("returns parsed JSON on a successful response", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ hello: "world" }) });
    const data = await api("/api/whatever");
    expect(data).toEqual({ hello: "world" });
    expect(global.fetch).toHaveBeenCalledWith("/api/whatever");
  });

  it("throws with the path and status on a non-ok response", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(api("/api/broken")).rejects.toThrow("/api/broken -> HTTP 500");
  });

  it("never caches -- two calls to the same path both hit the network", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ n: 1 }) });
    await api("/api/same");
    await api("/api/same");
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});

describe("fmt", () => {
  it("inr formats with the Indian numbering system and no decimals", () => {
    expect(fmt.inr(1234567)).toBe("₹12,34,567");
    expect(fmt.inr(null)).toBe("—");
  });

  it("pct formats a fraction as a percentage string", () => {
    expect(fmt.pct(0.1234)).toBe("12.3%");
    expect(fmt.pct(0.1234, 2)).toBe("12.34%");
    expect(fmt.pct(null)).toBe("—");
  });

  it("num formats with a fixed decimal count", () => {
    expect(fmt.num(3.14159, 2)).toBe("3.14");
    expect(fmt.num(null)).toBe("—");
  });
});
