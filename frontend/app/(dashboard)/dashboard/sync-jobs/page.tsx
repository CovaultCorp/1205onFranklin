"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/services/client";
import { getSyncJobs } from "@/services/operations";
import type { SyncJob } from "@/types/api";

export default function SyncJobsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["sync-jobs"], queryFn: getSyncJobs });

  return (
    <div className="page">
      <PageTitle eyebrow="Operations" title="Sync Jobs" description="Dry-run sync proposals, reconciliation jobs, failures, and completion history." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<SyncJob>
        ariaLabel="Sync jobs"
        rows={data?.sync_jobs ?? []}
        isLoading={isLoading}
        searchText={(job) => `${job.job_type} ${job.status} ${job.last_error ?? ""}`}
        columns={[
          { key: "id", label: "ID", render: (job) => job.id, sortable: true },
          { key: "type", label: "Job Type", render: (job) => job.job_type, sortable: true },
          { key: "status", label: "Status", render: (job) => <StatusBadge value={job.status} /> },
          { key: "attempts", label: "Attempts", render: (job) => job.attempt_count, sortable: true },
          { key: "created", label: "Created", render: (job) => formatDate(job.created_at), sortable: true },
          { key: "error", label: "Failure Details", render: (job) => job.last_error ?? "None" }
        ]}
      />
    </div>
  );
}
