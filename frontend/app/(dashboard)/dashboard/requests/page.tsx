"use client";

import {
  Button,
  Card,
  CardBody,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Select,
  SelectItem,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableColumn,
  TableHeader,
  TableRow,
  Textarea,
  useDisclosure
} from "@heroui/react";
import { CheckCircle2, CircleSlash, MessageSquareMore } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, formatDate } from "@/lib/api";

type Lookup = { id: number; name?: string; suite_number?: string };
type RequestRow = {
  id: number;
  request_type: string;
  status: string;
  requested_for_first_name: string;
  requested_for_last_name: string;
  requested_for_email: string;
  requested_for_company_text?: string;
  requested_for_suite_text?: string;
  reason?: string;
  created_at: string;
};

export default function RequestsPage() {
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [companies, setCompanies] = useState<Lookup[]>([]);
  const [suites, setSuites] = useState<Lookup[]>([]);
  const [profiles, setProfiles] = useState<Lookup[]>([]);
  const [selected, setSelected] = useState<RequestRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState("");
  const modal = useDisclosure();

  async function load() {
    const [requestData, lookupData] = await Promise.all([
      apiFetch<{ requests: RequestRow[] }>("/admin/requests"),
      apiFetch<{ companies: Lookup[]; suites: Lookup[]; profiles: Lookup[] }>("/admin/lookups")
    ]);
    setRequests(requestData.requests);
    setCompanies(lookupData.companies);
    setSuites(lookupData.suites);
    setProfiles(lookupData.profiles);
  }

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  function open(row: RequestRow) {
    setSelected(row);
    setActionError("");
    modal.onOpen();
  }

  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const payload = {
      requested_for_company_id: data.requested_for_company_id ? Number(data.requested_for_company_id) : null,
      requested_for_suite_id: data.requested_for_suite_id ? Number(data.requested_for_suite_id) : null,
      requested_access_profile_id: data.requested_access_profile_id ? Number(data.requested_access_profile_id) : null,
      admin_notes: data.admin_notes
    };
    try {
      await apiFetch(`/admin/requests/${selected.id}/approve`, { method: "POST", body: JSON.stringify(payload) });
      await load();
      modal.onClose();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Unable to approve request");
    }
  }

  async function updateStatus(path: string, body: Record<string, string>) {
    if (!selected) return;
    try {
      await apiFetch(`/admin/requests/${selected.id}/${path}`, { method: "POST", body: JSON.stringify(body) });
      await load();
      modal.onClose();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="eyebrow">Workflow</div>
          <h1 className="text-3xl font-bold">Admin review</h1>
        </div>
      </div>
      <Card radius="sm">
        <CardBody>
          {loading ? <Spinner /> : (
            <Table aria-label="Access requests" removeWrapper>
              <TableHeader>
                <TableColumn>Person</TableColumn>
                <TableColumn>Type</TableColumn>
                <TableColumn>Status</TableColumn>
                <TableColumn>Company</TableColumn>
                <TableColumn>Created</TableColumn>
                <TableColumn>Action</TableColumn>
              </TableHeader>
              <TableBody emptyContent="No access requests">
                {requests.map((request) => (
                  <TableRow key={request.id}>
                    <TableCell>
                      <div className="font-semibold">{request.requested_for_first_name} {request.requested_for_last_name}</div>
                      <div className="text-xs text-default-500">{request.requested_for_email}</div>
                    </TableCell>
                    <TableCell>{request.request_type.replaceAll("_", " ")}</TableCell>
                    <TableCell><StatusBadge value={request.status} /></TableCell>
                    <TableCell>{request.requested_for_company_text ?? "Not supplied"}</TableCell>
                    <TableCell>{formatDate(request.created_at)}</TableCell>
                    <TableCell><Button size="sm" variant="flat" onPress={() => open(request)}>Review</Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>
      <Modal isOpen={modal.isOpen} onOpenChange={modal.onOpenChange} size="2xl" scrollBehavior="inside">
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>{selected ? `${selected.requested_for_first_name} ${selected.requested_for_last_name}` : "Request"}</ModalHeader>
              <ModalBody>
                {selected ? (
                  <>
                    <div className="grid gap-2 rounded-lg border border-default-200 p-3 text-sm">
                      <div><strong>Email:</strong> {selected.requested_for_email}</div>
                      <div><strong>Company:</strong> {selected.requested_for_company_text ?? "Not supplied"}</div>
                      <div><strong>Suite:</strong> {selected.requested_for_suite_text ?? "Not supplied"}</div>
                      <div><strong>Reason:</strong> {selected.reason ?? "None"}</div>
                    </div>
                    <form className="grid gap-3" id="approve-request-form" onSubmit={approve}>
                      <Select name="requested_for_company_id" label="Company">
                        {companies.map((company) => <SelectItem key={company.id}>{company.name}</SelectItem>)}
                      </Select>
                      <Select name="requested_for_suite_id" label="Suite">
                        {suites.map((suite) => <SelectItem key={suite.id}>{suite.suite_number}</SelectItem>)}
                      </Select>
                      <Select name="requested_access_profile_id" label="Access profile">
                        {profiles.map((profile) => <SelectItem key={profile.id}>{profile.name}</SelectItem>)}
                      </Select>
                      <Textarea name="admin_notes" label="Admin notes" />
                    </form>
                    {actionError ? <p className="text-sm text-danger">{actionError}</p> : null}
                  </>
                ) : null}
              </ModalBody>
              <ModalFooter className="flex-wrap justify-between">
                <Button variant="flat" onPress={onClose}>Close</Button>
                <div className="flex flex-wrap gap-2">
                  <Button startContent={<MessageSquareMore size={16} />} variant="flat" onPress={() => updateStatus("needs-info", { admin_notes: "More information requested." })}>
                    Needs info
                  </Button>
                  <Button startContent={<CircleSlash size={16} />} color="danger" variant="flat" onPress={() => updateStatus("deny", { denial_reason: "Denied by admin." })}>
                    Deny
                  </Button>
                  <Button startContent={<CheckCircle2 size={16} />} color="primary" type="submit" form="approve-request-form">
                    Approve
                  </Button>
                </div>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>
    </div>
  );
}
