"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  Search,
  MessageSquare,
  Upload,
  LayoutDashboard,
  Clock,
  Link2,
} from "lucide-react";
import clsx from "clsx";

const nav = [
  {
    group: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    ],
  },
  {
    group: "Documents",
    items: [
      { href: "/documents", label: "All Documents", icon: FileText },
      { href: "/upload", label: "Upload", icon: Upload },
      { href: "/review", label: "Review Queue", icon: Clock },
    ],
  },
  {
    group: "Intelligence",
    items: [
      { href: "/search", label: "Search", icon: Search },
      { href: "/chat", label: "AI Assistant", icon: MessageSquare },
    ],
  },
  {
    group: "Settings",
    items: [
      { href: "/webhooks", label: "Webhooks", icon: Link2 },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex h-full w-[var(--sidebar-width)] flex-col border-r border-slate-100 bg-white">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-5 border-b border-slate-100">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 shadow-sm">
          <span className="text-xs font-bold text-white">AN</span>
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold text-slate-900 leading-none tracking-tight">Allergo Nordic</p>
          <p className="text-[10px] text-slate-400 mt-0.5 leading-none">Document Platform</p>
        </div>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {nav.map(({ group, items }) => (
          <div key={group}>
            <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
              {group}
            </p>
            <div className="space-y-0.5">
              {items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
                return (
                  <Link
                    key={href}
                    href={href}
                    className={clsx(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                      active
                        ? "bg-brand-50 text-brand-700 shadow-sm"
                        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                    )}
                  >
                    <Icon
                      size={15}
                      className={active ? "text-brand-600" : "text-slate-400"}
                    />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-slate-100 bg-slate-50">
        <p className="text-[10px] text-slate-400 font-medium">CFO Document Platform</p>
        <p className="text-[10px] text-slate-300 mt-0.5">v0.1.0 · Powered by GPT-4o</p>
      </div>
    </aside>
  );
}
