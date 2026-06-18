"use client";

import { useQuery } from "@tanstack/react-query";
import { PageTitle } from "@/components/page-title";
import { DataTable } from "@/components/data-table";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/services/client";
import { getUsers } from "@/services/users";
import type { User } from "@/types/api";

function accessSummary(user: User) {
  const policies = [
    ...(user.current_unifi_access_policy_names ?? []),
    ...(user.desired_unifi_access_policy_names ?? [])
  ].filter(Boolean);
  const groups = [
    ...(user.current_unifi_user_group_names ?? []),
    ...(user.desired_unifi_user_group_names ?? [])
  ].filter(Boolean);
  const uniquePolicies = Array.from(new Set(policies));
  const uniqueGroups = Array.from(new Set(groups));
  if (!uniquePolicies.length && !uniqueGroups.length) {
    return "Not set";
  }
  return [...uniquePolicies, ...uniqueGroups].join(", ");
}

export default function UsersPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["users"], queryFn: getUsers });

  return (
    <div className="page">
      <PageTitle eyebrow="ENTRY POINT" title="Users" description="Search local registry users, assigned tenants, suites, profiles, and latest UniFi state." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<User>
        ariaLabel="Users"
        rows={data?.users ?? []}
        isLoading={isLoading}
        searchText={(user) => `${user.name} ${user.email} ${user.company?.name ?? ""} ${user.suite?.suite_number ?? ""} ${user.status} ${accessSummary(user)}`}
        columns={[
          { key: "name", label: "Name", render: (user) => user.name, sortable: true },
          { key: "email", label: "Email", render: (user) => user.email, sortable: true },
          { key: "company", label: "Company", render: (user) => user.company?.name ?? "Unassigned", sortable: true },
          { key: "suite", label: "Suite", render: (user) => user.suite?.suite_number ?? "Unassigned", sortable: true },
          { key: "access", label: "Access Policy / Group", render: accessSummary, sortable: true },
          { key: "status", label: "Status", render: (user) => <StatusBadge value={user.status} /> },
          { key: "verified", label: "Verified", render: (user) => formatDate(user.last_verified_at), sortable: true }
        ]}
      />
    </div>
  );
}
