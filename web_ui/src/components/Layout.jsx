import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { springPill, pageTransition, EASE_OUT } from "../lib/motion";
import CommandPalette from "./CommandPalette";
import SymbolDrawer from "./SymbolDrawer";

const NAV = [
  { to: "/", label: "Overview", icon: "◈" },
  { to: "/ideas", label: "Idea Cards", icon: "▤" },
  { to: "/risk", label: "Risk", icon: "⛨" },
  { to: "/research", label: "Research & Verdicts", icon: "⚖" },
  { to: "/funds", label: "Funds", icon: "◉" },
  { to: "/events", label: "Events", icon: "⚡" },
];

const LS_KEY = "micc-sidebar-collapsed";

export default function Layout() {
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(LS_KEY) === "1");

  useEffect(() => { localStorage.setItem(LS_KEY, collapsed ? "1" : "0"); }, [collapsed]);

  // Ctrl/Cmd+B toggles, matching the convention from VS Code / Slack / Linear
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setCollapsed((c) => !c);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-full">
      <motion.aside
        animate={{ width: collapsed ? 0 : 208 }}
        transition={{ duration: 0.28, ease: EASE_OUT }}
        className="flex shrink-0 flex-col overflow-hidden border-r border-white/[0.06] bg-navy-900/60 backdrop-blur-xl"
        style={{ borderRightWidth: collapsed ? 0 : 1 }}
      >
        <div className="flex w-52 items-start justify-between px-5 pb-6 pt-7">
          <div>
            <div className="text-lg font-bold tracking-tight">
              <span className="bg-gradient-to-r from-cyan-300 to-emerald-300 bg-clip-text text-transparent">MICC</span>
            </div>
            <div className="label mt-1 tracking-[0.18em]">Quant Idea Desk</div>
          </div>
          <button
            onClick={() => setCollapsed(true)}
            title="Collapse sidebar (Ctrl+B)"
            className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-200"
          >
            <ChevronLeft />
          </button>
        </div>
        <div className="w-52 px-3 pb-3">
          <button
            onClick={() => window.dispatchEvent(new Event("micc:toggle-palette"))}
            className="flex w-full items-center gap-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2
                       text-[12px] text-slate-500 transition-colors hover:border-white/10 hover:bg-white/[0.04] hover:text-slate-300"
          >
            <SearchGlyph />
            <span className="flex-1 text-left">Search…</span>
            <kbd className="rounded border border-white/10 px-1 py-0.5 text-[10px]">⌘K</kbd>
          </button>
        </div>
        <nav className="w-52 flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `group relative block rounded-xl text-[13px] outline-none
                 focus-visible:ring-1 focus-visible:ring-cyan-400/50
                 ${isActive ? "text-white" : "text-slate-400 hover:text-slate-200"}`
              }
            >
              {({ isActive }) => (
                <motion.div
                  className="relative flex items-center gap-3 rounded-xl px-3 py-2.5"
                  whileHover={{ x: isActive ? 0 : 2 }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ duration: 0.15 }}
                >
                  {isActive ? (
                    <motion.span
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-xl border border-cyan-500/25 bg-gradient-to-r from-cyan-500/15 to-emerald-500/10"
                      transition={springPill}
                    />
                  ) : (
                    <span className="absolute inset-0 rounded-xl bg-white/[0.03] opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
                  )}
                  <span className="relative text-base opacity-80">{n.icon}</span>
                  <span className="relative whitespace-nowrap">{n.label}</span>
                </motion.div>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="w-52 px-5 py-5 text-[10px] leading-relaxed text-slate-600">
          research only · not advice<br />
          survivorship-free · PIT-correct
        </div>
      </motion.aside>

      {/* reveal handle — shown only while the sidebar is collapsed */}
      <AnimatePresence>
        {collapsed && (
          <motion.button
            initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
            onClick={() => setCollapsed(false)}
            title="Show sidebar (Ctrl+B)"
            className="fixed left-2 top-1/2 z-30 flex h-9 w-6 -translate-y-1/2 items-center justify-center
                       rounded-lg border border-white/10 bg-navy-900/80 text-slate-500 backdrop-blur-md
                       transition-colors hover:text-cyan-300"
          >
            <ChevronRight />
          </motion.button>
        )}
      </AnimatePresence>

      <main className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          <motion.div
            key={loc.pathname}
            {...pageTransition}
            className="mx-auto max-w-[1240px] px-8 py-8"
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      <CommandPalette />
      <SymbolDrawer />
    </div>
  );
}

function SearchGlyph() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function ChevronLeft() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18l6-6-6-6" />
    </svg>
  );
}
