import {
  createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode,
} from "react";

/* A menu: a button and what it holds, opened under it (``up``: above; ``right``: aligned to its right edge).
   Composed of Menu.Item (a choice; ``checked`` makes it a tick box), Menu.Sep, Menu.Label and Menu.Block (any
   content: a slider, a form). A click outside or Escape closes it; a choice closes it. Uses the old page's classes. */

const CloseContext = createContext<() => void>(() => {});

interface MenuProps {
  label: ReactNode;
  children: ReactNode | (() => ReactNode);
  title?: string;
  className?: string;
  buttonClassName?: string;
  right?: boolean;
  up?: boolean;
}

export function Menu({ label, children, title, className = "", buttonClassName = "", right, up }: MenuProps) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const outside = (ev: MouseEvent) => { if (!box.current?.contains(ev.target as Node)) setOpen(false); };
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") setOpen(false); };
    document.addEventListener("click", outside);
    document.addEventListener("keydown", esc);
    pop.current?.querySelector<HTMLElement>("button, input")?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("click", outside);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <span ref={box} className={`menu${right ? " right" : ""}${up ? " up" : ""} ${className}`.trim()}>
      <button
        type="button"
        className={`menu-btn ${buttonClassName}`.trim()}
        title={title}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>
      <div ref={pop} id={id} className="menu-pop" role="menu" hidden={!open}>
        <CloseContext.Provider value={close}>
          {open && (typeof children === "function" ? children() : children)}
        </CloseContext.Provider>
      </div>
    </span>
  );
}

interface ItemProps {
  children: ReactNode;
  onSelect?: () => void;
  checked?: boolean;
  hint?: ReactNode;
  disabled?: boolean;
}

function Item({ children, onSelect, checked, hint, disabled }: ItemProps) {
  const close = useContext(CloseContext);
  const tick = checked !== undefined;
  return (
    <button
      type="button"
      className="menu-item"
      role={tick ? "menuitemcheckbox" : "menuitem"}
      aria-checked={tick ? checked : undefined}
      disabled={disabled}
      onClick={() => { close(); onSelect?.(); }}
    >
      {tick && <span className="tick">{checked ? "✓" : ""}</span>}
      {children}
      {hint && <span className="hint">{hint}</span>}
    </button>
  );
}

Menu.Item = Item;
Menu.Sep = () => <div className="menu-sep" />;
Menu.Label = ({ children }: { children: ReactNode }) => <div className="menu-label">{children}</div>;
Menu.Block = ({ children }: { children: ReactNode }) => <div className="menu-block">{children}</div>;
/** The menu's close, for a Block's own controls. */
export const useMenuClose = () => useContext(CloseContext);
