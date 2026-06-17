"use client";

import { Card, CardBody, Input, Pagination, Spinner, Table, TableBody, TableCell, TableColumn, TableHeader, TableRow } from "@heroui/react";
import { Search } from "lucide-react";
import { ReactNode, useMemo, useState } from "react";

export type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
};

export function DataTable<T extends { id: number | string }>({
  ariaLabel,
  rows,
  columns,
  searchText,
  isLoading,
  emptyContent = "No records found"
}: {
  ariaLabel: string;
  rows: T[];
  columns: Column<T>[];
  searchText: (row: T) => string;
  isLoading?: boolean;
  emptyContent?: string;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [direction, setDirection] = useState<"asc" | "desc">("asc");
  const pageSize = 10;

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    const next = rows.filter((row) => searchText(row).toLowerCase().includes(q));
    if (!sortKey) return next;
    const column = columns.find((item) => item.key === sortKey);
    if (!column) return next;
    return [...next].sort((a, b) => {
      const av = String(column.render(a) ?? "");
      const bv = String(column.render(b) ?? "");
      return direction === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [columns, direction, query, rows, searchText, sortKey]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize);

  function toggleSort(key: string, sortable?: boolean) {
    if (!sortable) return;
    if (sortKey === key) {
      setDirection(direction === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setDirection("asc");
    }
  }

  return (
    <Card radius="sm" shadow="sm">
      <CardBody className="gap-4">
        <Input
          aria-label={`Search ${ariaLabel}`}
          className="max-w-sm"
          placeholder="Search"
          startContent={<Search size={17} />}
          value={query}
          onValueChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
        />
        {isLoading ? (
          <div className="flex justify-center py-10"><Spinner /></div>
        ) : (
          <Table aria-label={ariaLabel} removeWrapper>
            <TableHeader>
              {columns.map((column) => (
                <TableColumn key={column.key} onClick={() => toggleSort(column.key, column.sortable)}>
                  <span className={column.sortable ? "cursor-pointer select-none" : ""}>{column.label}</span>
                </TableColumn>
              ))}
            </TableHeader>
            <TableBody emptyContent={emptyContent}>
              {visible.map((row) => (
                <TableRow key={row.id}>
                  {columns.map((column) => <TableCell key={column.key}>{column.render(row)}</TableCell>)}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <div className="flex justify-end">
          <Pagination page={page} total={pages} onChange={setPage} showControls />
        </div>
      </CardBody>
    </Card>
  );
}
