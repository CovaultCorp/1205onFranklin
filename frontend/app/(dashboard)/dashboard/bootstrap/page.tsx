"use client";

import { Card, CardBody } from "@heroui/react";
import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { getBootstrap } from "@/services/operations";

type Batch = {
  id: number;
  source: string;
  status: string;
  filename?: string | null;
  created_at: string;
};

export default function BootstrapPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["bootstrap"], queryFn: getBootstrap });

  return (
    <div className="page">
      <PageTitle eyebrow="Operations" title="Bootstrap Users" description="Review unmatched UniFi snapshots and recent import batches before promoting users locally." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <Card className="dashboard-panel mb-5" radius="sm" shadow="sm">
        <CardBody>
          <div className="text-sm text-default-500">Unmatched UniFi snapshots</div>
          <div className="text-3xl font-bold">{data?.unmatched_count ?? 0}</div>
        </CardBody>
      </Card>
      <DataTable<Batch>
        ariaLabel="Import batches"
        rows={(data?.recent_batches as Batch[]) ?? []}
        isLoading={isLoading}
        searchText={(batch) => `${batch.source} ${batch.status} ${batch.filename ?? ""}`}
        columns={[
          { key: "id", label: "Batch", render: (batch) => batch.id, sortable: true },
          { key: "source", label: "Source", render: (batch) => batch.source, sortable: true },
          { key: "filename", label: "File", render: (batch) => batch.filename ?? "Generated", sortable: true },
          { key: "status", label: "Status", render: (batch) => <StatusBadge value={batch.status} /> }
        ]}
      />
    </div>
  );
}
