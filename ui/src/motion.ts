import type { Transition, Variants } from "framer-motion";

/* Transition presets. Springs rather than tweens for anything that moves in
   space, per the motion guidance; short tweens for pure opacity/colour.
   Motion dial was set to 4/10 -- standard, not choreographed. Nothing here
   animates width/height directly; collapse uses a height:auto layout
   transition, which Framer Motion resolves to a transform-friendly path. */

export const spring: Transition = { type: "spring", stiffness: 320, damping: 26 };
export const springSoft: Transition = { type: "spring", stiffness: 240, damping: 28 };
export const springStiff: Transition = { type: "spring", stiffness: 520, damping: 32 };
export const snappy: Transition = { type: "tween", duration: 0.16, ease: [0.25, 0.1, 0.25, 1] };
export const smooth: Transition = { type: "tween", duration: 0.24, ease: "easeOut" };

/** Exit is faster than enter -- leaving should not hold the reviewer up. */
export const exitFast: Transition = { type: "tween", duration: 0.13, ease: "easeIn" };

export const listContainer: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.035, delayChildren: 0.04 } },
};

export const listItem: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: spring },
  exit: { opacity: 0, y: -6, transition: exitFast },
};

export const sectionIn: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: smooth },
};

/** Collapse/expand for evidence panels. */
export const collapse: Variants = {
  closed: { height: 0, opacity: 0, transition: { height: springStiff, opacity: { duration: 0.1 } } },
  open: { height: "auto", opacity: 1, transition: { height: springSoft, opacity: { duration: 0.2, delay: 0.04 } } },
};

/** Strip motion, keep the state change. Used when the OS asks for less
    motion -- the interface must still work, it just stops moving. */
export function still<T extends Variants>(v: T, reduce: boolean): T {
  if (!reduce) return v;
  const flat: Variants = {};
  for (const [key, value] of Object.entries(v)) {
    const val = typeof value === "function" ? value : { ...(value as object) };
    const obj = val as Record<string, unknown>;
    delete obj.y;
    delete obj.x;
    delete obj.scale;
    obj.transition = { duration: 0 };
    if (key === "closed") obj.height = 0;
    if (key === "open") obj.height = "auto";
    flat[key] = obj as never;
  }
  return flat as T;
}
