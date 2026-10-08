import { useEffect, useState, type ReactNode } from "react";

type DrawerProps = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
};

const EXIT_DURATION_MS = 260;

export default function Drawer({ open, onClose, title, children }: DrawerProps) {
  const [rendered, setRendered] = useState(open);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (open) {
      setRendered(true);
      const raf = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(raf);
    }
    setVisible(false);
    const timeout = window.setTimeout(() => setRendered(false), EXIT_DURATION_MS);
    return () => window.clearTimeout(timeout);
  }, [open]);

  useEffect(() => {
    if (!rendered) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [rendered, onClose]);

  if (!rendered) return null;

  return (
    <div className={`drawer-overlay${visible ? " is-visible" : ""}`} onClick={onClose}>
      <div
        className={`drawer-panel${visible ? " is-visible" : ""}`}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-head">
          {typeof title === "string" ? <h2>{title}</h2> : title}
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>
  );
}
