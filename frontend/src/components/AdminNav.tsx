import { UploadCloud, Users, QrCode, Settings, PowerOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type AdminSection = "principal" | "socios" | "cortes" | "gestores" | "config";

type AdminNavItem = {
  key: AdminSection;
  label: string;
  shortLabel?: string;
  Icon: LucideIcon;
};

const ITEMS: AdminNavItem[] = [
  { key: "principal", label: "Principal", Icon: UploadCloud },
  { key: "socios", label: "Socios", Icon: Users },
  { key: "cortes", label: "Cortes", Icon: PowerOff },
  { key: "gestores", label: "Gestores", Icon: QrCode },
  { key: "config", label: "Configuración", shortLabel: "Ajustes", Icon: Settings },
];

type AdminNavProps = {
  active: AdminSection;
  onChange: (section: AdminSection) => void;
  variant: "sidebar" | "tabs";
};

export default function AdminNav({ active, onChange, variant }: AdminNavProps) {
  if (variant === "tabs") {
    return (
      <nav className="admin-nav-tabs" aria-label="Secciones del panel">
        {ITEMS.map(({ key, label, shortLabel, Icon }) => (
          <button
            key={key}
            type="button"
            aria-label={label}
            className={`admin-nav-tab${active === key ? " is-active" : ""}`}
            onClick={() => onChange(key)}
            aria-current={active === key}
          >
            <Icon size={20} strokeWidth={2} aria-hidden="true" />
            <span>{shortLabel ?? label}</span>
          </button>
        ))}
      </nav>
    );
  }

  return (
    <nav className="admin-nav-list" aria-label="Secciones del panel">
      {ITEMS.map(({ key, label, Icon }) => (
        <button
          key={key}
          type="button"
          className={`admin-nav-link${active === key ? " is-active" : ""}`}
          onClick={() => onChange(key)}
          aria-current={active === key}
        >
          <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
