import type { ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Bell,
  Compass,
  Home as HomeIcon,
  LayoutDashboard,
  MessageSquare,
  PlusCircle,
  Settings as SettingsIcon,
  Shield,
  Sparkles,
  Swords,
  TrendingUp,
  UserRound,
} from "lucide-react";

import Avatar from "@/components/ui/Avatar";
import Button from "@/components/ui/Button";
import { useAuth } from "@/context/AuthContext";
import { useNotifications } from "@/hooks/useNotifications";
import { cn, titleCase } from "@/lib/utils";

const PRIMARY = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/feed", label: "Vibe Feed", icon: Sparkles },
  { to: "/battles", label: "Vibe Battles", icon: Swords },
  { to: "/learn", label: "LearnSpace", icon: TrendingUp },
  { to: "/explore", label: "Explore", icon: Compass },
  { to: "/create", label: "Create", icon: PlusCircle },
];

const SECONDARY = [
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/messages", label: "Messages", icon: MessageSquare },
  { to: "/creator", label: "CreatorSpace", icon: LayoutDashboard },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

const MOBILE = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/feed", label: "Feed", icon: Sparkles },
  { to: "/battles", label: "Battles", icon: Swords },
  { to: "/create", label: "Create", icon: PlusCircle },
  { to: "/messages", label: "Inbox", icon: MessageSquare },
];

export default function AppShell() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { unreadCount, messageCount } = useNotifications(Boolean(user));

  const isStaff = user?.role === "moderator" || user?.role === "admin";

  const profileLink = user ? `/u/${user.username}` : "/login";

  return (
    <div className="min-h-screen lg:flex">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-ink-800/70 bg-ink-950/80 px-4 py-6 backdrop-blur lg:flex">
        <button
          type="button"
          onClick={() => navigate("/")}
          className="mb-8 flex items-center gap-2 text-left font-display text-xl font-semibold tracking-tight"
        >
          <span className="grid h-9 w-9 place-items-center rounded-2xl bg-gradient-to-br from-violet to-coral text-sm font-bold text-white">
            VS
          </span>
          VibeSpace
        </button>

        <nav className="space-y-1">
          {PRIMARY.map((item) => (
            <SidebarLink key={item.to} {...item} />
          ))}
        </nav>

        <div className="my-6 h-px bg-ink-800/70" />

        <nav className="space-y-1">
          {SECONDARY.map((item) => (
            <SidebarLink
              key={item.to}
              {...item}
              badge={
                item.to === "/notifications" ? unreadCount : item.to === "/messages" ? messageCount : undefined
              }
            />
          ))}
          {isStaff ? <SidebarLink to="/admin" label="Admin" icon={Shield} /> : null}
        </nav>

        <div className="mt-auto pt-6">
          {user ? (
            <div className="flex items-center gap-3 rounded-2xl border border-ink-800/80 bg-ink-900/60 p-3">
              <Avatar src={user.avatar_url} name={user.display_name ?? user.username} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{user.display_name ?? user.username}</p>
                <p className="text-[11px] uppercase tracking-wide text-haze">{titleCase(user.role)}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => navigate(profileLink)}>
                <UserRound className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <Button className="w-full" onClick={() => navigate("/login")}>
              Sign in
            </Button>
          )}
        </div>
      </aside>

      {/* Mobile header */}
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-ink-800/70 bg-ink-950/90 px-4 py-3 backdrop-blur lg:hidden">
        <button type="button" onClick={() => navigate("/")} className="flex items-center gap-2 font-display font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-violet to-coral text-xs font-bold">
            VS
          </span>
          VibeSpace
        </button>
        <div className="flex items-center gap-2">
          <IconButton to="/notifications" badge={unreadCount} label="Notifications">
            <Bell className="h-5 w-5" />
          </IconButton>
          <IconButton to={profileLink} label="Profile">
            <Avatar src={user?.avatar_url} name={user?.display_name ?? user?.username} size="sm" />
          </IconButton>
        </div>
      </header>

      <main className="min-w-0 flex-1 px-4 pb-28 pt-6 sm:px-6 lg:px-10 lg:pb-16">
        <div className="mx-auto w-full max-w-5xl">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-ink-800/80 bg-ink-950/95 px-2 py-2 backdrop-blur lg:hidden">
        <ul className="flex items-center justify-between">
          {MOBILE.map((item) => (
            <li key={item.to} className="flex-1">
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex flex-col items-center gap-1 rounded-2xl px-2 py-2 text-[11px] transition",
                    isActive ? "bg-violet/15 text-violet-soft" : "text-haze",
                  )
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

function SidebarLink({
  to,
  label,
  icon: Icon,
  badge,
}: {
  to: string;
  label: string;
  icon: typeof HomeIcon;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition",
          isActive
            ? "bg-violet/15 text-white shadow-[inset_0_0_0_1px_hsl(var(--vibe-violet)/0.35)]"
            : "text-haze hover:bg-ink-850/80 hover:text-white",
        )
      }
    >
      <Icon className="h-4 w-4" />
      <span className="flex-1">{label}</span>
      {badge ? (
        <span className="rounded-full bg-coral/90 px-1.5 py-0.5 text-[10px] font-bold text-ink-950">
          {badge > 99 ? "99+" : badge}
        </span>
      ) : null}
    </NavLink>
  );
}

function IconButton({
  to,
  badge,
  label,
  children,
}: {
  to: string;
  badge?: number;
  label: string;
  children: ReactNode;
}) {
  return (
    <NavLink to={to} aria-label={label} className="relative grid h-9 w-9 place-items-center rounded-xl text-haze">
      {children}
      {badge ? (
        <span className="absolute -right-0.5 -top-0.5 rounded-full bg-coral px-1 text-[10px] font-bold text-ink-950">
          {badge > 9 ? "9+" : badge}
        </span>
      ) : null}
    </NavLink>
  );
}