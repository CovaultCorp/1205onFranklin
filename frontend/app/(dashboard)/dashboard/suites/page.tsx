"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { getSuites } from "@/services/property";
import type { Suite } from "@/types/api";

export default function SuitesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["suites"], queryFn: getSuites });

  return (
    <div className="page">
      <PageTitle eyebrow="Property Data" title="Suites" description="Suite inventory, assigned company, floor, area, and active access users." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<Suite>
        ariaLabel="Suites"
        rows={data?.suites ?? []}
        isLoading={isLoading}
        searchText={(suite) => `${suite.suite_number} ${suite.assigned_company?.name ?? ""} ${suite.floor ?? ""} ${suite.status}`}
        columns={[
          { key: "suite", label: "Suite", render: (suite) => suite.suite_number, sortable: true },
          { key: "company", label: "Assigned Company", render: (suite) => suite.assigned_company?.name ?? "Unassigned", sortable: true },
          { key: "floor", label: "Floor", render: (suite) => suite.floor ?? "Not set", sortable: true },
          { key: "users", label: "Active Users", render: (suite) => suite.active_user_count, sortable: true },
          { key: "status", label: "Status", render: (suite) => <StatusBadge value={suite.status} /> }
        ]}
      />
    </div>
  );
}
