"use client";

import { Card, CardBody, Input, Spinner, Table, TableBody, TableCell, TableColumn, TableHeader, TableRow } from "@nextui-org/react";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, formatDate } from "@/lib/api";

type UserRow = {
  id: number;
  name: string;
  email: string;
  employee_number?: string;
  company?: { name: string };
  suite?: { suite_number: string };
  status: string;
  last_verified_at?: string;
};

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{ users: UserRow[] }>("/admin/users").then((data) => setUsers(data.users)).finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return users.filter((user) => [user.name, user.email, user.company?.name, user.suite?.suite_number].some((value) => value?.toLowerCase().includes(q)));
  }, [users, query]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="eyebrow">Registry</div>
          <h1 className="text-3xl font-bold">Users</h1>
        </div>
        <Input className="max-w-xs" startContent={<Search size={17} />} placeholder="Search users" value={query} onValueChange={setQuery} />
      </div>
      <Card radius="sm">
        <CardBody>
          {loading ? <Spinner /> : (
            <Table aria-label="Users table" removeWrapper>
              <TableHeader>
                <TableColumn>Name</TableColumn>
                <TableColumn>Email</TableColumn>
                <TableColumn>Company</TableColumn>
                <TableColumn>Suite</TableColumn>
                <TableColumn>Status</TableColumn>
                <TableColumn>Verified</TableColumn>
              </TableHeader>
              <TableBody emptyContent="No users found">
                {filtered.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell>{user.name}</TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>{user.company?.name ?? "Unassigned"}</TableCell>
                    <TableCell>{user.suite?.suite_number ?? "Unassigned"}</TableCell>
                    <TableCell><StatusBadge value={user.status} /></TableCell>
                    <TableCell>{formatDate(user.last_verified_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
