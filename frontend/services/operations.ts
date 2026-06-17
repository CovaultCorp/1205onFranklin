import { apiFetch } from "./client";
import type { AuditLog, Conflict, SyncJob } from "@/types/api";

export function getConflicts() {
  return apiFetch<{ conflicts: Conflict[] }>("/admin/conflicts");
}

export function resolveConflict(id: number) {
  return apiFetch<{ conflict: Conflict }>(`/admin/conflicts/${id}/resolve`, { method: "POST", body: "{}" });
}

export function getSyncJobs() {
  return apiFetch<{ sync_jobs: SyncJob[] }>("/admin/sync-jobs");
}

export function getBootstrap() {
  return apiFetch<{ unmatched_count: number; unmatched: unknown[]; recent_batches: unknown[] }>("/admin/bootstrap");
}

export function getAuditLogs() {
  return apiFetch<{ audit_logs: AuditLog[] }>("/admin/audit-logs");
}

export function getSettings() {
  return apiFetch<{ settings: Record<string, string | boolean> }>("/admin/settings");
}
