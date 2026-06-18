"use client";

import { Button, Card, CardBody, Chip, Spinner } from "@heroui/react";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  ClipboardList,
  DatabaseZap,
  DoorOpen,
  Layers3,
  ShieldCheck,
  Users
} from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BarMetricChart, DonutMetricChart } from "@/components/charts";
import { DataTable } from "@/components/data-table";
import { KpiCard } from "@/components/kpi-card";
import { StatusBadge } from "@/components/status-badge";
import { getDashboard } from "@/services/dashboard";
import { formatDate } from "@/services/client";
import type { AccessRequest, Conflict, SyncJob } from "@/types/api";

const modules = [
  {
    href: "/dashboard/requests",
    title: "Requests",
    description: "Review submitted access changes and approvals.",
    icon: ClipboardList,
    tone: "primary"
  },
  {
    href: "/dashboard/users",
    title: "Users",
    description: "Search local registry users and access state.",
    icon: Users,
    tone: "success"
  },
  {
    href: "/dashboard/companies",
    title: "Companies",
    description: "Manage tenant organizations and contacts.",
    icon: Building2,
    tone: "primary"
  },
  {
    href: "/dashboard/suites",
    title: "Suites",
    description: "Review suite inventory and assignments.",
    icon: DoorOpen,
    tone: "warning"
  },
  {
    href: "/dashboard/occupancy",
    title: "Occupancy",
    description: "Track company-suite occupancy relationships.",
    icon: Layers3,
    tone: "primary"
  },
  {
    href: "/dashboard/access-profiles",
    title: "Access Profiles",
    description: "View local profile templates and mappings.",
    icon: ShieldCheck,
    tone: "success"
  },
  {
    href: "/dashboard/conflicts",
    title: "Conflicts",
    description: "Resolve reconciliation exceptions.",
    icon: AlertTriangle,
    tone: "danger"
  },
  {
    href: "/dashboard/sync-jobs",
    title: "Sync Jobs",
    description: "Inspect dry-run jobs and worker outcomes.",
    icon: DatabaseZap,
    tone: "warning"
  },
  {
    href: "/dashboard/reports",
    title: "Reports",
    description: "Generate previews, CSV exports, and emails.",
    icon: ClipboardList,
    tone: "primary"
  }
] as const;

const toneClasses = {
  primary: "bg-primary-100 text-primary",
  success: "bg-success-100 text-success",
  warning: "bg-warning-100 text-warning",
  danger: "bg-danger-100 text-danger"
};

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });

  if (error) return <div className="page text-danger">{error.message}</div>;
  if (isLoading || !data) return <div className="page flex justify-center py-20"><Spinner /></div>;

  const syncFailures = data.stats.sync_failures ?? 0;
  const openConflicts = data.stats.open_conflicts ?? 0;

  return (
    <div className="page">
      <section className="dashboard-hero">
        <div>
          <div className="eyebrow">Building Access Registry</div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight md:text-4xl">Operations dashboard</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-default-500">
            Monitor the local registry source of truth, review access workflows, and keep UniFi sync planning visible without enabling write behavior.
          </p>
        </div>
        <div className="dashboard-hero-actions">
          <Chip color={syncFailures ? "danger" : "success"} variant="flat">
            {syncFailures ? `${syncFailures} sync failures` : "Sync healthy"}
          </Chip>
          <Chip color={openConflicts ? "warning" : "success"} variant="flat">
            {openConflicts ? `${openConflicts} conflicts open` : "No open conflicts"}
          </Chip>
          <Button as={Link} href="/dashboard/requests" color="primary" endContent={<ArrowRight size={16} />}>
            Review requests
          </Button>
        </div>
      </section>

      <section className="dashboard-grid kpi-grid">
        <KpiCard
          label="Active Users"
          value={data.stats.active_users ?? 0}
          icon={Users}
          helper="People currently active in the registry"
          trend="Source-of-truth"
          tone="success"
        />
        <KpiCard
          label="Pending Requests"
          value={data.stats.pending_requests ?? 0}
          icon={ClipboardList}
          helper="Submitted items awaiting admin action"
          trend="Approval queue"
          tone="warning"
        />
        <KpiCard
          label="Open Conflicts"
          value={openConflicts}
          icon={AlertTriangle}
          helper="Reconciliation issues needing review"
          trend="Operational risk"
          tone={openConflicts ? "danger" : "success"}
        />
        <KpiCard
          label="Stale Verifications"
          value={data.stats.stale_verification ?? 0}
          icon={ShieldCheck}
          helper="Active users not verified recently"
          trend="90 day threshold"
          tone="warning"
        />
      </section>

      <section className="mt-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">Management shortcuts</h2>
            <p className="mt-1 text-sm text-default-500">Jump into the modules used most often by building operations.</p>
          </div>
        </div>
        <div className="module-grid">
          {modules.map((item) => {
            const Icon = item.icon;
            return (
              <Card key={item.href} className="module-card" radius="sm" shadow="sm" isPressable as={Link} href={item.href}>
                <CardBody className="gap-4 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className={`rounded-xl p-3 ${toneClasses[item.tone]}`}>
                      <Icon size={20} />
                    </div>
                    <ArrowRight className="text-default-400" size={18} />
                  </div>
                  <div>
                    <h3 className="text-base font-bold">{item.title}</h3>
                    <p className="mt-1 text-sm leading-5 text-default-500">{item.description}</p>
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      </section>

      <section className="mt-8 grid gap-4 xl:grid-cols-3">
        <BarMetricChart title="Sync Activity" data={data.analytics.sync_activity} />
        <DonutMetricChart title="Conflict Summary" data={data.analytics.conflict_summary} />
        <BarMetricChart title="Verification Status" data={data.analytics.verification_status} />
      </section>

      <section className="mt-8">
        <div className="mb-4">
          <h2 className="text-xl font-bold">Recent activity</h2>
          <p className="mt-1 text-sm text-default-500">Latest requests, dry-run sync work, and conflicts from the backend.</p>
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <DataTable<AccessRequest>
            ariaLabel="Recent requests"
            rows={data.recent_requests}
            emptyContent="No recent requests"
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
            emptyContent="No recent sync jobs"
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
            emptyContent="No recent conflicts"
            searchText={(row) => `${row.conflict_type} ${row.severity} ${row.status}`}
            columns={[
              { key: "type", label: "Type", render: (row) => row.conflict_type.replaceAll("_", " "), sortable: true },
              { key: "severity", label: "Severity", render: (row) => <StatusBadge value={row.severity} /> },
              { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> }
            ]}
          />
        </div>
      </section>
    </div>
  );
}
