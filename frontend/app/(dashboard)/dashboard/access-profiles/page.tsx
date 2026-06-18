"use client";

import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/data-table";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { getAccessProfiles } from "@/services/property";
import type { AccessProfile } from "@/types/api";

export default function AccessProfilesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["access-profiles"], queryFn: getAccessProfiles });

  return (
    <div className="page">
      <PageTitle eyebrow="Access Management" title="Access Profiles" description="Local access templates, UniFi policy references, group mappings, and assignment counts." />
      {error ? <p className="text-danger">{error.message}</p> : null}
      <DataTable<AccessProfile>
        ariaLabel="Access profiles"
        rows={data?.profiles ?? []}
        isLoading={isLoading}
        searchText={(profile) => `${profile.name} ${profile.description ?? ""}`}
        columns={[
          { key: "name", label: "Profile", render: (profile) => profile.name, sortable: true },
          { key: "assignments", label: "Assignments", render: (profile) => profile.assignment_count, sortable: true },
          { key: "policies", label: "Policy IDs", render: (profile) => profile.unifi_access_policy_ids.length, sortable: true },
          { key: "groups", label: "Group IDs", render: (profile) => profile.unifi_user_group_ids.length, sortable: true },
          { key: "status", label: "Status", render: (profile) => <StatusBadge value={profile.active ? "active" : "inactive"} /> }
        ]}
      />
    </div>
  );
}
