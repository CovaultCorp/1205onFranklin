import { apiFetch } from "./client";
import type { DashboardData } from "@/types/api";

export function getDashboard() {
  return apiFetch<DashboardData>("/admin/dashboard");
}
