import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardData } from "./useDashboardData";

vi.mock("@/api/files", () => ({ listFiles: vi.fn() }));
vi.mock("@/api/alerts", () => ({ listAlerts: vi.fn() }));

import { listAlerts } from "@/api/alerts";
import { listFiles } from "@/api/files";
import { makeAlert, makeFile } from "@/components/testFixtures";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useDashboardData", () => {
  it("loads files and alerts on mount", async () => {
    const file = makeFile({ id: "f1" });
    const alert = makeAlert({ id: 7 });
    vi.mocked(listFiles).mockResolvedValue([file]);
    vi.mocked(listAlerts).mockResolvedValue([alert]);

    const { result } = renderHook(() => useDashboardData());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.files).toEqual([file]);
    expect(result.current.alerts).toEqual([alert]);
    expect(result.current.error).toBeNull();
  });

  it("surfaces fetch errors", async () => {
    vi.mocked(listFiles).mockRejectedValue(new Error("network down"));
    vi.mocked(listAlerts).mockResolvedValue([]);

    const { result } = renderHook(() => useDashboardData());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).toBe("network down");
  });

  it("reloads data when loadData is called", async () => {
    vi.mocked(listFiles).mockResolvedValue([]);
    vi.mocked(listAlerts).mockResolvedValue([]);

    const { result } = renderHook(() => useDashboardData());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    vi.mocked(listFiles).mockResolvedValue([makeFile({ id: "f2" })]);
    await act(async () => {
      await result.current.loadData();
    });

    expect(result.current.files).toHaveLength(1);
  });
});
