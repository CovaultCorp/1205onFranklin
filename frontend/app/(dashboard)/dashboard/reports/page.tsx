"use client";

import {
  Button,
  Card,
  CardBody,
  Input,
  Select,
  SelectItem,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow
} from "@heroui/react";
import { Download, FilePlus2, Mail } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, formatDate } from "@/lib/api";

type Lookup = { id: number; name?: string; suite_number?: string };
type ReportRun = {
  id: number;
  report_type: string;
  status: string;
  recipient_email?: string;
  created_at: string;
  sent_at?: string;
};

export default function ReportsPage() {
  const [companies, setCompanies] = useState<Lookup[]>([]);
  const [suites, setSuites] = useState<Lookup[]>([]);
  const [runs, setRuns] = useState<ReportRun[]>([]);
  const [reportType, setReportType] = useState("full_building_access");
  const [sendEmail, setSendEmail] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    const [lookups, reportRuns] = await Promise.all([
      apiFetch<{ companies: Lookup[]; suites: Lookup[] }>("/admin/lookups"),
      apiFetch<{ runs: ReportRun[] }>("/admin/reports/runs")
    ]);
    setCompanies(lookups.companies);
    setSuites(lookups.suites);
    setRuns(reportRuns.runs);
  }

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const payload = {
      report_type: reportType,
      company_id: data.company_id ? Number(data.company_id) : null,
      suite_id: data.suite_id ? Number(data.suite_id) : null,
      recipient_email: data.recipient_email || null,
      send_email: sendEmail
    };
    try {
      const result = await apiFetch<{ run: ReportRun }>("/admin/reports/generate", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      const detail = await apiFetch<{ report_html: string }>(`/admin/reports/runs/${result.run.id}`);
      setPreviewHtml(detail.report_html);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate report");
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="eyebrow">Reports</div>
          <h1 className="text-3xl font-bold">Preview and send reports</h1>
        </div>
      </div>
      <div className="section-grid">
        <Card radius="sm">
          <CardBody>
            <form className="grid gap-4" onSubmit={submit}>
              <Select label="Report type" selectedKeys={[reportType]} onChange={(event) => setReportType(event.target.value)}>
                <SelectItem key="full_building_access">Full building access</SelectItem>
                <SelectItem key="company_users">Users by company</SelectItem>
                <SelectItem key="suite_users">Users by suite</SelectItem>
              </Select>
              {reportType === "company_users" ? (
                <Select name="company_id" label="Company" isRequired>
                  {companies.map((company) => <SelectItem key={company.id}>{company.name}</SelectItem>)}
                </Select>
              ) : null}
              {reportType === "suite_users" ? (
                <Select name="suite_id" label="Suite" isRequired>
                  {suites.map((suite) => <SelectItem key={suite.id}>{suite.suite_number}</SelectItem>)}
                </Select>
              ) : null}
              <Switch isSelected={sendEmail} onValueChange={setSendEmail}>Send email</Switch>
              {sendEmail ? <Input name="recipient_email" type="email" label="Recipient email" isRequired /> : null}
              {error ? <p className="text-sm text-danger">{error}</p> : null}
              <Button color="primary" type="submit" startContent={sendEmail ? <Mail size={17} /> : <FilePlus2 size={17} />}>
                {sendEmail ? "Generate and send" : "Generate preview"}
              </Button>
            </form>
            {previewHtml ? (
              <div className="mt-5">
                <h2 className="mb-3 text-lg font-bold">Latest preview</h2>
                <div className="report-preview" dangerouslySetInnerHTML={{ __html: previewHtml }} />
              </div>
            ) : null}
          </CardBody>
        </Card>
        <Card radius="sm">
          <CardBody>
            <h2 className="mb-3 text-lg font-bold">Report runs</h2>
            {loading ? <Spinner /> : (
              <Table aria-label="Report runs" removeWrapper>
                <TableHeader>
                  <TableColumn>Type</TableColumn>
                  <TableColumn>Status</TableColumn>
                  <TableColumn>Created</TableColumn>
                  <TableColumn>CSV</TableColumn>
                </TableHeader>
                <TableBody emptyContent="No reports yet">
                  {runs.map((run) => (
                    <TableRow key={run.id}>
                      <TableCell>{run.report_type.replaceAll("_", " ")}</TableCell>
                      <TableCell><StatusBadge value={run.status} /></TableCell>
                      <TableCell>{formatDate(run.created_at)}</TableCell>
                      <TableCell>
                        <Button as="a" href={`/api/backend/admin/reports/runs/${run.id}/download-csv`} isIconOnly size="sm" variant="flat">
                          <Download size={15} />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
