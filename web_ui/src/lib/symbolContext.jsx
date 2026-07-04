import { createContext, useContext, useState } from "react";

// Shared "which symbol is open in the profile drawer" state, so any page
// (Events table, command palette, …) can trigger the same unified view.
const Ctx = createContext(null);

export function SymbolProvider({ children }) {
  const [symbol, setSymbol] = useState(null);
  return <Ctx.Provider value={{ symbol, open: setSymbol, close: () => setSymbol(null) }}>{children}</Ctx.Provider>;
}

export function useSymbol() {
  return useContext(Ctx);
}
