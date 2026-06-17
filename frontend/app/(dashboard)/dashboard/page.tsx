"use client";

import { Button, Card, CardBody, Spinner } from "@heroui/react";
import {
  AlertTriangle,
  Building2,
  ClipboardList,
  DatabaseZap,
  DoorOpen,
  FileStack,
  Layers3,
  ShieldCheck,
  Users
} from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BarMetricChart, DonutMetricChart } from "@/components/charts";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { PageTitle } from "@/components/page-title";
import { StatusBadge } from "@/components/status-badge";
import { getDashboard } from "@/services/dashboard";
import { formatDate } from "@/services/client";
import type { AccessRequest, Conflict, SyncJob } from "@/types/api";

const shortcuts = [
  { href: "/dashboard/requests", label: "Requests", icon: ClipboardList },
  { href: "/dashboard/users", label: "Users", icon: Users },
  { href: "/dashboard/companies", label: "Companies", icon: Building2 },
  { href: "/dashboard/suites", label: "Suites", icon: DoorOpen },
  { href: "/dashboard/occupancy", label: "Occupancy", icon: Layers3 },
  { href: "/dashboard/access-profiles", label: "Access Profiles", icon: ShieldCheck },
  { href: "/dashboard/conflicts", label: "Conflicts", icon: AlertTriangle },
  { href: "/dashboard/sync-jobs", label: "Sync Jobs", icon: DatabaseZap },
  { href: "/dashboard/bootstrap", label: "Bootstrap Users", icon: FileStack }
];

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });

  if (error) return <div className="page text-danger">{error.message}</div>;
  if (isLoading || !data) return <div className="page flex justify-center py-20"><Spinner /></div>;

  return (
    <div className="page">
      <PageTitle
        eyebrow="Operations"
        title="Building access dashboard"
        description="Live registry health, review queues, conflicts, and dry-run synchronization activity."
      />
      <div className="dashboard-grid">
        <KpiCard label="Active Users" value={data.stats.active_users ?? 0} icon={Users} trend="Source-of-truth registry" tone="success" />
        <KpiCard label="Pending Requests" value={data.stats.pending_requests ?? 0} icon={ClipboardList} trend="Awaiting admin review" tone="warning" />
        <KpiCard label="Open Conflicts" value={data.stats.open_conflicts ?? 0} icon={AlertTriangle} trend="Needs reconciliation review" tone="danger" />
        <KpiCard label="Stale Verifications" value={data.stats.stale_verification ?? 0} icon={ShieldCheck} trend="Older than 90 days" tone="warning" />
        <KpiCard label="Sync Failures" value={data.stats.sync_failures ?? 0} icon={DatabaseZap} trend="Dry-run or worker failures" tone="danger" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {shortcuts.map((item) => {
          const Icon = item.icon;
          return (
            <Card key={item.href} radius="sm" shadow="sm" isPressable as={Link} href={item.href}>
              <CardBody className="flex-row items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-primary-100 p-2 text-primary"><Icon size={18} /></div>
                  <span className="font-semibold">{item.label}</span>
                </div>
                <Button size="sm" variant="light">Open</Button>
              </CardBody>
            </Card>
          );
        })}
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        <BarMetricChart title="Sync Activity" data={data.analytics.sync_activity} />
        <DonutMetricChart title="Conflict Summary" data={data.analytics.conflict_summary} />
        <BarMetricChart title="Verification Status" data={data.analytics.verification_status} />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        <DataTable<AccessRequest>
          ariaLabel="Recent requests"
          rows={data.recent_requests}
          searchText={(row) => `${row.requested_for_first_name} ${row.requested_for_last_name} ${row.status}`}
          columns={[
            { key: "person", label: "Person", render: (row) => `${row.requested_for_first_name} ${row.requested_for_last_name}`, sortable: true },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "created", label: "Created", render: (row) => formatDate(row.created_at), sortable: true }
          ]}
        />
        <DataTable<SyncJob>
          ariaLabel="Recent sync jobs"
          rows={data.recent_sync_jobs}
          searchText={(row) => `${row.job_type} ${row.status}`}
          columns={[
            { key: "job", label: "Job", render: (row) => row.job_type, sortable: true },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "created", label: "Created", render: (row) => formatDate(row.created_at), sortable: true }
          ]}
        />
        <DataTable<Conflict>
          ariaLabel="Recent conflicts"
          rows={data.recent_conflicts}
          searchText={(row) => `${row.conflict_type} ${row.severity} ${row.status}`}
          columns={[
            { key: "type", label: "Type", render: (row) => row.conflict_type.replaceAll("_", " "), sortable: true },
            { key: "severity", label: "Severity", render: (row) => <StatusBadge value={row.severity} /> },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> }
          ]}
        />
      </div>
    </div>
  );
}
