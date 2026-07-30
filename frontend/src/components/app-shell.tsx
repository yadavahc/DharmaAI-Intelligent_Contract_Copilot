"use client";

/**
 * Authenticated app shell: sidebar navigation, top bar, and system status.
 *
 * Navigation is role-filtered (Playbook Manager is admin-only), which mirrors the
 * backend's authorisation rather than replacing it — the API refuses unauthorised
 * writes regardless of what the UI shows.
 */

import {
  Activity,
  BadgeCheck,
  BookOpen,
  ChevronLeft,
  FileText,
  Gauge,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Swords,
  Upload,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { signOut, useSession } from "next-auth/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { AmbientBackground } from "@/components/ambient-background";
import { Badge, Button, Tooltip } from "@/components/ui/primitives";
import { AnimatePresence, PulseDot, motion } from "@/components/ui/motion";
import { api } from "@/lib/api";
import type { HealthResponse, UserRole } from "@/lib/types";
import { ROLE_LABELS, cn, initials } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  roles?: UserRole[];
  badge?: "reviews";
}

const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/contracts", label: "Contracts", icon: FileText },
      { href: "/upload", label: "Upload", icon: Upload },
    ],
  },
  {
    title: "Work",
    items: [
      { href: "/negotiations", label: "Negotiations", icon: Swords },
      { href: "/review", label: "Review Queue", icon: BadgeCheck, badge: "reviews" },
      { href: "/search", label: "Semantic Search", icon: Search },
    ],
  },
  {
    title: "Governance",
    items: [
      { href: "/playbook", label: "Playbook", icon: BookOpen, roles: ["ADMIN"] },
      { href: "/guardrails", label: "Guardrails", icon: ShieldCheck },
      { href: "/audit", label: "Audit Log", icon: Activity },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);
  const [health, setHealth] = React.useState<HealthResponse | null>(null);
  const [openReviews, setOpenReviews] = React.useState<number>(0);

  const role = (session?.user?.role ?? "BUSINESS_USER") as UserRole;

  // Close the mobile drawer on navigation.
  React.useEffect(() => setMobileOpen(false), [pathname]);

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [h, queue] = await Promise.all([
          api.health(),
          api.reviewQueue({ status: "open" }).catch(() => ({ count: 0 })),
        ]);
        if (!cancelled) {
          setHealth(h);
          setOpenReviews(queue.count ?? 0);
        }
      } catch {
        if (!cancelled) setHealth(null);
      }
    };
    load();
    const interval = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pathname]);

  const visibleSections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.roles || item.roles.includes(role)),
  })).filter((section) => section.items.length > 0);

  return (
    <div className="relative flex min-h-dvh">
      <AmbientBackground variant="mesh" intensity={0.45} />

      {/* ── desktop sidebar ── */}
      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-silver-50/[0.06] bg-base-900/50 backdrop-blur-xl lg:flex",
          "transition-[width] duration-300 ease-premium",
          collapsed ? "w-[76px]" : "w-64",
        )}
      >
        <SidebarContent
          sections={visibleSections}
          pathname={pathname}
          collapsed={collapsed}
          openReviews={openReviews}
        />
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="mx-3 mb-3 flex h-9 items-center justify-center gap-2 rounded-md border border-silver-50/[0.07] text-2xs font-semibold uppercase tracking-wider text-silver-500 transition-colors hover:border-silver-50/15 hover:text-silver-300"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft
            className={cn("size-3.5 transition-transform duration-300", collapsed && "rotate-180")}
          />
          {!collapsed && "Collapse"}
        </button>
      </aside>

      {/* ── mobile drawer ── */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
              className="fixed inset-0 z-40 bg-base-950/80 backdrop-blur-sm lg:hidden"
            />
            <motion.aside
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 34 }}
              className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-silver-50/10 bg-base-900/95 backdrop-blur-xl lg:hidden"
            >
              <div className="flex items-center justify-between px-4 pt-4">
                <Logo />
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setMobileOpen(false)}
                  aria-label="Close navigation"
                >
                  <X />
                </Button>
              </div>
              <SidebarContent
                sections={visibleSections}
                pathname={pathname}
                collapsed={false}
                openReviews={openReviews}
                hideLogo
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ── main column ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-silver-50/[0.06] bg-base-950/70 backdrop-blur-xl">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
            <Button
              variant="ghost"
              size="icon-sm"
              className="lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu />
            </Button>

            <div className="lg:hidden">
              <Logo compact />
            </div>

            <div className="ml-auto flex items-center gap-2 sm:gap-3">
              <SystemStatus health={health} />

              <div className="hidden items-center gap-2.5 rounded-full border border-silver-50/[0.08] bg-base-800/60 py-1 pl-1 pr-3 sm:flex">
                <div className="grid size-7 place-items-center rounded-full bg-accent/15 text-2xs font-bold text-accent-soft">
                  {initials(session?.user?.name ?? session?.user?.email)}
                </div>
                <div className="leading-tight">
                  <p className="max-w-[10rem] truncate text-xs font-medium text-silver-200">
                    {session?.user?.name ?? session?.user?.email ?? "Guest"}
                  </p>
                  <p className="text-[0.625rem] uppercase tracking-wider text-silver-500">
                    {ROLE_LABELS[role] ?? role}
                  </p>
                </div>
              </div>

              <Tooltip content="Settings">
                <Button variant="ghost" size="icon-sm" asChild>
                  <Link href="/settings" aria-label="Settings">
                    <Settings />
                  </Link>
                </Button>
              </Tooltip>

              <Tooltip content="Sign out">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => signOut({ callbackUrl: "/" })}
                  aria-label="Sign out"
                >
                  <LogOut />
                </Button>
              </Tooltip>
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>

        <footer className="border-t border-silver-50/[0.06] px-4 py-4 sm:px-6 lg:px-8">
          <p className="text-2xs text-silver-600">
            Dharma AI · multi-agent contract review ·{" "}
            {health?.lyzr.is_genuine_sdk
              ? `Lyzr ${health.lyzr.lyzr_version}`
              : "Lyzr compatibility layer"}{" "}
            · {health?.demo_mode ? "demo mode" : `live · ${health?.model ?? "—"}`}
          </p>
        </footer>
      </div>
    </div>
  );
}

function SidebarContent({
  sections,
  pathname,
  collapsed,
  openReviews,
  hideLogo = false,
}: {
  sections: { title: string; items: NavItem[] }[];
  pathname: string;
  collapsed: boolean;
  openReviews: number;
  hideLogo?: boolean;
}) {
  return (
    <>
      {!hideLogo && (
        <div className={cn("px-4 pb-2 pt-5", collapsed && "px-3")}>
          <Logo compact={collapsed} />
        </div>
      )}
      <nav className="flex-1 overflow-y-auto px-3 py-4 hide-scrollbar">
        {sections.map((section) => (
          <div key={section.title} className="mb-6">
            {!collapsed && (
              <p className="mb-2 px-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-silver-600">
                {section.title}
              </p>
            )}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                const count = item.badge === "reviews" ? openReviews : 0;

                const link = (
                  <Link
                    href={item.href}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-all duration-200",
                      active
                        ? "bg-accent/[0.10] font-medium text-accent-soft"
                        : "text-silver-400 hover:bg-base-800/60 hover:text-silver-100",
                      collapsed && "justify-center px-0",
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-accent"
                        transition={{ type: "spring", stiffness: 380, damping: 32 }}
                      />
                    )}
                    <Icon className="size-4 shrink-0" />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                    {!collapsed && count > 0 && (
                      <Badge variant="high" size="sm" className="ml-auto">
                        {count}
                      </Badge>
                    )}
                    {collapsed && count > 0 && (
                      <span className="absolute right-2 top-1.5 size-1.5 rounded-full bg-risk-high" />
                    )}
                  </Link>
                );

                return (
                  <li key={item.href}>
                    {collapsed ? <Tooltip content={item.label}>{link}</Tooltip> : link}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5" aria-label="Dharma AI home">
      <span className="relative grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-accent to-accent/50 shadow-glow-sm">
        <Sparkles className="size-4 text-accent-fg" strokeWidth={2.5} />
      </span>
      {!compact && (
        <span className="text-base font-semibold tracking-tight text-silver-50">
          Dharma<span className="text-accent"> AI</span>
        </span>
      )}
    </Link>
  );
}

function SystemStatus({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return (
      <Tooltip content="Backend unreachable — start it with `docker compose up`">
        <span className="flex items-center gap-1.5 rounded-full border border-risk-critical/30 bg-risk-critical/10 px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider text-risk-critical">
          <span className="size-1.5 rounded-full bg-risk-critical" />
          Offline
        </span>
      </Tooltip>
    );
  }

  const tooltip = (
    <span className="block space-y-0.5 text-left">
      <span className="block">
        Lyzr: {health.lyzr.lyzr_runtime}
        {health.lyzr.lyzr_version ? ` v${health.lyzr.lyzr_version}` : ""}
      </span>
      <span className="block">DB: {health.database.backend}</span>
      <span className="block">Vectors: {health.vector_store.backend}</span>
      <span className="block">
        {health.demo_mode ? "Demo mode (no OpenAI calls)" : `Live · ${health.model}`}
      </span>
    </span>
  );

  return (
    <Tooltip content={tooltip}>
      <span
        className={cn(
          "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-semibold uppercase tracking-wider",
          health.demo_mode
            ? "border-risk-medium/30 bg-risk-medium/10 text-risk-medium"
            : "border-accent/30 bg-accent/10 text-accent-soft",
        )}
      >
        {health.demo_mode ? <Gauge className="size-3" /> : <PulseDot />}
        {health.demo_mode ? "Demo" : "Live"}
      </span>
    </Tooltip>
  );
}
