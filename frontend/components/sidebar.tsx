"use client";

import { Button, Divider } from "@heroui/react";
import {
  AlertTriangle,
  Building2,
  ClipboardList,
  DatabaseZap,
  DoorOpen,
  FileClock,
  FileText,
  Gauge,
  Layers3,
  LogOut,
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
      { href: "/dashboard/sync-jobs", label: "Sync Jobs", icon: DatabaseZap }
    ]
  },
  {
    label: "Reports",
    items: [
      { href: "/dashboard/reports", label: "Reports", icon: FileText },
      { href: "/dashboard/audit-log", label: "Audit Log", icon: FileClock }
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
      <div className="sidebar-brand">
        <Link href="/dashboard" className="flex min-w-0 items-center gap-3">
          <div className="brand-mark">
            <ShieldCheck size={22} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold leading-tight">Building Access Registry</div>
            <div className="mt-0.5 text-xs text-default-500">Access operations</div>
          </div>
        </Link>
        <ThemeToggle />
      </div>
      <Divider className="my-5" />
      <Link href="/dashboard" className={`nav-item nav-overview ${pathname === "/dashboard" ? "active" : ""}`}>
        <Gauge size={18} />
        <span className="truncate text-sm font-semibold">Dashboard</span>
      </Link>
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
      <Divider className="my-5" />
      <Link href="/dashboard/bootstrap" className={`nav-item ${pathname.startsWith("/dashboard/bootstrap") ? "active" : ""}`}>
        <DatabaseZap size={18} />
        <span className="truncate text-sm font-semibold">Bootstrap Users</span>
      </Link>
      <Link href="/dashboard/settings" className={`nav-item ${pathname.startsWith("/dashboard/settings") ? "active" : ""}`}>
        <Settings size={18} />
        <span className="truncate text-sm font-semibold">Settings</span>
      </Link>
      <div className="mt-6">
        <Button fullWidth variant="flat" startContent={<LogOut size={17} />} onPress={handleLogout}>
          Log out
        </Button>
      </div>
    </aside>
  );
}
