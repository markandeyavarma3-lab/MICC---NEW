// Shared animation presets. Previously each component picked its own duration/
// easing ad hoc (0.22s here, 0.3s there, 0.8s elsewhere) — consolidated here so
// the whole app moves with one consistent, deliberately-tuned physics feel.

export const EASE_OUT = [0.16, 1, 0.3, 1]; // "expo-out" — confident settle, no bounce
export const EASE_SOFT = [0.22, 1, 0.36, 1];

export const springPill = { type: "spring", stiffness: 420, damping: 34, mass: 0.9 };
export const springDrawer = { type: "spring", stiffness: 340, damping: 36, mass: 1 };

export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.32, ease: EASE_OUT },
};

/** staggered entrance for grids/lists — pass index i */
export const stagger = (i, { delay = 0.035, cap = 0.4, y = 10 } = {}) => ({
  initial: { opacity: 0, y },
  animate: { opacity: 1, y: 0 },
  transition: { delay: Math.min(i * delay, cap), duration: 0.4, ease: EASE_OUT },
});

export const fadeIn = (delay = 0) => ({
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  transition: { duration: 0.35, delay, ease: EASE_SOFT },
});
