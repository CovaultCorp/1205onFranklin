"use client";

import { Card, CardBody } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { getSettings } from "@/services/operations";

export default function SettingsPage() {
  const { data, error } = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const settings = data?.settings ?? {};

  return (
    <div className="page">
      <PageTitle eyebrow="System" title="Settings" description="Read-only deployment and safety settings exposed to the dashboard." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <div className="grid gap-4 md:grid-cols-2">
        {Object.entries(settings).map(([key, value]) => (
          <Card key={key} className="dashboard-panel" radius="sm" shadow="sm">
            <CardBody className="flex-row items-center justify-between">
              <div>
                <div className="text-sm text-default-500">{key.replaceAll("_", " ")}</div>
                <div className="font-semibold">{typeof value === "boolean" ? (value ? "Enabled" : "Disabled") : String(value)}</div>
              </div>
              {typeof value === "boolean" ? <StatusBadge value={value ? "active" : "inactive"} /> : null}
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}
