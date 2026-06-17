"use client";

import { Card, CardBody, Spinner, Table, TableBody, TableCell, TableColumn, TableHeader, TableRow } from "@nextui-org/react";
import { AlertTriangle, ClipboardList, Database, FileText, ShieldCheck, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { apiFetch, formatDate } from "@/lib/api";
import { StatusBadge } from "@/components/status-badge";

type DashboardData = {
  stats: Record<string, number>;
  recent_reports: Array<{ id: number; report_type: string; status: string; created_at: string }>;
  recent_sync_jobs: Array<{ id: number; job_type: string; status: string; created_at: string }>;
};

const cards = [
  ["active_users", "Active users", Users],
  ["pending_requests", "Pending requests", ClipboardList],
  ["open_conflicts", "Open conflicts", AlertTriangle],
  ["unifi_snapshots", "UniFi snapshots", Database],
  ["missing_company", "Missing company", Users],
  ["missing_suite", "Missing suite", Users],
  ["stale_verification", "Stale verification", ShieldCheck],
  ["sync_failures", "Sync failures", AlertTriangle]
] as const;

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<DashboardData>("/admin/dashboard").then(setData).catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="page text-danger">{error}</div>;
  if (!data) return <div className="page flex justify-center py-20"><Spinner /></div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="eyebrow">Admin dashboard</div>
          <h1 className="text-3xl font-bold">Building access operations</h1>
        </div>
      </div>
      <div className="dashboard-grid">
        {cards.map(([key, label, Icon]) => (
          <Card key={key} radius="sm">
            <CardBody className="gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-default-500">{label}</span>
                <Icon size={18} className="text-primary" />
              </div>
              <div className="text-3xl font-bold">{data.stats[key] ?? 0}</div>
            </CardBody>
          </Card>
        ))}
      </div>
      <div className="section-grid">
        <Card radius="sm">
          <CardBody>
            <h2 className="mb-3 flex items-center gap-2 text-lg font-bold"><FileText size={18} /> Recent reports</h2>
            <Table aria-label="Recent reports" removeWrapper>
              <TableHeader>
                <TableColumn>Type</TableColumn>
                <TableColumn>Status</TableColumn>
                <TableColumn>Created</TableColumn>
              </TableHeader>
              <TableBody emptyContent="No report runs yet">
                {data.recent_reports.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>{run.report_type.replaceAll("_", " ")}</TableCell>
                    <TableCell><StatusBadge value={run.status} /></TableCell>
                    <TableCell>{formatDate(run.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>
        <Card radius="sm">
          <CardBody>
            <h2 className="mb-3 text-lg font-bold">Recent sync jobs</h2>
            <Table aria-label="Recent sync jobs" removeWrapper>
              <TableHeader>
                <TableColumn>Job</TableColumn>
                <TableColumn>Status</TableColumn>
              </TableHeader>
              <TableBody emptyContent="No sync jobs yet">
                {data.recent_sync_jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>{job.job_type}</TableCell>
                    <TableCell><StatusBadge value={job.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
