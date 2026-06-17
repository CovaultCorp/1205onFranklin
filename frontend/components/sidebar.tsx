"use client";

import { Button, Divider } from "@heroui/react";
import {
  AlertTriangle,
  Building2,
  ClipboardList,
  DatabaseZap,
  DoorOpen,
  FileClock,
  FileStack,
  FileText,
  Gauge,
  Layers3,
  LogOut,
  Send,
  Settings,
  ShieldCheck,
  Users
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/services/auth";
import { ThemeToggle } from "./theme-toggle";

const groups = [
  {
    label: "Dashboard",
    items: [{ href: "/dashboard", label: "Overview", icon: Gauge }]
  },
  {
    label: "Access Management",
    items: [
      { href: "/dashboard/requests", label: "Requests", icon: ClipboardList },
      { href: "/dashboard/users", label: "Users", icon: Users },
      { href: "/dashboard/access-profiles", label: "Access Profiles", icon: ShieldCheck }
    ]
  },
  {
    label: "Property Data",
    items: [
      { href: "/dashboard/companies", label: "Companies", icon: Building2 },
      { href: "/dashboard/suites", label: "Suites", icon: DoorOpen },
      { href: "/dashboard/occupancy", label: "Occupancy", icon: Layers3 }
    ]
  },
  {
    label: "Operations",
    items: [
      { href: "/dashboard/conflicts", label: "Conflicts", icon: AlertTriangle },
      { href: "/dashboard/sync-jobs", label: "Sync Jobs", icon: DatabaseZap },
      { href: "/dashboard/bootstrap", label: "Bootstrap Users", icon: FileStack }
    ]
  },
  {
    label: "Reports",
    items: [
      { href: "/dashboard/reports", label: "Reports", icon: FileText },
      { href: "/dashboard/audit-log", label: "Audit Log", icon: FileClock }
    ]
  },
  {
    label: "System",
    items: [
      { href: "/dashboard/settings", label: "Settings", icon: Settings },
      { href: "/request-access", label: "Request Access", icon: Send }
    ]
  }
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      <div className="flex items-center justify-between gap-3">
        <Link href="/dashboard" className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-white">
            <ShieldCheck size={22} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-base font-bold leading-tight">Building Access Registry</div>
            <div className="text-xs text-default-500">UniFi sync control</div>
          </div>
        </Link>
        <ThemeToggle />
      </div>
      <Divider className="my-5" />
      <nav className="nav-list">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="nav-section">{group.label}</div>
            <div className="grid gap-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link key={item.href} href={item.href} className={`nav-item ${active ? "active" : ""}`}>
                    <Icon size={18} />
                    <span className="truncate text-sm font-semibold">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="mt-6">
        <Button fullWidth variant="flat" startContent={<LogOut size={17} />} onPress={handleLogout}>
          Log out
        </Button>
      </div>
    </aside>
  );
}
