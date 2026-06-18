"use client";

import { Button, Card, CardBody, Divider, Input } from "@heroui/react";
import { LockKeyhole, Mail } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login } from "@/services/auth";
import { ThemeToggle } from "@/components/theme-toggle";

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
      <div className="login-theme-toggle">
        <ThemeToggle />
      </div>

      <section className="login-card-wrap" aria-labelledby="login-title">
        <Card className="login-card" radius="lg" shadow="sm">
          <CardBody className="login-card-body">
            <div className="login-heading">
              <p className="login-brand">ENTRY POINT</p>
              <h1 id="login-title">Building Access &amp; Tenant Management</h1>
              <p>Manage tenant access, permissions, and building security for 1205 on Franklin.</p>
            </div>

            <Divider className="login-divider" />

            <form className="login-form" onSubmit={submit}>
              <Input
                name="email"
                label="Email"
                type="email"
                autoComplete="email"
                variant="bordered"
                labelPlacement="outside"
                placeholder="Email"
                size="lg"
                isRequired
                startContent={<Mail aria-hidden="true" className="login-input-icon" size={17} />}
              />
              <Input
                name="password"
                label="Password"
                type="password"
                autoComplete="current-password"
                variant="bordered"
                labelPlacement="outside"
                placeholder="Password"
                size="lg"
                isRequired
                startContent={<LockKeyhole aria-hidden="true" className="login-input-icon" size={17} />}
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

            <p className="login-helper">Authorized building operations users only.</p>
          </CardBody>
        </Card>
      </section>
    </main>
  );
}
