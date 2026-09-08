import { describe, expect, it } from "vitest";

import { formatDate, formatSize, getLevelVariant, getProcessingVariant } from "./format";

describe("formatSize", () => {
  it("formats bytes, kilobytes and megabytes", () => {
    expect(formatSize(0)).toBe("0 B");
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(2048)).toBe("2.0 KB");
    expect(formatSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("formatDate", () => {
  it("renders a valid date without throwing", () => {
    const out = formatDate("2026-01-02T10:30:00Z");
    expect(out).toMatch(/\d{2}\.\d{2}\.\d{4}/);
  });
});

describe("badge variants", () => {
  it("maps alert levels to bootstrap variants", () => {
    expect(getLevelVariant("critical")).toBe("danger");
    expect(getLevelVariant("warning")).toBe("warning");
    expect(getLevelVariant("info")).toBe("success");
  });

  it("maps processing statuses to bootstrap variants", () => {
    expect(getProcessingVariant("failed")).toBe("danger");
    expect(getProcessingVariant("processing")).toBe("warning");
    expect(getProcessingVariant("processed")).toBe("success");
    expect(getProcessingVariant("uploaded")).toBe("secondary");
  });
});
