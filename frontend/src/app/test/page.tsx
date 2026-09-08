import { DashboardPage } from "@/components/DashboardPage";

/**
 * Backwards-compatible alias: the dashboard used to be served under /test
 * (Next basePath). It now lives at the root, and this page keeps /test working.
 */
export default function TestPage() {
  return <DashboardPage />;
}
