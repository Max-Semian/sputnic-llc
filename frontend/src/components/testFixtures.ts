import type { AlertItem, FileItem } from "@/types";

/** Minimal valid fixtures for component tests. */

let seq = 0;

export function makeFile(overrides: Partial<FileItem> = {}): FileItem {
  seq += 1;
  return {
    id: `file-${seq}`,
    title: "Отчёт",
    original_name: "report.txt",
    mime_type: "text/plain",
    size: 1024,
    processing_status: "processed",
    scan_status: "clean",
    scan_details: "no threats found",
    metadata_json: null,
    requires_attention: false,
    created_at: "2026-01-02T10:00:00Z",
    updated_at: "2026-01-02T10:00:01Z",
    ...overrides,
  };
}

export function makeAlert(overrides: Partial<AlertItem> = {}): AlertItem {
  seq += 1;
  return {
    id: seq,
    file_id: "file-1",
    level: "warning",
    message: "File requires attention",
    created_at: "2026-01-02T10:00:02Z",
    ...overrides,
  };
}
