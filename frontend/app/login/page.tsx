"use client";

import { Button, Input } from "@heroui/react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login } from "@/services/auth";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await login(String(data.get("email")), String(data.get("password")));
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to log in");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card-wrap" aria-labelledby="login-title">
        <div className="login-card">
          <div className="login-heading">
            <p className="login-brand">ENTRY POINT</p>
            <h1 id="login-title">Building Access &amp; Tenant Management</h1>
            <p>Manage tenant access, permissions, and building security for 1205 on Franklin.</p>
          </div>

          <form className="login-form" onSubmit={submit}>
            <Input
              name="email"
              aria-label="Email"
              type="email"
              autoComplete="email"
              variant="bordered"
              placeholder="Email"
              size="lg"
              isRequired
            />
            <Input
              name="password"
              aria-label="Password"
              type="password"
              autoComplete="current-password"
              variant="bordered"
              placeholder="Password"
              size="lg"
              isRequired
            />
            {error ? (
              <div className="login-alert" role="alert">
                {error}
              </div>
            ) : null}
            <Button className="login-submit" type="submit" size="lg" fullWidth isLoading={loading}>
              Sign In
            </Button>
          </form>
        </div>
      </section>
    </main>
  );
}
