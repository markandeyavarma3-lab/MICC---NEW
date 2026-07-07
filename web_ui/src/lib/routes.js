import { lazy } from "react";

// Single source of truth for route -> lazy-loaded page, so both App.jsx (which
// needs the lazy component) and Layout.jsx (which prefetches on nav hover, so
// a click feels instant instead of waiting on the chunk fetch) share one map.
const loaders = {
  "/": () => import("../pages/Overview"),
  "/ideas": () => import("../pages/Ideas"),
  "/portfolio": () => import("../pages/Portfolio"),
  "/risk": () => import("../pages/Risk"),
  "/research": () => import("../pages/Research"),
  "/funds": () => import("../pages/Funds"),
  "/events": () => import("../pages/Events"),
};

export const LazyPages = Object.fromEntries(
  Object.entries(loaders).map(([path, loader]) => [path, lazy(loader)])
);

export function prefetchRoute(path) {
  loaders[path]?.();
}
