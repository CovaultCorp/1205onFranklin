import { apiFetch } from "./client";
import type { AccessRequest, Lookup } from "@/types/api";

export function getRequests() {
  return apiFetch<{ requests: AccessRequest[] }>("/admin/requests");
}

export function getLookups() {
  return apiFetch<{ companies: Lookup[]; suites: Lookup[]; profiles: Lookup[] }>("/admin/lookups");
}

export function submitAccessRequest(payload: Record<string, unknown>) {
  return apiFetch<{ request: AccessRequest }>("/access-requests", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function approveRequest(id: number, payload: Record<string, unknown>) {
  return apiFetch<{ request: AccessRequest; sync_job_id: number }>(`/admin/requests/${id}/approve`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function denyRequest(id: number, denial_reason: string) {
  return apiFetch<{ request: AccessRequest }>(`/admin/requests/${id}/deny`, {
    method: "POST",
    body: JSON.stringify({ denial_reason })
  });
}

export function requestNeedsInfo(id: number, admin_notes: string) {
  return apiFetch<{ request: AccessRequest }>(`/admin/requests/${id}/needs-info`, {
    method: "POST",
    body: JSON.stringify({ admin_notes })
  });
}
