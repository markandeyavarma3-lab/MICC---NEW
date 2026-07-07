import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { m, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";
import { useSymbol } from "../lib/symbolContext";
import { EASE_OUT } from "../lib/motion";
import { useFocusTrap } from "../lib/a11y";

const PAGES = [
  { to: "/", label: "Overview", icon: "◈" },
  { to: "/ideas", label: "Idea Cards", icon: "▤" },
  { to: "/portfolio", label: "Portfolio", icon: "◆" },
  { to: "/risk", label: "Risk", icon: "⛨" },
  { to: "/research", label: "Research & Verdicts", icon: "⚖" },
  { to: "/funds", label: "Funds", icon: "◉" },
  { to: "/events", label: "Events & Smart Money", icon: "⚡" },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [symbols, setSymbols] = useState([]); // [{symbol, company, confidence_score}]
  const inputRef = useRef(null);
  const panelRef = useRef(null);
  const navigate = useNavigate();
  const { open: openSymbol } = useSymbol();
  useFocusTrap(panelRef, open);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    const onEvent = () => setOpen((o) => !o);
    window.addEventListener("keydown", onKey);
    window.addEventListener("micc:toggle-palette", onEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("micc:toggle-palette", onEvent);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      setQ(""); setSel(0);
      // focus is handled by useFocusTrap (input is the first focusable element)
      api("/api/ideas").then((d) => setSymbols(d?.cards || [])).catch(() => {});
    }
  }, [open]);

  const pageResults = useMemo(() => {
    if (!q) return PAGES;
    const n = q.toLowerCase();
    return PAGES.filter((p) => p.label.toLowerCase().includes(n));
  }, [q]);

  const symbolResults = useMemo(() => {
    if (!q) return [];
    const n = q.toLowerCase();
    return symbols.filter((s) => s.symbol.toLowerCase().includes(n) || s.company?.toLowerCase().includes(n)).slice(0, 6);
  }, [q, symbols]);

  const items = useMemo(() => [
    ...pageResults.map((p) => ({ type: "page", ...p })),
    ...symbolResults.map((s) => ({ type: "symbol", ...s })),
  ], [pageResults, symbolResults]);

  useEffect(() => { setSel(0); }, [q]);

  const activate = (item) => {
    if (!item) return;
    if (item.type === "page") navigate(item.to);
    else openSymbol(item.symbol);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); activate(items[sel]); }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <m.div
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }} onClick={() => setOpen(false)}
          />
          <m.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            className="fixed left-1/2 top-[18%] z-50 w-full max-w-[540px] -translate-x-1/2"
            initial={{ opacity: 0, y: -12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }} transition={{ duration: 0.22, ease: EASE_OUT }}
          >
            <div className="glass overflow-hidden">
              <div className="flex items-center gap-3 border-b border-white/[0.06] px-4 py-3">
                <span aria-hidden="true" className="text-slate-500">⌘K</span>
                <input
                  ref={inputRef}
                  role="combobox"
                  aria-expanded="true"
                  aria-controls="palette-listbox"
                  aria-activedescendant={items[sel] ? `palette-opt-${sel}` : undefined}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder="Jump to a page or search a symbol…"
                  className="w-full bg-transparent text-[14px] text-slate-100 outline-none placeholder:text-slate-500"
                />
                <kbd className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-500">esc</kbd>
              </div>
              <div id="palette-listbox" role="listbox" className="max-h-[360px] overflow-y-auto p-2">
                {items.length === 0 && (
                  <div className="px-3 py-6 text-center text-[13px] text-slate-500">no matches</div>
                )}
                {pageResults.length > 0 && (
                  <div className="label px-3 pb-1 pt-2">Pages</div>
                )}
                {pageResults.map((p) => {
                  const i = items.indexOf(items.find((it) => it.type === "page" && it.to === p.to));
                  return (
                    <Row key={p.to} id={`palette-opt-${i}`} active={i === sel} icon={p.icon} label={p.label}
                         onClick={() => activate(items[i])} onMouseEnter={() => setSel(i)} />
                  );
                })}
                {symbolResults.length > 0 && (
                  <div className="label px-3 pb-1 pt-3">Idea cards</div>
                )}
                {symbolResults.map((s) => {
                  const i = items.indexOf(items.find((it) => it.type === "symbol" && it.symbol === s.symbol));
                  return (
                    <Row key={s.symbol} id={`palette-opt-${i}`} active={i === sel} icon="●" label={s.symbol}
                         sub={s.company} right={`conf ${s.confidence_score.toFixed(0)}`}
                         onClick={() => activate(items[i])} onMouseEnter={() => setSel(i)} />
                  );
                })}
              </div>
            </div>
          </m.div>
        </>
      )}
    </AnimatePresence>
  );
}

function Row({ id, active, icon, label, sub, right, onClick, onMouseEnter }) {
  return (
    <div
      id={id}
      role="option"
      aria-selected={active}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors
                  ${active ? "bg-cyan-500/10 text-white" : "text-slate-300"}`}
    >
      <span aria-hidden="true" className="w-4 text-center opacity-70">{icon}</span>
      <span className="flex-1 truncate">{label}{sub && <span className="ml-2 text-[11px] text-slate-500">{sub}</span>}</span>
      {right && <span className="num text-[11px] text-slate-500">{right}</span>}
    </div>
  );
}
