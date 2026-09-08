import { useCallback, useEffect, useState } from "react";

import { listAlerts } from "@/api/alerts";
import { listFiles } from "@/api/files";
import type { AlertItem, FileItem } from "@/types";

export type DashboardState = {
  files: FileItem[];
  alerts: AlertItem[];
  isLoading: boolean;
  error: string | null;
  loadData: () => Promise<void>;
};

/**
 * Owns the files/alerts list state and data fetching for the dashboard.
 * Previously this logic lived inline in the page component.
 */
export function useDashboardData(): DashboardState {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [filesData, alertsData] = await Promise.all([listFiles(), listAlerts()]);
      setFiles(filesData);
      setAlerts(alertsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Произошла ошибка");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return { files, alerts, isLoading, error, loadData };
}
