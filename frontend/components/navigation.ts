import type { IconName } from "./icons";

export type NavItem = { href: string; label: string; icon: IconName; hint: string };

/** Every page, grouped as in the sidebar. The command menu and breadcrumb read this too. */
export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Workspace",
    items: [
      { href: "/", label: "Overview", icon: "overview", hint: "Key numbers and recent activity" },
      { href: "/copilot", label: "Copilot", icon: "chat", hint: "Ask with customer context" },
    ],
  },
  {
    group: "Knowledge",
    items: [
      { href: "/sources", label: "Sources", icon: "files", hint: "Upload, reindex, deprecate" },
      { href: "/search", label: "Search lab", icon: "search", hint: "Compare retrieval modes" },
    ],
  },
  {
    group: "Governance",
    items: [
      { href: "/actions", label: "Approvals", icon: "approve", hint: "Review proposed changes" },
      { href: "/audit", label: "Audit log", icon: "list", hint: "Every event, newest first" },
      { href: "/evals", label: "Evaluations", icon: "chart", hint: "Latest evaluation run" },
    ],
  },
];

export const ALL_ITEMS = NAV.flatMap((g) => g.items);

export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function findPage(pathname: string) {
  const item = ALL_ITEMS.find((i) => isActive(pathname, i.href));
  const group = NAV.find((g) => g.items.includes(item as NavItem));
  return { item, group: group?.group };
}
