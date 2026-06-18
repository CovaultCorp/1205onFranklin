"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { formatDate } from "@/services/client";
import { getAuditLogs } from "@/services/operations";
import type { AuditLog } from "@/types/api";

export default function AuditLogPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["audit-log"], queryFn: getAuditLogs });

  return (
    <div className="page">
      <PageTitle eyebrow="Reports" title="Audit Log" description="Recent meaningful actions recorded by the registry backend." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<AuditLog>
        ariaLabel="Audit log"
        rows={data?.audit_logs ?? []}
        isLoading={isLoading}
        searchText={(log) => `${log.actor_email ?? ""} ${log.action} ${log.target_type} ${log.target_id ?? ""}`}
        columns={[
          { key: "time", label: "Time", render: (log) => formatDate(log.created_at), sortable: true },
          { key: "actor", label: "Actor", render: (log) => log.actor_email ?? "System", sortable: true },
          { key: "action", label: "Action", render: (log) => log.action, sortable: true },
          { key: "target", label: "Target", render: (log) => `${log.target_type} ${log.target_id ?? ""}`, sortable: true }
        ]}
      />
    </div>
  );
}
