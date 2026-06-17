import { apiFetch } from "./client";
import type { ReportRun } from "@/types/api";

export function getReportRuns() {
  return apiFetch<{ runs: ReportRun[] }>("/admin/reports/runs");
}

export function getReportRun(id: number) {
  return apiFetch<{ run: ReportRun; report_html: string }>(`/admin/reports/runs/${id}`);
}

export function generateReport(payload: Record<string, unknown>) {
  return apiFetch<{ run: ReportRun }>("/admin/reports/generate", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
