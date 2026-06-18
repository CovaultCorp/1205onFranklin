import { Card, CardBody, Chip } from "@heroui/react";
import type { LucideIcon } from "lucide-react";

const toneClasses = {
  primary: {
    icon: "bg-primary-100 text-primary",
    accent: "bg-primary",
    chip: "primary"
  },
  warning: {
    icon: "bg-warning-100 text-warning",
    accent: "bg-warning",
    chip: "warning"
  },
  danger: {
    icon: "bg-danger-100 text-danger",
    accent: "bg-danger",
    chip: "danger"
  },
  success: {
    icon: "bg-success-100 text-success",
    accent: "bg-success",
    chip: "success"
  }
};

export function KpiCard({
  label,
  value,
  trend,
  helper,
  icon: Icon,
  tone = "primary"
}: {
  label: string;
  value: number;
  trend?: string;
  helper?: string;
  icon: LucideIcon;
  tone?: "primary" | "warning" | "danger" | "success";
}) {
  const toneConfig = toneClasses[tone];

  return (
    <Card className="kpi-card" radius="sm" shadow="sm">
      <CardBody className="gap-4 p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <span className="text-sm font-semibold text-default-500">{label}</span>
            {helper ? <div className="mt-1 text-xs text-default-400">{helper}</div> : null}
          </div>
          <div className={`rounded-xl p-3 ${toneConfig.icon}`}>
            <Icon size={20} />
          </div>
        </div>
        <div className="flex items-end justify-between gap-3">
          <div className="text-4xl font-bold tracking-tight">{value.toLocaleString()}</div>
          <div className={`mb-2 h-2 w-2 rounded-full ${toneConfig.accent}`} />
        </div>
        <Chip color={toneConfig.chip as "primary" | "warning" | "danger" | "success"} size="sm" variant="flat">
          {trend ?? "Current registry state"}
        </Chip>
      </CardBody>
    </Card>
  );
}
