import { apiFetch } from "./client";
import type { User } from "@/types/api";

export function getUsers() {
  return apiFetch<{ users: User[] }>("/admin/users");
}
