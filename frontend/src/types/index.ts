/**
 * Shared domain types mirroring the backend DTOs (src/schemas.py).
 */

export type ProcessingStatus = "uploaded" | "processing" | "processed" | "failed";

export type ScanStatus = "clean" | "suspicious" | "failed" | null;

export type AlertLevel = "info" | "warning" | "critical";

export type FileItem = {
  id: string;
  title: string;
  original_name: string;
  mime_type: string;
  size: number;
  processing_status: ProcessingStatus;
  scan_status: ScanStatus;
  scan_details: string | null;
  metadata_json: Record<string, unknown> | null;
  requires_attention: boolean;
  created_at: string;
  updated_at: string;
};

export type AlertItem = {
  id: number;
  file_id: string;
  level: AlertLevel;
  message: string;
  created_at: string;
};
