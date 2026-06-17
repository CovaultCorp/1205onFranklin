import { apiFetch } from "./client";
import type { Session } from "@/types/api";

export function getSession() {
  return apiFetch<Session>("/session");
}

export function login(email: string, password: string) {
  return apiFetch<{ account: Session["account"] }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export function logout() {
  return apiFetch<{ ok: boolean }>("/auth/logout", { method: "POST", body: "{}" });
}
