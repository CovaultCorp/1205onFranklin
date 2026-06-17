import { Card, CardBody } from "@heroui/react";
import type { LucideIcon } from "lucide-react";

const toneClasses = {
  primary: "bg-primary-100 text-primary",
  warning: "bg-warning-100 text-warning",
  danger: "bg-danger-100 text-danger",
  success: "bg-success-100 text-success"
};

export function KpiCard({
  label,
  value,
  trend,
  icon: Icon,
  tone = "primary"
}: {
  label: string;
  value: number;
  trend?: string;
  icon: LucideIcon;
  tone?: "primary" | "warning" | "danger" | "success";
}) {
  return (
    <Card radius="sm" shadow="sm">
      <CardBody className="gap-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-default-500">{label}</span>
          <div className={`rounded-lg p-2 ${toneClasses[tone]}`}>
            <Icon size={18} />
          </div>
        </div>
        <div className="text-3xl font-bold">{value}</div>
        <div className="text-xs text-default-500">{trend ?? "Current registry state"}</div>
      </CardBody>
    </Card>
  );
}
