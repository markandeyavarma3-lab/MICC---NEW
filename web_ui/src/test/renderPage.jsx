import { render } from "@testing-library/react";
import { LazyMotion, domMax } from "framer-motion";
import { SymbolProvider } from "../lib/symbolContext";

// Shared wrapper for page smoke tests: every page tree sits under LazyMotion
// (m.* components need it) and SymbolProvider (Events/CommandPalette/SymbolDrawer
// share this context) in the real app, via App.jsx -- mirror that here.
export function renderPage(ui) {
  return render(
    <LazyMotion features={domMax}>
      <SymbolProvider>{ui}</SymbolProvider>
    </LazyMotion>
  );
}
