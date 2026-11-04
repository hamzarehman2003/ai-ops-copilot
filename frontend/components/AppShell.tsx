"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { Icon, type IconName } from "./icons";
import { SystemInfo } from "./SystemInfo";
import { useUser } from "./UserProvider";
import { cx, ErrorBanner } from "./ui";

type NavItem = { href: string; label: string; icon: IconName };

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Workspace",
    items: [
      { href: "/", label: "Overview", icon: "overview" },
      { href: "/copilot", label: "Copilot", icon: "chat" },
    ],
  },
  {
    group: "Knowledge",
    items: [
      { href: "/sources", label: "Sources", icon: "file" },
      { href: "/search", label: "Search lab", icon: "search" },
    ],
  },
  {
    group: "Governance",
    items: [
      { href: "/actions", label: "Approvals", icon: "approve" },
      { href: "/audit", label: "Audit log", icon: "list" },
      { href: "/evals", label: "Evaluations", icon: "chart" },
    ],
  },
];

const ALL_ITEMS = NAV.flatMap((g) => g.items);

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/** Pending approvals for the nav badge; refreshed on navigation. */
function usePendingCount(pathname: string) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    api
      .actions("pending")
      .then((a) => !cancelled && setCount(a.length))
      .catch(() => !cancelled && setCount(null));
    return () => {
      cancelled = true;
    };
  }, [pathname]);
  return count;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const pending = usePendingCount(pathname);
  const { me } = useUser();

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-line bg-paper md:flex">
        <Link href="/" className="flex items-center gap-3 px-5 pt-6 pb-7">
          <BrandMark />
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-[-0.01em] text-ink">
              Ops Copilot
            </div>
            <div className="text-[12px] text-ink-3">{me?.workspace.name ?? "Support desk"}</div>
          </div>
        </Link>

        <nav className="flex flex-col gap-6 px-3" aria-label="Main">
          {NAV.map((group) => (
            <div key={group.group}>
              <div className="eyebrow mb-1.5 px-2.5 text-ink-4">{group.group}</div>
              <div className="flex flex-col gap-px">
                {group.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cx(
                        "group relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13.5px] transition-colors",
                        active
                          ? "bg-surface font-medium text-ink shadow-card ring-1 ring-line"
                          : "text-ink-2 hover:bg-paper-2 hover:text-ink",
                      )}
                    >
                      <Icon
                        name={item.icon}
                        className={cx(
                          "h-[17px] w-[17px]",
                          active ? "text-accent" : "text-ink-3 group-hover:text-ink-2",
                        )}
                      />
                      {item.label}
                      {item.href === "/actions" && pending ? (
                        <span className="ml-auto rounded-full bg-accent px-1.5 font-mono text-[10.5px] leading-[18px] font-medium text-white tabular-nums">
                          {pending}
                        </span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-auto px-5 pb-5">
          <div className="rounded-lg border border-line bg-surface/70 p-3 text-[11.5px] leading-relaxed text-ink-3">
            <span className="font-medium text-ink-2">Demo build.</span> Synthetic customers and
            documents. Writes only run after a human approves them.
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar pathname={pathname} />
        {/* Mobile nav */}
        <nav
          className="flex gap-1 overflow-x-auto border-b border-line bg-paper px-3 py-2 md:hidden"
          aria-label="Main mobile"
        >
          {ALL_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cx(
                "rounded-md px-2.5 py-1.5 text-[12.5px] font-medium whitespace-nowrap",
                isActive(pathname, item.href) ? "bg-surface text-ink ring-1 ring-line" : "text-ink-3",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <main className="mx-auto w-full max-w-[1320px] flex-1 px-4 pt-8 pb-16 sm:px-6 lg:px-10 lg:pt-10">
          {children}
        </main>
      </div>
    </div>
  );
}

function BrandMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--color-ink)" />
      <circle cx="13" cy="16" r="6.5" fill="none" stroke="var(--color-paper)" strokeWidth="2.4" />
      <circle cx="21.5" cy="16" r="3" fill="var(--color-accent)" />
    </svg>
  );
}

function TopBar({ pathname }: { pathname: string }) {
  const { email, users, me, meError, setEmail } = useUser();
  const current = ALL_ITEMS.find((i) => isActive(pathname, i.href));
  const initials = (me?.user.name ?? email)
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line bg-paper/85 px-4 backdrop-blur-md sm:px-6 lg:px-10">
      <div className="hidden min-w-0 items-center gap-2 text-[13px] sm:flex">
        {meError ? (
          <ErrorBanner error={meError} />
        ) : (
          <>
            <span className="truncate text-ink-3">{me?.workspace.name ?? "…"}</span>
            <Icon name="chevronRight" className="h-3.5 w-3.5 text-ink-4" />
            <span className="font-medium text-ink">{current?.label}</span>
          </>
        )}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <SystemInfo />
        <span className="mx-1 hidden h-5 w-px bg-line sm:block" aria-hidden />
        <label className="relative flex items-center gap-2 rounded-lg py-1 pr-1 pl-1 hover:bg-paper-2">
          <span
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-paper"
            aria-hidden
          >
            {initials}
          </span>
          <span className="sr-only">Signed in as</span>
          <select
            aria-label="Signed in as"
            data-testid="user-switcher"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="max-w-[11rem] cursor-pointer appearance-none bg-transparent pr-5 text-[13px] font-medium text-ink focus:outline-none sm:max-w-[16rem]"
          >
            {!users.some((u) => u.email === email) && <option value={email}>{email}</option>}
            {users.map((u) => (
              <option key={u.email} value={u.email}>
                {u.name} · {u.role} · {u.workspace}
              </option>
            ))}
          </select>
          <Icon
            name="chevronDown"
            className="pointer-events-none absolute right-1.5 h-3.5 w-3.5 text-ink-3"
          />
        </label>
      </div>
    </header>
  );
}
