import { NavLink, Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";

const NAV = [
  { to: "/", label: "Overview", icon: "◈" },
  { to: "/ideas", label: "Idea Cards", icon: "▤" },
  { to: "/risk", label: "Risk", icon: "⛨" },
  { to: "/research", label: "Research & Verdicts", icon: "⚖" },
  { to: "/funds", label: "Funds", icon: "◉" },
  { to: "/events", label: "Events & Smart Money", icon: "⚡" },
];

export default function Layout() {
  const loc = useLocation();
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-white/[0.06] bg-navy-900/60 backdrop-blur-xl">
        <div className="px-6 pb-6 pt-7">
          <div className="text-xl font-bold tracking-tight">
            <span className="bg-gradient-to-r from-cyan-300 to-emerald-300 bg-clip-text text-transparent">MICC</span>
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-slate-500">Quant Idea Desk</div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] transition-colors
                 ${isActive ? "text-white" : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.03]"}`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.span
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-xl border border-cyan-500/25 bg-gradient-to-r from-cyan-500/15 to-emerald-500/10"
                      transition={{ type: "spring", stiffness: 400, damping: 32 }}
                    />
                  )}
                  <span className="relative text-base opacity-80">{n.icon}</span>
                  <span className="relative">{n.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="px-6 py-5 text-[10px] leading-relaxed text-slate-600">
          research only · not advice<br />
          survivorship-free · PIT-correct
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          <motion.div
            key={loc.pathname}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="mx-auto max-w-[1240px] px-8 py-8"
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
