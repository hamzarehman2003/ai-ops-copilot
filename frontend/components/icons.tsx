// Icon set: lucide line icons behind short names, so call sites stay `<Icon name="..." />`.

import {
  Activity,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  ChartColumn,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  CornerDownLeft,
  FileText,
  Files,
  Inbox,
  Info,
  Layers,
  LayoutDashboard,
  MessagesSquare,
  Monitor,
  Moon,
  PanelLeft,
  Plus,
  RefreshCw,
  ScrollText,
  Search,
  Shield,
  ShieldCheck,
  Sun,
  ThumbsDown,
  ThumbsUp,
  TriangleAlert,
  Upload,
  User,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";

const icons = {
  overview: LayoutDashboard,
  chat: MessagesSquare,
  file: FileText,
  files: Files,
  search: Search,
  check: Check,
  approve: ShieldCheck,
  list: ScrollText,
  chart: ChartColumn,
  activity: Activity,
  arrowRight: ArrowRight,
  arrowUpRight: ArrowUpRight,
  refresh: RefreshCw,
  upload: Upload,
  close: X,
  send: ArrowUp,
  enter: CornerDownLeft,
  layers: Layers,
  shield: Shield,
  bolt: Zap,
  user: User,
  book: BookOpen,
  inbox: Inbox,
  chevronDown: ChevronDown,
  chevronRight: ChevronRight,
  chevronsUpDown: ChevronsUpDown,
  info: Info,
  alert: TriangleAlert,
  thumbUp: ThumbsUp,
  thumbDown: ThumbsDown,
  plus: Plus,
  panel: PanelLeft,
  sun: Sun,
  moon: Moon,
  monitor: Monitor,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof icons;

export function Icon({
  name,
  className = "h-4 w-4",
  strokeWidth = 1.75,
}: {
  name: IconName;
  className?: string;
  strokeWidth?: number;
}) {
  const Component = icons[name];
  return <Component className={className} strokeWidth={strokeWidth} aria-hidden />;
}
