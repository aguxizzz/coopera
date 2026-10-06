import { UploadCloud, Users, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type AdminSection = "principal" | "socios" | "config";

type AdminNavItem = {
  key: AdminSection;
  label: string;
  Icon: LucideIcon;
};

const ITEMS: AdminNavItem[] = [
  { key: "principal", label: "Principal", Icon: UploadCloud },
  { key: "socios", label: "Socios", Icon: Users },
  { key: "config", label: "Configuración", Icon: Settings },
];

type AdminNavProps = {
  variant: "sidebar" | "tabs";
  active: AdminSection;
  onChange: (section: AdminSection) => void;
};

export default function AdminNav({ variant, active, onChange }: AdminNavProps) {
  return (
    <>
      {variant === "sidebar" && (
      <nav className="admin-nav-sidebar" aria-label="Secciones del panel">
        {ITEMS.map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            className={`admin-nav-item${active === key ? " is-active" : ""}`}
            onClick={() => onChange(key)}
            aria-current={active === key}
          >
            <span className="admin-nav-icon">
              <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
            </span>
            <span className="admin-nav-label">{label}</span>
          </button>
        ))}
      </nav>
      )}

      {variant === "tabs" && (
      <nav className="admin-nav-pill" aria-label="Secciones del panel">
        {ITEMS.map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            className={`admin-nav-pill-item${active === key ? " is-active" : ""}`}
            onClick={() => onChange(key)}
            aria-current={active === key}
          >
            <span className="admin-nav-icon">
              <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
            </span>
            <span className="admin-nav-pill-label">{label}</span>
          </button>
        ))}
      </nav>
      )}
    </>
  );
}
