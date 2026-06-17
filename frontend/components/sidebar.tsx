"use client";

import { Button, Divider } from "@nextui-org/react";
import { ClipboardList, FileText, Gauge, LogOut, Send, ShieldCheck, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ThemeToggle } from "./theme-toggle";
import { apiFetch } from "@/lib/api";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: Gauge },
  { href: "/dashboard/requests", label: "Admin Review", icon: ClipboardList },
  { href: "/dashboard/users", label: "Users", icon: Users },
  { href: "/dashboard/reports", label: "Reports", icon: FileText },
  { href: "/request-access", label: "Request Access", icon: Send }
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    await apiFetch("/auth/logout", { method: "POST", body: "{}" });
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      <div className="flex items-center justify-between gap-3">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-white">
            <ShieldCheck size={22} />
          </div>
          <div>
            <div className="text-base font-bold leading-tight">Access Registry</div>
            <div className="text-xs text-default-500">UniFi sync control</div>
          </div>
        </Link>
        <ThemeToggle />
      </div>
      <Divider className="my-5" />
      <nav className="nav-list">
        {nav.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.href} href={item.href} className={`nav-item ${active ? "active" : ""}`}>
              <Icon size={18} />
              <span className="text-sm font-semibold">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="absolute bottom-6 left-4 right-4 hidden md:block">
        <Button fullWidth variant="flat" startContent={<LogOut size={17} />} onPress={logout}>
          Log out
        </Button>
      </div>
    </aside>
  );
}
