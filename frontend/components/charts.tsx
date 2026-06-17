"use client";

import { Card, CardBody } from "@heroui/react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const colors = ["#006fee", "#f5a524", "#f31260", "#17c964"];

export function BarMetricChart({ title, data }: { title: string; data: Array<{ label: string; value: number }> }) {
  return (
    <Card radius="sm" shadow="sm">
      <CardBody>
        <h2 className="mb-4 text-lg font-bold">{title}</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#006fee" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  );
}

export function DonutMetricChart({ title, data }: { title: string; data: Array<{ label: string; value: number }> }) {
  return (
    <Card radius="sm" shadow="sm">
      <CardBody>
        <h2 className="mb-4 text-lg font-bold">{title}</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="label" innerRadius={58} outerRadius={90} paddingAngle={4}>
                {data.map((entry, index) => <Cell key={entry.label} fill={colors[index % colors.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardBody>
    </Card>
  );
}
