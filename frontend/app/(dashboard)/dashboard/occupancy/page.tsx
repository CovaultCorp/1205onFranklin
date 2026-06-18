"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/services/client";
import { getOccupancy } from "@/services/property";
import type { Occupancy } from "@/types/api";

export default function OccupancyPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["occupancy"], queryFn: getOccupancy });

  return (
    <div className="page">
      <PageTitle eyebrow="Property Data" title="Occupancy" description="Company-suite occupancy overview with active access-user counts." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<Occupancy>
        ariaLabel="Occupancy"
        rows={data?.occupancy ?? []}
        isLoading={isLoading}
        searchText={(row) => `${row.company?.name ?? ""} ${row.suite?.suite_number ?? ""} ${row.occupancy_status}`}
        columns={[
          { key: "company", label: "Company", render: (row) => row.company?.name ?? "Unknown", sortable: true },
          { key: "suite", label: "Suite", render: (row) => row.suite?.suite_number ?? "Unknown", sortable: true },
          { key: "users", label: "Active Users", render: (row) => row.active_user_count, sortable: true },
          { key: "start", label: "Start", render: (row) => formatDate(row.start_date), sortable: true },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={row.occupancy_status} /> }
        ]}
      />
    </div>
  );
}
