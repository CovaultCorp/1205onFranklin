import { apiFetch } from "./client";
import type { AccessProfile, Company, Occupancy, Suite } from "@/types/api";

export function getCompanies() {
  return apiFetch<{ companies: Company[] }>("/admin/companies");
}

export function getSuites() {
  return apiFetch<{ suites: Suite[] }>("/admin/suites");
}

export function getOccupancy() {
  return apiFetch<{ occupancy: Occupancy[] }>("/admin/occupancy");
}

export function getAccessProfiles() {
  return apiFetch<{ profiles: AccessProfile[] }>("/admin/access-profiles");
}
