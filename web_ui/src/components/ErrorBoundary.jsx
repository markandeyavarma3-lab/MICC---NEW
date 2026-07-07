import { Component } from "react";

// Class component: React error boundaries have no hook equivalent. Without this,
// any uncaught render error anywhere (a null field, an unexpected API shape)
// unmounts the WHOLE app to a blank screen -- sidebar included. Layout mounts one
// of these around <Outlet/>, keyed by route, so a crash is contained to the
// current page and clears automatically on navigation.
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("MICC page crashed:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="flex h-64 flex-col items-center justify-center gap-3 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full border border-red-500/30 bg-red-500/10 text-red-300">
            !
          </div>
          <div className="text-sm text-slate-300">This page hit an unexpected error.</div>
          <div className="max-w-xs text-[12px] text-slate-500">
            {String(this.state.error?.message || this.state.error)}
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-[12px] text-slate-300 transition-colors hover:bg-white/5"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
