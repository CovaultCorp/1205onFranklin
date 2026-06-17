"use client";

import { Button, Card, CardBody, Input } from "@heroui/react";
import { LockKeyhole } from "lucide-react";
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
    <main className="flex min-h-screen items-center justify-center px-5 py-10">
      <div className="absolute right-5 top-5">
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-md" radius="sm">
        <CardBody className="gap-6 p-8">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-white">
              <LockKeyhole size={22} />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Admin login</h1>
              <p className="text-sm text-default-500">Building Access Registry</p>
            </div>
          </div>
          <form className="grid gap-4" onSubmit={submit}>
            <Input name="email" label="Email" type="email" isRequired />
            <Input name="password" label="Password" type="password" isRequired />
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <Button color="primary" type="submit" isLoading={loading}>
              Sign in
            </Button>
          </form>
        </CardBody>
      </Card>
    </main>
  );
}
