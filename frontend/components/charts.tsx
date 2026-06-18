"use client";

import { Card, CardBody } from "@heroui/react";
import { ChartNoAxesCombined } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const colors = ["#006fee", "#f5a524", "#f31260", "#17c964"];

export function BarMetricChart({ title, data }: { title: string; data: Array<{ label: string; value: number }> }) {
  const hasData = data.some((item) => item.value > 0);

  return (
    <Card className="dashboard-panel" radius="sm" shadow="sm">
      <CardBody className="p-5">
        <h2 className="mb-1 text-lg font-bold">{title}</h2>
        <p className="mb-4 text-sm text-default-500">Current operational distribution</p>
        <div className="h-64">
          {hasData ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#006fee" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChartState />
          )}
        </div>
      </CardBody>
    </Card>
  );
}

export function DonutMetricChart({ title, data }: { title: string; data: Array<{ label: string; value: number }> }) {
  const hasData = data.some((item) => item.value > 0);

  return (
    <Card className="dashboard-panel" radius="sm" shadow="sm">
      <CardBody className="p-5">
        <h2 className="mb-1 text-lg font-bold">{title}</h2>
        <p className="mb-4 text-sm text-default-500">Priority mix for active records</p>
        <div className="h-64">
          {hasData ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="label" innerRadius={58} outerRadius={90} paddingAngle={4}>
                  {data.map((entry, index) => <Cell key={entry.label} fill={colors[index % colors.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChartState />
          )}
        </div>
      </CardBody>
    </Card>
  );
}

function EmptyChartState() {
  return (
    <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-default-200 bg-default-50/60 text-center">
      <div className="mb-3 rounded-full bg-default-100 p-3 text-default-400">
        <ChartNoAxesCombined size={22} />
      </div>
      <div className="text-sm font-semibold">No activity yet</div>
      <div className="mt-1 max-w-48 text-xs text-default-500">Charts will populate as requests, sync jobs, and conflicts are recorded.</div>
    </div>
  );
}
