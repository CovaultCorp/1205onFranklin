"use client";

import { Button } from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/services/client";
import { getConflicts, resolveConflict } from "@/services/operations";
import type { Conflict } from "@/types/api";

export default function ConflictsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["conflicts"], queryFn: getConflicts });
  const resolve = useMutation({
    mutationFn: resolveConflict,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["conflicts"] })
  });

  return (
    <div className="page">
      <PageTitle eyebrow="Operations" title="Conflicts" description="Operational reconciliation exceptions with priority, age, and resolution controls." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<Conflict>
        ariaLabel="Conflicts"
        rows={data?.conflicts ?? []}
        isLoading={isLoading}
        searchText={(conflict) => `${conflict.conflict_type} ${conflict.description} ${conflict.severity} ${conflict.status}`}
        columns={[
          { key: "type", label: "Type", render: (conflict) => conflict.conflict_type.replaceAll("_", " "), sortable: true },
          { key: "severity", label: "Priority", render: (conflict) => <StatusBadge value={conflict.severity} /> },
          { key: "status", label: "Status", render: (conflict) => <StatusBadge value={conflict.status} /> },
          { key: "created", label: "Age", render: (conflict) => formatDate(conflict.created_at), sortable: true },
          { key: "description", label: "Description", render: (conflict) => <span className="line-clamp-2">{conflict.description}</span> },
          {
            key: "action",
            label: "Action",
            render: (conflict) => conflict.status === "open" ? (
              <Button size="sm" variant="flat" color="success" startContent={<CheckCircle2 size={15} />} onPress={() => resolve.mutate(conflict.id)}>
                Resolve
              </Button>
            ) : "Resolved"
          }
        ]}
      />
    </div>
  );
}
