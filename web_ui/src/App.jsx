import { HashRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Ideas from "./pages/Ideas";
import Risk from "./pages/Risk";
import Research from "./pages/Research";
import Funds from "./pages/Funds";
import Events from "./pages/Events";

// HashRouter so the Python static server needs no SPA-fallback routing.
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/ideas" element={<Ideas />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/research" element={<Research />} />
          <Route path="/funds" element={<Funds />} />
          <Route path="/events" element={<Events />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
