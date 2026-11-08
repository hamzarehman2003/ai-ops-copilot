"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { ACTIONS_CHANGED, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CommandMenu } from "./CommandMenu";
import { Icon } from "./icons";
import { findPage, isActive, NAV } from "./navigation";
import { SystemInfo } from "./SystemInfo";
import { ThemeToggle } from "./ThemeToggle";
import { useUser } from "./UserProvider";
import { ErrorBanner } from "./ui";

/** Pending approvals for the nav badge; refreshed on navigation and after every decision. */
function usePendingCount(pathname: string) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .actions("pending")
        .then((a) => !cancelled && setCount(a.length))
        .catch(() => !cancelled && setCount(null));
    void load();
    window.addEventListener(ACTIONS_CHANGED, load);
    return () => {
      cancelled = true;
      window.removeEventListener(ACTIONS_CHANGED, load);
    };
  }, [pathname]);
  return count;
}

/** The frame every page lives in: the sidebar sits on the canvas, each page in a raised inset
 *  panel (rounded, hairline border) with a thin sticky header on top. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <SidebarProvider>
      <AppSidebar pathname={pathname} />
      <SidebarInset className="page-glow min-w-0 md:border md:border-sidebar-border md:shadow-card">
        <Header pathname={pathname} />
        {/* SidebarInset is already the <main> landmark. */}
        <div className="mx-auto w-full max-w-[1200px] flex-1 px-4 pt-8 pb-16 duration-300 animate-in fade-in slide-in-from-bottom-1 sm:px-6 lg:px-10 lg:pt-10">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

function AppSidebar({ pathname }: { pathname: string }) {
  const pending = usePendingCount(pathname);
  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader className="h-14 justify-center px-3 group-data-[collapsible=icon]:px-1">
        <Link href="/" aria-label="Ops Copilot home" className="flex items-center gap-2.5">
          <Logo />
          <span className="text-[15px] font-semibold tracking-[-0.02em] group-data-[collapsible=icon]:hidden">
            Ops Copilot
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent className="pt-1">
        {NAV.map((group) => (
          <SidebarGroup key={group.group}>
            <SidebarGroupLabel className="h-7 px-2 text-caption font-medium text-sidebar-foreground/50">
              {group.group}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu className="gap-0.5">
                {group.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        asChild
                        isActive={active}
                        tooltip={item.label}
                        className="h-8 rounded-md text-body text-sidebar-foreground/70 hover:text-sidebar-foreground data-[active=true]:bg-background data-[active=true]:font-medium data-[active=true]:text-sidebar-foreground data-[active=true]:shadow-[0_0_0_1px_var(--sidebar-border),0_1px_2px_rgb(var(--shadow-color)/0.06)]"
                      >
                        <Link href={item.href}>
                          <Icon
                            name={item.icon}
                            className={cn("opacity-80", active && "text-primary opacity-100")}
                          />
                          <span>{item.label}</span>
                        </Link>
                      </SidebarMenuButton>
                      {item.href === "/actions" && pending ? (
                        <SidebarMenuBadge className="numeric rounded-full bg-primary/12 px-1.5 text-micro font-medium text-primary peer-data-[active=true]/menu-button:text-primary">
                          {pending}
                        </SidebarMenuBadge>
                      ) : null}
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <UserMenu />
        <div className="flex items-center justify-between gap-2 group-data-[collapsible=icon]:flex-col">
          <ApiStatus />
          <ThemeToggle />
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="size-7 shrink-0 drop-shadow-sm" aria-hidden>
      <defs>
        <linearGradient id="logo-fill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7c7cf2" />
          <stop offset="1" stopColor="#4a3fb8" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-fill)" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="7.5" fill="none" stroke="#fff" strokeOpacity="0.18" />
      <circle cx="13" cy="16" r="6.5" fill="none" stroke="#fff" strokeWidth="2.4" />
      <circle cx="21.5" cy="16" r="3" fill="#fff" />
    </svg>
  );
}

function initials(name: string) {
  return name
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Who is signed in; the menu switches between users (the stand-in for real sign-in). */
function UserMenu() {
  const { email, users, me, setEmail } = useUser();
  const name = me?.user.name ?? email;
  const workspaces = Array.from(new Set(users.map((u) => u.workspace_name)));

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              tooltip={name}
              data-testid="user-switcher"
              aria-label="Signed in as"
              className="data-[state=open]:bg-sidebar-accent"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary/25 to-plum/25 text-xs font-semibold text-primary ring-1 ring-primary/20">
                {initials(name)}
              </span>
              <span className="grid min-w-0 flex-1 text-left leading-tight">
                <span className="truncate text-sm font-medium">{name}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {me ? `${capitalize(me.user.role)} · ${me.workspace.name}` : email}
                </span>
              </span>
              <Icon name="chevronsUpDown" className="ml-auto text-muted-foreground" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            side="top"
            align="start"
            className="w-(--radix-dropdown-menu-trigger-width) min-w-60"
          >
            <DropdownMenuRadioGroup value={email} onValueChange={setEmail}>
              {workspaces.map((ws, i) => (
                <div key={ws}>
                  {i > 0 && <DropdownMenuSeparator />}
                  <DropdownMenuLabel className="eyebrow text-micro">{ws}</DropdownMenuLabel>
                  {users
                    .filter((u) => u.workspace_name === ws)
                    .map((u) => (
                      <DropdownMenuRadioItem key={u.email} value={u.email}>
                        <span className="flex-1">{u.name}</span>
                        <span className="text-xs text-muted-foreground">{capitalize(u.role)}</span>
                      </DropdownMenuRadioItem>
                    ))}
                </div>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

/** Live dot: green while the API answers. */
function ApiStatus() {
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    const check = () =>
      api
        .meta()
        .then(() => !cancelled && setOk(true))
        .catch(() => !cancelled && setOk(false));
    void check();
    const t = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);
  const label = ok === null ? "Checking…" : ok ? "All systems running" : "API unreachable";
  return (
    <span
      className="flex min-w-0 items-center gap-2 px-2 text-xs text-muted-foreground"
      title={label}
    >
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          ok === null && "bg-muted-foreground/40",
          ok === true &&
            "bg-success shadow-[0_0_0_3px_color-mix(in_srgb,var(--success)_18%,transparent)]",
          ok === false && "bg-destructive",
        )}
      />
      <span className="truncate group-data-[collapsible=icon]:hidden">{label}</span>
    </span>
  );
}

function Header({ pathname }: { pathname: string }) {
  const { meError } = useUser();
  const { item, group } = findPage(pathname);

  return (
    <header className="sticky top-0 z-10 flex h-13 shrink-0 items-center gap-3 border-b border-border/70 bg-background/75 px-4 backdrop-blur-md md:rounded-t-xl md:px-5">
      <SidebarTrigger className="-ml-1.5 text-muted-foreground" />
      {meError ? (
        <ErrorBanner error={meError} />
      ) : (
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
          <span className="text-muted-foreground">{group ?? "Ops Copilot"}</span>
          <Icon name="chevronRight" className="size-3.5 text-muted-foreground/50" />
          <span className="truncate font-medium">{item?.label}</span>
        </nav>
      )}
      <div className="ml-auto flex items-center gap-2">
        <SystemInfo />
        <CommandMenu />
      </div>
    </header>
  );
}
