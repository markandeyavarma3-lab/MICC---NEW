import { HashRouter, Routes, Route } from "react-router-dom";
import { LazyMotion, domMax } from "framer-motion";
import Layout from "./components/Layout";
import { SymbolProvider } from "./lib/symbolContext";
import { LazyPages } from "./lib/routes";

// Route-based code splitting: each page (and its charts) only downloads when
// actually visited, instead of one 770KB chunk shipped up front for a
// single-user tool that's usually only looking at one page at a time.
const { "/": Overview, "/ideas": Ideas, "/portfolio": Portfolio, "/risk": Risk,
        "/research": Research, "/funds": Funds, "/events": Events } = LazyPages;

// HashRouter so the Python static server needs no SPA-fallback routing.
export default function App() {
  return (
    // domMax (not the smaller domAnimation) because Layout's nav pill and
    // Risk's drawdown-band both use layoutId shared-layout animations.
    <LazyMotion features={domMax}>
      <SymbolProvider>
        <HashRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Overview />} />
              <Route path="/ideas" element={<Ideas />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/risk" element={<Risk />} />
              <Route path="/research" element={<Research />} />
              <Route path="/funds" element={<Funds />} />
              <Route path="/events" element={<Events />} />
            </Route>
          </Routes>
        </HashRouter>
      </SymbolProvider>
    </LazyMotion>
  );
}
