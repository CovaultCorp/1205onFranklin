"use client";

import { Button, Card, CardBody, CardHeader, Input, Select, SelectItem, Textarea } from "@nextui-org/react";
import { Send } from "lucide-react";
import { FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

const requestTypes = [
  ["new_access", "New access"],
  ["change_access", "Change access"],
  ["temporary_access", "Temporary access"],
  ["offboarding", "Offboarding"],
  ["lost_badge", "Lost badge"]
];

export default function RequestAccessPage() {
  const [submittedId, setSubmittedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const data = Object.fromEntries(
      Array.from(new FormData(event.currentTarget).entries()).map(([key, value]) => [key, value === "" ? null : value])
    );
    try {
      const result = await apiFetch<{ request: { id: number } }>("/access-requests", {
        method: "POST",
        body: JSON.stringify(data)
      });
      setSubmittedId(result.request.id);
      event.currentTarget.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to submit request");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="content">
      <div className="page">
        <div className="page-header">
          <div>
            <div className="eyebrow">Public portal</div>
            <h1 className="text-3xl font-bold">Request access</h1>
            <p className="mt-2 max-w-2xl text-default-500">
              Submit building access changes for admin review. Provisioning stays pending until an admin approves it.
            </p>
          </div>
          <ThemeToggle />
        </div>
        <Card radius="sm">
          <CardHeader className="gap-3">
            <Send size={20} />
            <h2 className="text-lg font-bold">Access request details</h2>
          </CardHeader>
          <CardBody>
            {submittedId ? (
              <div className="rounded-lg border border-success-200 bg-success-50 p-4 text-success-700">
                Request #{submittedId} was submitted for admin review.
              </div>
            ) : null}
            <form className="form-grid mt-4" onSubmit={submit}>
              <Select name="request_type" label="Request type" defaultSelectedKeys={["new_access"]} isRequired>
                {requestTypes.map(([key, label]) => (
                  <SelectItem key={key} value={key}>
                    {label}
                  </SelectItem>
                ))}
              </Select>
              <Input name="requested_for_email" type="email" label="User email" isRequired />
              <Input name="requested_for_first_name" label="First name" isRequired />
              <Input name="requested_for_last_name" label="Last name" isRequired />
              <Input name="requested_for_employee_number" label="Employee number" />
              <Input name="requested_for_department" label="Department" />
              <Input name="requested_for_company_text" label="Company" />
              <Input name="requested_for_suite_text" label="Suite" />
              <Input name="requested_start_date" type="date" label="Start date" />
              <Input name="requested_end_date" type="date" label="End date" />
              <Textarea className="full-span" name="reason" label="Reason" minRows={3} />
              <Input name="requester_name" label="Requester name" isRequired />
              <Input name="requester_email" type="email" label="Requester email" isRequired />
              {error ? <p className="full-span text-sm text-danger">{error}</p> : null}
              <Button className="full-span" color="primary" type="submit" isLoading={loading}>
                Submit request
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </main>
  );
}
