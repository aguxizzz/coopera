import { useEffect, useState } from "react";

type ToastProps = {
  message: string | null;
  variant?: "success" | "error";
  onDismiss: () => void;
  duration?: number;
};

const EXIT_DURATION_MS = 180;

export default function Toast({ message, variant = "success", onDismiss, duration = 4000 }: ToastProps) {
  const [rendered, setRendered] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (message) {
      setRendered(true);
      const raf = requestAnimationFrame(() => setVisible(true));
      const timeout = window.setTimeout(onDismiss, duration);
      return () => {
        cancelAnimationFrame(raf);
        window.clearTimeout(timeout);
      };
    }
    setVisible(false);
    const timeout = window.setTimeout(() => setRendered(false), EXIT_DURATION_MS);
    return () => window.clearTimeout(timeout);
  }, [message, duration, onDismiss]);

  if (!rendered) return null;

  return (
    <div className={`toast toast-${variant}${visible ? " is-visible" : ""}`} role="status">
      {message}
    </div>
  );
}
