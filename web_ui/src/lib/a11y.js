import { useEffect, useRef } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

/** Traps Tab/Shift+Tab focus within containerRef while active, focuses the
 * first focusable element on activation, and restores focus to whatever had
 * it beforehand once deactivated -- for the command palette and both drawers,
 * none of which trapped focus before (Tab could leak into the page behind them). */
export function useFocusTrap(containerRef, active) {
  const prevFocus = useRef(null);

  useEffect(() => {
    if (!active) return;
    prevFocus.current = document.activeElement;
    const container = containerRef.current;
    const focusables = () => Array.from(container?.querySelectorAll(FOCUSABLE) || []);
    const first = focusables()[0];
    first?.focus();

    const onKey = (e) => {
      if (e.key !== "Tab" || !container) return;
      const els = focusables();
      if (!els.length) return;
      const firstEl = els[0], lastEl = els[els.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prevFocus.current?.focus?.();
    };
  }, [active, containerRef]);
}
