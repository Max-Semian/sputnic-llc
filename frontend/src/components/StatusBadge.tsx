import { Badge } from "react-bootstrap";

import type { ProcessingStatus, ScanStatus } from "@/types";

type StatusBadgeProps = {
  variant: string;
  label: string;
};

export function StatusBadge({ variant, label }: StatusBadgeProps) {
  return <Badge bg={variant}>{label}</Badge>;
}

export function ProcessingStatusBadge({ status }: { status: ProcessingStatus }) {
  return <StatusBadge label={status} variant={processingVariant(status)} />;
}

export function ScanStatusBadge({ status }: { status: ScanStatus }) {
  return <StatusBadge label={status ?? "pending"} variant={scanVariant(status)} />;
}

function processingVariant(status: ProcessingStatus): string {
  if (status === "failed") return "danger";
  if (status === "processing") return "warning";
  if (status === "processed") return "success";
  return "secondary";
}

function scanVariant(status: ScanStatus): string {
  if (status === "suspicious") return "warning";
  if (status === "failed") return "danger";
  return "success";
}
