import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, request, resolveApiUrl } from "./apiClient";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("resolveApiUrl", () => {
  it("defaults to localhost:8000 and normalizes slashes", () => {
    expect(resolveApiUrl("/files")).toBe("http://localhost:8000/files");
    expect(resolveApiUrl("alerts")).toBe("http://localhost:8000/alerts");
  });
});

describe("request", () => {
  it("parses successful JSON responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([{ id: 1 }])));

    const result = await request<Array<{ id: number }>>("/alerts");
    expect(result).toEqual([{ id: 1 }]);
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/alerts",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("throws ApiError with the backend detail message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "File is empty" }, 400)),
    );

    const error = await request("/files").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(400);
    expect((error as ApiError).message).toBe("File is empty");
  });

  it("throws a generic ApiError for non-JSON errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("boom", { status: 500 })));

    const error = await request("/files").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain("500");
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    expect(await request("/files/1", { method: "DELETE" })).toBeUndefined();
  });
});
