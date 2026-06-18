"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { getCompanies } from "@/services/property";
import type { Company } from "@/types/api";

export default function CompaniesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["companies"], queryFn: getCompanies });

  return (
    <div className="page">
      <PageTitle eyebrow="Property Data" title="Companies" description="Tenant company records, contacts, assigned suites, and active occupants." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<Company>
        ariaLabel="Companies"
        rows={data?.companies ?? []}
        isLoading={isLoading}
        searchText={(company) => `${company.name} ${company.primary_contact_email ?? ""} ${company.status}`}
        columns={[
          { key: "name", label: "Company", render: (company) => company.name, sortable: true },
          { key: "contact", label: "Contact", render: (company) => company.primary_contact_email ?? "Not set", sortable: true },
          { key: "users", label: "Active Users", render: (company) => company.active_user_count, sortable: true },
          { key: "suites", label: "Suites", render: (company) => company.suite_count, sortable: true },
          { key: "status", label: "Status", render: (company) => <StatusBadge value={company.status} /> }
        ]}
      />
    </div>
  );
}
