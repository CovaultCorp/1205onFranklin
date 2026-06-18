"use client";

import { Chip } from "@heroui/react";
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

function sourceChip(user: User) {
  return (
    <Chip size="sm" variant="flat" color={user.data_source?.includes("UniFi") ? "primary" : "default"}>
      {user.data_source ?? "Entry Point"}
    </Chip>
  );
}

function suiteLabel(user: User) {
  if (user.suite?.suite_number) return user.suite.suite_number;
  if (user.unifi_suite_number) return `UniFi ${user.unifi_suite_number}`;
  return "Unassigned";
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
        emptyContent="No Entry Point or UniFi Access users found"
        searchText={(user) => `${user.name} ${user.email} ${user.company?.name ?? ""} ${suiteLabel(user)} ${user.status} ${user.unifi_status ?? ""} ${user.data_source ?? ""} ${accessSummary(user)}`}
        columns={[
          { key: "name", label: "Name", render: (user) => user.name, sortable: true },
          { key: "source", label: "Source", render: sourceChip, sortable: true },
          { key: "email", label: "Email", render: (user) => user.email || "No email", sortable: true },
          { key: "company", label: "Company", render: (user) => user.company?.name ?? "Unassigned", sortable: true },
          { key: "suite", label: "Suite", render: suiteLabel, sortable: true },
          { key: "unifi_status", label: "UniFi Status", render: (user) => <StatusBadge value={user.unifi_status ?? user.status} /> },
          { key: "access", label: "Access Policies / Groups", render: accessSummary, sortable: true },
          { key: "credentials", label: "Credentials", render: (user) => user.credential_summary ?? "Not synced", sortable: true },
          { key: "synced", label: "Last Synced", render: (user) => formatDate(user.last_synced_at), sortable: true }
        ]}
      />
    </div>
  );
}
