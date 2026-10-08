import { Home, Users, QrCode, Settings, PowerOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type AdminSection = "principal" | "socios" | "cortes" | "gestores" | "config";

type AdminNavItem = {
  key: AdminSection;
  label: string;
  Icon: LucideIcon;
};

const ITEMS: AdminNavItem[] = [
  { key: "principal", label: "Principal", Icon: Home },
  { key: "socios", label: "Socios", Icon: Users },
  { key: "cortes", label: "Cortes", Icon: PowerOff },
  { key: "gestores", label: "Gestores", Icon: QrCode },
  { key: "config", label: "Configuración", Icon: Settings },
];

type AdminNavProps = {
  active: AdminSection;
  onChange: (section: AdminSection) => void;
  variant: "sidebar" | "tabs";
  badges?: Partial<Record<AdminSection, number>>;
};

export default function AdminNav({ active, onChange, variant, badges }: AdminNavProps) {
  if (variant === "tabs") {
    return (
      <nav className="admin-nav-tabs" aria-label="Secciones del panel">
        {ITEMS.map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            className={`admin-nav-tab${active === key ? " is-active" : ""}`}
            onClick={() => onChange(key)}
            aria-current={active === key}
          >
            <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
            <span>{label}</span>
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
          <span className="admin-nav-icon" aria-hidden="true">
            <Icon size={16} strokeWidth={1.8} />
          </span>
          <span className="admin-nav-label">{label}</span>
          {badges?.[key] != null && <span className="admin-nav-badge">{badges[key]}</span>}
        </button>
      ))}
    </nav>
  );
}
