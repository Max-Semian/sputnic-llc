import { request } from "@/lib/apiClient";
import type { AlertItem } from "@/types";

export function listAlerts(): Promise<AlertItem[]> {
  return request<AlertItem[]>("/alerts");
}
