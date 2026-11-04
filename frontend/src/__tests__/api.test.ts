import { describe, expect, it, vi } from "vitest";
import { ApiError, api, formatDate, formatDateTime, formatNumber, roleRank } from "../api";

describe("formatting", () => {
  it("writes dates as DD/MM/YYYY", () => {
    expect(formatDate("2026-11-04T10:00:00+00:00")).toMatch(/^\d{2}\/\d{2}\/\d{4}$/);
  });

  it("writes AM and PM in capitals", () => {
    expect(formatDateTime("2026-11-04T10:00:00+00:00")).toMatch(/(AM|PM)$/);
  });

  it("puts commas in numbers", () => {
    expect(formatNumber(2999)).toBe("2,999");
  });
});

describe("roles", () => {
  it("ranks owner above viewer", () => {
    expect(roleRank.owner).toBeGreaterThan(roleRank.viewer);
  });
});

describe("api", () => {
  it("shows the server's message when a request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Full Name is required." }), { status: 422 })));
    await expect(api("/api/test")).rejects.toThrow("Full Name is required.");
    await expect(api("/api/test")).rejects.toBeInstanceOf(ApiError);
    vi.unstubAllGlobals();
  });

  it("sends JSON with the right header", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api("/api/test", { method: "POST", json: { a: 1 } });
    const init = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init[1].body).toBe('{"a":1}');
    vi.unstubAllGlobals();
  });
});
