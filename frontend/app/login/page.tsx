"use client";

import { Button, Card, CardBody, Divider, Input } from "@heroui/react";
import { LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
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
        <div className="login-logo">
          <BrandLogo href="" size="auth" />
        </div>

        <Card className="login-card" radius="sm" shadow="sm">
          <CardBody className="login-card-body">
            <div className="login-heading">
              <div className="login-icon" aria-hidden="true">
                <ShieldCheck size={20} />
              </div>
              <div>
                <p className="login-eyebrow">Secure dashboard access</p>
                <h1 id="login-title">Building Access Registry</h1>
                <p>Sign in to manage 1205 on Franklin access records.</p>
              </div>
            </div>

            <Divider className="login-divider" />

            <form className="login-form" onSubmit={submit}>
              <Input
                name="email"
                label="Email"
                type="email"
                autoComplete="email"
                variant="bordered"
                isRequired
                startContent={<Mail aria-hidden="true" className="login-input-icon" size={17} />}
              />
              <Input
                name="password"
                label="Password"
                type="password"
                autoComplete="current-password"
                variant="bordered"
                isRequired
                startContent={<LockKeyhole aria-hidden="true" className="login-input-icon" size={17} />}
              />
              {error ? (
                <div className="login-alert" role="alert">
                  {error}
                </div>
              ) : null}
              <Button className="login-submit" type="submit" isLoading={loading}>
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
