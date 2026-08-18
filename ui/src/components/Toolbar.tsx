import { motion, useReducedMotion } from "framer-motion";
import { Search } from "../icons";
import { spring } from "../motion";

export interface PillOption { value: string; label: string; count?: number }

/** A segmented filter. The active background is a single shared element moved
    between options with layoutId, so the selection slides rather than
    blinking -- the spatial continuity rule from the UX set. */
export function PillGroup({
  options, value, onChange, groupId, label,
}: {
  options: PillOption[];
  value: string;
  onChange: (v: string) => void;
  groupId: string;
  label: string;
}) {
  const reduce = useReducedMotion() ?? false;
  return (
    <div className="filter-group" role="group" aria-label={label}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            className="pill"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
          >
            {on &&
              (reduce ? (
                <span className="pill-bg" />
              ) : (
                <motion.span className="pill-bg" layoutId={`${groupId}-bg`} transition={spring} />
              ))}
            <span>
              {o.label}
              {o.count !== undefined && <span className="n">{o.count}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function SearchBox({
  value, onChange, inputRef,
}: {
  value: string;
  onChange: (v: string) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="search">
      <Search />
      <input
        ref={inputRef}
        type="search"
        value={value}
        placeholder="Search findings, rules, quoted text…"
        aria-label="Search findings"
        onChange={(e) => onChange(e.target.value)}
      />
      {!value && <kbd>/</kbd>}
    </div>
  );
}
