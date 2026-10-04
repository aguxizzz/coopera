import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Search, X, Crown, UserCog, UserPlus, Trash2 } from "lucide-react";
import {
  ApiError,
  connectHelipagos,
  createAdmin,
  deleteAdmin,
  deleteLogo,
  deleteMember,
  deleteMembers,
  disconnectHelipagos,
  disconnectMp,
  getAdminSettings,
  getAuditLog,
  getCurrentAdmin,
  getHelipagosStatus,
  getMpConnectUrl,
  getMpStatus,
  importSpreadsheet,
  listAdmins,
  listMemberInvoices,
  listMembers,
  setInvoicePagado,
  updateAdminRole,
  updateAdminSettings,
  uploadLogo,
  type AdminRole,
  type AdminUserOut,
  type AuditLogEntry,
  type HelipagosStatus,
  type ImportResult,
  type InvoiceOut,
  type MemberRow,
  type MpStatus,
  type TenantSettings,
} from "../lib/api";
import Drawer from "../components/Drawer";
import ConfirmDialog from "../components/ConfirmDialog";
import FilePicker from "../components/FilePicker";
import LogoPlaceholder from "../components/LogoPlaceholder";
import AdminNav, { type AdminSection } from "../components/AdminNav";

const MESES = [
  "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function money(value: number) {
  return value.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
}

type ConfirmState = {
  message: string;
  onConfirm: () => void;
};

const ACCENT_SWATCHES = ["#1d6fa3", "#0f7a6a", "#2f5fe0", "#b4451f", "#5a3fa0"];

export default function AdminDashboard() {
  const { tenantSlug = "" } = useParams();
  const navigate = useNavigate();
  const token = sessionStorage.getItem(`coopera_token_${tenantSlug}`);

  function handleLogout() {
    sessionStorage.removeItem(`coopera_token_${tenantSlug}`);
    navigate(`/${tenantSlug}/admin`);
  }

  const [section, setSection] = useState<AdminSection>("principal");

  const [members, setMembers] = useState<MemberRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sociosQuery, setSociosQuery] = useState("");

  const [file, setFile] = useState<File | null>(null);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMember, setDrawerMember] = useState<MemberRow | null>(null);
  const [invoices, setInvoices] = useState<InvoiceOut[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);
  const [invoicesError, setInvoicesError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const [settings, setSettings] = useState<TenantSettings | null>(null);
  const [settingsForm, setSettingsForm] = useState({
    contact_email: "",
    contact_phone: "",
    contact_whatsapp: "",
    contact_address: "",
    primary_color: "#2563eb",
  });
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [logoUploading, setLogoUploading] = useState<"primary" | "secondary" | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const [mpStatus, setMpStatus] = useState<MpStatus | null>(null);
  const [mpLoading, setMpLoading] = useState(false);
  const [mpError, setMpError] = useState<string | null>(null);
  const mpResult = searchParams.get("mp");

  const loadMpStatus = useCallback(() => {
    if (!token) return;
    getMpStatus(tenantSlug, token)
      .then(setMpStatus)
      .catch(() => setMpError("No se pudo cargar el estado de Mercado Pago"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadMpStatus();
  }, [loadMpStatus]);

  useEffect(() => {
    if (mpResult) {
      const next = new URLSearchParams(searchParams);
      next.delete("mp");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mpResult]);

  async function handleMpConnect() {
    if (!token) return;
    setMpLoading(true);
    setMpError(null);
    try {
      const { url } = await getMpConnectUrl(tenantSlug, token);
      window.location.href = url;
    } catch (err) {
      setMpError(err instanceof ApiError ? err.message : "No se pudo iniciar la conexión con Mercado Pago");
      setMpLoading(false);
    }
  }

  async function handleMpDisconnect() {
    if (!token) return;
    setMpLoading(true);
    setMpError(null);
    try {
      const status = await disconnectMp(tenantSlug, token);
      setMpStatus(status);
    } catch (err) {
      setMpError(err instanceof ApiError ? err.message : "No se pudo desconectar Mercado Pago");
    } finally {
      setMpLoading(false);
    }
  }

  const [helipagosStatus, setHelipagosStatus] = useState<HelipagosStatus | null>(null);
  const [helipagosLoading, setHelipagosLoading] = useState(false);
  const [helipagosError, setHelipagosError] = useState<string | null>(null);
  const [helipagosForm, setHelipagosForm] = useState({
    token: "",
    webhook_apikey: "",
    environment: "sandbox" as "sandbox" | "production",
  });

  const loadHelipagosStatus = useCallback(() => {
    if (!token) return;
    getHelipagosStatus(tenantSlug, token)
      .then(setHelipagosStatus)
      .catch(() => setHelipagosError("No se pudo cargar el estado de Helipagos"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadHelipagosStatus();
  }, [loadHelipagosStatus]);

  async function handleHelipagosConnect(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setHelipagosLoading(true);
    setHelipagosError(null);
    try {
      const status = await connectHelipagos(tenantSlug, token, helipagosForm);
      setHelipagosStatus(status);
      setHelipagosForm({ token: "", webhook_apikey: "", environment: "sandbox" });
    } catch (err) {
      setHelipagosError(err instanceof ApiError ? err.message : "No se pudo conectar Helipagos");
    } finally {
      setHelipagosLoading(false);
    }
  }

  async function handleHelipagosDisconnect() {
    if (!token) return;
    setHelipagosLoading(true);
    setHelipagosError(null);
    try {
      const status = await disconnectHelipagos(tenantSlug, token);
      setHelipagosStatus(status);
    } catch (err) {
      setHelipagosError(err instanceof ApiError ? err.message : "No se pudo desconectar Helipagos");
    } finally {
      setHelipagosLoading(false);
    }
  }

  const [currentAdmin, setCurrentAdmin] = useState<AdminUserOut | null>(null);
  const isOwner = currentAdmin?.role === "owner";

  const [admins, setAdmins] = useState<AdminUserOut[]>([]);
  const [adminsError, setAdminsError] = useState<string | null>(null);
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [newAdminRole, setNewAdminRole] = useState<AdminRole>("staff");
  const [adminsSaving, setAdminsSaving] = useState(false);

  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);

  const loadAdminsAndAudit = useCallback(() => {
    if (!token) return;
    getCurrentAdmin(tenantSlug, token)
      .then(setCurrentAdmin)
      .catch(() => undefined);
  }, [tenantSlug, token]);

  useEffect(() => {
    loadAdminsAndAudit();
  }, [loadAdminsAndAudit]);

  const loadAdmins = useCallback(() => {
    if (!token || !isOwner) return;
    listAdmins(tenantSlug, token)
      .then(setAdmins)
      .catch(() => setAdminsError("No se pudo cargar la lista de administradores"));
    getAuditLog(tenantSlug, token)
      .then(setAuditLog)
      .catch(() => undefined);
  }, [tenantSlug, token, isOwner]);

  useEffect(() => {
    loadAdmins();
  }, [loadAdmins]);

  async function handleCreateAdmin(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setAdminsSaving(true);
    setAdminsError(null);
    try {
      await createAdmin(tenantSlug, token, {
        email: newAdminEmail,
        password: newAdminPassword,
        role: newAdminRole,
      });
      setNewAdminEmail("");
      setNewAdminPassword("");
      setNewAdminRole("staff");
      loadAdmins();
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo crear el administrador");
    } finally {
      setAdminsSaving(false);
    }
  }

  async function handleChangeAdminRole(admin: AdminUserOut, role: AdminRole) {
    if (!token) return;
    setAdminsError(null);
    try {
      await updateAdminRole(tenantSlug, token, admin.id, role);
      loadAdmins();
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo cambiar el rol");
    }
  }

  function handleRemoveAdmin(admin: AdminUserOut) {
    setConfirmState({
      message: `¿Eliminar al administrador ${admin.email}?`,
      onConfirm: async () => {
        if (!token) return;
        setAdminsError(null);
        try {
          await deleteAdmin(tenantSlug, token, admin.id);
          setConfirmState(null);
          loadAdmins();
        } catch (err) {
          setAdminsError(err instanceof ApiError ? err.message : "No se pudo eliminar el administrador");
          setConfirmState(null);
        }
      },
    });
  }

  const loadSettings = useCallback(() => {
    if (!token) return;
    getAdminSettings(tenantSlug, token)
      .then((s) => {
        setSettings(s);
        setSettingsForm({
          contact_email: s.contact_email ?? "",
          contact_phone: s.contact_phone ?? "",
          contact_whatsapp: s.contact_whatsapp ?? "",
          contact_address: s.contact_address ?? "",
          primary_color: s.primary_color,
        });
      })
      .catch(() => setSettingsError("No se pudo cargar la configuración"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSettingsSaving(true);
    setSettingsError(null);
    setSettingsSaved(false);
    try {
      const updated = await updateAdminSettings(tenantSlug, token, settingsForm);
      setSettings(updated);
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch (err) {
      setSettingsError(err instanceof ApiError ? err.message : "No se pudo guardar la configuración");
    } finally {
      setSettingsSaving(false);
    }
  }

  async function handleLogoChange(kind: "primary" | "secondary", file: File | null) {
    if (!token || !file) return;
    setLogoUploading(kind);
    setLogoError(null);
    try {
      const updated = await uploadLogo(tenantSlug, token, kind, file);
      setSettings(updated);
    } catch (err) {
      setLogoError(err instanceof ApiError ? err.message : "No se pudo subir el logo");
    } finally {
      setLogoUploading(null);
    }
  }

  async function handleLogoRemove(kind: "primary" | "secondary") {
    if (!token) return;
    setLogoUploading(kind);
    setLogoError(null);
    try {
      const updated = await deleteLogo(tenantSlug, token, kind);
      setSettings(updated);
    } catch (err) {
      setLogoError(err instanceof ApiError ? err.message : "No se pudo eliminar el logo");
    } finally {
      setLogoUploading(null);
    }
  }

  const refresh = useCallback(() => {
    if (!token) return;
    listMembers(tenantSlug, token)
      .then((rows) => {
        setMembers(rows);
        setSelected(new Set());
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "No se pudo cargar la lista de socios"));
  }, [tenantSlug, token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filteredMembers = useMemo(() => {
    const q = sociosQuery.trim().toLowerCase();
    if (!q) return members;
    return members.filter((m) =>
      [m.nombre, m.identificador, m.numero_socio].some((field) =>
        field?.toLowerCase().includes(q),
      ),
    );
  }, [members, sociosQuery]);

  const stats = useMemo(
    () => ({
      socios: members.length,
      saldo: members.reduce((total, m) => total + m.saldo_total, 0),
    }),
    [members],
  );

  if (!token) {
    return <Navigate to={`/${tenantSlug}/admin`} replace />;
  }

  function toggleSelected(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected((prev) => {
      const visibleIds = filteredMembers.map((m) => m.id);
      const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => prev.has(id));
      if (allVisibleSelected) {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      }
      return new Set([...prev, ...visibleIds]);
    });
  }

  function handleDeleteOne(member: MemberRow) {
    setConfirmState({
      message: `¿Eliminar a ${member.nombre} y todas sus facturas asociadas?`,
      onConfirm: async () => {
        setDeleteError(null);
        setDeleting(true);
        try {
          await deleteMember(tenantSlug, token!, member.id);
          setConfirmState(null);
          refresh();
        } catch (err) {
          setDeleteError(err instanceof ApiError ? err.message : "No se pudo eliminar el socio");
          setConfirmState(null);
        } finally {
          setDeleting(false);
        }
      },
    });
  }

  function handleDeleteSelected() {
    if (selected.size === 0) return;
    setConfirmState({
      message: `¿Eliminar ${selected.size} socio(s) y sus facturas asociadas?`,
      onConfirm: async () => {
        setDeleteError(null);
        setDeleting(true);
        try {
          await deleteMembers(tenantSlug, token!, Array.from(selected));
          setConfirmState(null);
          refresh();
        } catch (err) {
          setDeleteError(err instanceof ApiError ? err.message : "No se pudieron eliminar los socios seleccionados");
          setConfirmState(null);
        } finally {
          setDeleting(false);
        }
      },
    });
  }

  async function openInvoiceDrawer(member: MemberRow) {
    setDrawerMember(member);
    setDrawerOpen(true);
    setInvoices([]);
    setInvoicesError(null);
    setInvoicesLoading(true);
    try {
      const rows = await listMemberInvoices(tenantSlug, token!, member.id);
      setInvoices(rows);
    } catch (err) {
      setInvoicesError(err instanceof ApiError ? err.message : "No se pudieron cargar las facturas");
    } finally {
      setInvoicesLoading(false);
    }
  }

  function closeInvoiceDrawer() {
    setDrawerOpen(false);
  }

  async function handleTogglePagado(invoice: InvoiceOut) {
    if (!token) return;
    setTogglingId(invoice.id);
    try {
      const updated = await setInvoicePagado(tenantSlug, token, invoice.id, !invoice.pagado);
      setInvoices((prev) => prev.map((inv) => (inv.id === updated.id ? updated : inv)));
      refresh();
    } catch (err) {
      setInvoicesError(err instanceof ApiError ? err.message : "No se pudo actualizar el pago");
    } finally {
      setTogglingId(null);
    }
  }

  async function handleImport(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const result = await importSpreadsheet(tenantSlug, token!, file, year, month);
      setImportResult(result);
      refresh();
    } catch (err) {
      setImportError(err instanceof ApiError ? err.message : "Ocurrió un error al importar");
    } finally {
      setImporting(false);
    }
  }

  const accent = settings?.primary_color ?? "#2f5fe0";

  return (
    <div className="admin-panel" style={{ ["--accent" as string]: accent }}>
      <aside className="admin-sidebar">
        <div className="admin-sidebar-brand">
          <LogoPlaceholder src={settings?.logo_primary_url} alt={settings?.name} />
          <div className="admin-sidebar-brand-text">
            <span className="admin-sidebar-name">{settings?.name ?? "Cooperativa"}</span>
            <span className="admin-sidebar-sub">Administración</span>
          </div>
        </div>

        <AdminNav variant="sidebar" active={section} onChange={setSection} />

        <div className="admin-sidebar-footer">
          <Link className="admin-sidebar-footer-link" to={`/${tenantSlug}`}>
            Ver portal de socios
          </Link>
          {currentAdmin && <span className="muted admin-sidebar-email">{currentAdmin.email}</span>}
          <button type="button" className="btn-ghost" onClick={handleLogout}>
            Cerrar sesión
          </button>
        </div>
      </aside>

      <div className="admin-content">
        <header className="admin-topbar">
          <div className="admin-topbar-row">
            <div className="admin-topbar-brand">
              <LogoPlaceholder src={settings?.logo_primary_url} alt={settings?.name} />
              <div className="admin-topbar-brand-text">
                <span>{settings?.name ?? "Cooperativa"}</span>
                <span>Administración</span>
              </div>
            </div>
            <button type="button" className="btn-ghost" onClick={handleLogout}>
              Salir
            </button>
          </div>
          <AdminNav variant="tabs" active={section} onChange={setSection} />
        </header>

        <main className="admin-main">
          <div className="admin-main-inner">
          {section === "principal" && (
            <div className="admin-stats">
              <div className="admin-stat-card">
                <span className="admin-stat-label">Socios activos</span>
                <span className="admin-stat-value">{stats.socios}</span>
              </div>
              <div className="admin-stat-card">
                <span className="admin-stat-label">Saldo a cobrar</span>
                <span className="admin-stat-value">{money(stats.saldo)}</span>
              </div>
            </div>
          )}

          {section === "config" && (
      <form onSubmit={handleSaveSettings}>
      <div className="card">
        <div className="card-head">
          <h2>Identidad</h2>
        </div>
        <p className="muted small">
          Logos y color destacado que se muestran en el portal de socios.
        </p>

        <div className="settings-logos">
          <div className="settings-logo-field">
            <div className="settings-logo-row">
              <LogoPlaceholder className="settings-logo-preview" src={settings?.logo_primary_url} />
              <div className="settings-logo-info">
                <span className="settings-logo-label">Logo principal</span>
                <div className="settings-logo-actions">
                  <FilePicker
                    id="logo-primary"
                    file={null}
                    onChange={(f) => handleLogoChange("primary", f)}
                    accept="image/png,image/jpeg,image/webp,image/svg+xml"
                    buttonLabel={logoUploading === "primary" ? "Subiendo..." : "Subir imagen"}
                  />
                  {settings?.logo_primary_url && (
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={logoUploading === "primary"}
                      onClick={() => handleLogoRemove("primary")}
                    >
                      Eliminar
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="settings-logo-field">
            <div className="settings-logo-row">
              <LogoPlaceholder className="settings-logo-preview" src={settings?.logo_secondary_url} />
              <div className="settings-logo-info">
                <span className="settings-logo-label">Logo secundario</span>
                <div className="settings-logo-actions">
                  <FilePicker
                    id="logo-secondary"
                    file={null}
                    onChange={(f) => handleLogoChange("secondary", f)}
                    accept="image/png,image/jpeg,image/webp,image/svg+xml"
                    buttonLabel={logoUploading === "secondary" ? "Subiendo..." : "Subir imagen"}
                  />
                  {settings?.logo_secondary_url && (
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={logoUploading === "secondary"}
                      onClick={() => handleLogoRemove("secondary")}
                    >
                      Eliminar
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
        {logoError && <p className="error">{logoError}</p>}

        <div className="settings-form">
          <label>
            Color destacado
            <div className="color-field">
              <input
                type="color"
                value={settingsForm.primary_color}
                onChange={(e) => setSettingsForm((f) => ({ ...f, primary_color: e.target.value }))}
              />
              <input
                type="text"
                value={settingsForm.primary_color}
                onChange={(e) => setSettingsForm((f) => ({ ...f, primary_color: e.target.value }))}
                pattern="^#[0-9a-fA-F]{6}$"
                placeholder="#2563eb"
              />
            </div>
            <div className="color-swatches">
              {ACCENT_SWATCHES.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  aria-label={hex}
                  className={`color-swatch${settingsForm.primary_color.toLowerCase() === hex ? " is-active" : ""}`}
                  style={{ background: hex }}
                  onClick={() => setSettingsForm((f) => ({ ...f, primary_color: hex }))}
                />
              ))}
            </div>
          </label>
          <div className="config-color-preview">
            <span className="muted small">Vista previa en el portal</span>
            <div className="color-preview-box" style={{ ["--accent" as string]: settingsForm.primary_color }}>
              <span>Total a pagar</span>
              <span className="color-preview-amount">{money(12500)}</span>
              <span className="color-preview-btn">Descargar boleta (PDF)</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Contacto</h2>
        </div>
        <p className="muted small">
          Datos de contacto que se muestran en el portal de socios.
        </p>

        <div className="settings-form">
          <label>
            Email de contacto
            <input
              type="email"
              value={settingsForm.contact_email}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_email: e.target.value }))}
              placeholder="contacto@cooperativa.coop"
            />
          </label>
          <label>
            Teléfono
            <input
              value={settingsForm.contact_phone}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_phone: e.target.value }))}
              placeholder="+54 351 555-1234"
            />
          </label>
          <label>
            WhatsApp
            <input
              value={settingsForm.contact_whatsapp}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_whatsapp: e.target.value }))}
              placeholder="+54 9 351 555-1234"
            />
          </label>
          <label className="settings-form-address">
            Dirección
            <input
              value={settingsForm.contact_address}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_address: e.target.value }))}
              placeholder="Calle 123, Localidad"
            />
          </label>
          <button type="submit" disabled={settingsSaving}>
            {settingsSaving ? "Guardando..." : "Guardar configuración"}
          </button>
          {settingsSaved && <p className="success">Configuración guardada.</p>}
          {settingsError && <p className="error">{settingsError}</p>}
        </div>
      </div>
      </form>
      )}

      {section === "config" && (
      <div className="card">
        <div className="card-head">
          <h2>Mercado Pago</h2>
        </div>
        <p className="muted small">
          Conectá la cuenta de Mercado Pago de la cooperativa para que los socios puedan pagar sus
          boletas online. El dinero se acredita directamente en tu cuenta de Mercado Pago — Coopera
          nunca lo recibe ni lo retiene.
        </p>

        {mpResult === "success" && <p className="success">Mercado Pago conectado correctamente.</p>}
        {mpResult === "error" && (
          <p className="error">No se pudo completar la conexión con Mercado Pago. Probá de nuevo.</p>
        )}

        {mpStatus && !mpStatus.configured && (
          <p className="muted small">
            Esta instancia de Coopera todavía no tiene configurada la integración con Mercado Pago
            (falta de lado del servidor). Contactá al equipo de Coopera.
          </p>
        )}

        {mpStatus?.configured && !isOwner && (
          <p className="muted small">
            Solo un administrador con rol "owner" puede conectar o desconectar Mercado Pago.
          </p>
        )}

        {mpStatus?.configured && isOwner && (
          <div className="mp-connect">
            {mpStatus.connected ? (
              <>
                <p className="success">
                  Conectado {mpStatus.mp_user_id ? `(cuenta MP #${mpStatus.mp_user_id})` : ""}
                </p>
                <button type="button" className="btn-danger" disabled={mpLoading} onClick={handleMpDisconnect}>
                  {mpLoading ? "Desconectando..." : "Desconectar Mercado Pago"}
                </button>
              </>
            ) : (
              <button type="button" disabled={mpLoading} onClick={handleMpConnect}>
                {mpLoading ? "Redirigiendo..." : "Conectar con Mercado Pago"}
              </button>
            )}
          </div>
        )}
        {mpError && <p className="error">{mpError}</p>}
      </div>
      )}

      {section === "config" && (
      <div className="card">
        <div className="card-head">
          <h2>Helipagos</h2>
        </div>
        <p className="muted small">
          Conectá el token de Helipagos de la cooperativa para que los socios puedan pagar sus
          boletas online (tarjeta, código de barras, QR). A diferencia de Mercado Pago, no hace
          falta autorizar nada: pegá el token y el apikey de webhook que te dio Helipagos al darte
          de alta.
        </p>

        {helipagosStatus && !isOwner && (
          <p className="muted small">
            Solo un administrador con rol "owner" puede conectar o desconectar Helipagos.
          </p>
        )}

        {helipagosStatus?.connected && isOwner && (
          <div className="mp-connect">
            <p className="success">
              Conectado ({helipagosStatus.environment === "production" ? "producción" : "sandbox"})
            </p>
            <button
              type="button"
              className="btn-danger"
              disabled={helipagosLoading}
              onClick={handleHelipagosDisconnect}
            >
              {helipagosLoading ? "Desconectando..." : "Desconectar Helipagos"}
            </button>
          </div>
        )}

        {helipagosStatus && !helipagosStatus.connected && isOwner && (
          <form className="settings-form" onSubmit={handleHelipagosConnect}>
            <label>
              Token
              <input
                value={helipagosForm.token}
                onChange={(e) => setHelipagosForm((f) => ({ ...f, token: e.target.value }))}
                placeholder="Token Bearer provisto por Helipagos"
                required
              />
            </label>
            <label>
              Apikey de webhook
              <input
                value={helipagosForm.webhook_apikey}
                onChange={(e) => setHelipagosForm((f) => ({ ...f, webhook_apikey: e.target.value }))}
                placeholder="Valor del header 'apikey' que envía Helipagos"
                required
              />
            </label>
            <label>
              Entorno
              <select
                value={helipagosForm.environment}
                onChange={(e) =>
                  setHelipagosForm((f) => ({
                    ...f,
                    environment: e.target.value as "sandbox" | "production",
                  }))
                }
              >
                <option value="sandbox">Sandbox (pruebas)</option>
                <option value="production">Producción</option>
              </select>
            </label>
            <button type="submit" disabled={helipagosLoading}>
              {helipagosLoading ? "Conectando..." : "Conectar Helipagos"}
            </button>
          </form>
        )}
        {helipagosError && <p className="error">{helipagosError}</p>}
      </div>
      )}

      {section === "config" && isOwner && (
      <div className="card admins-card">
        <div className="card-head">
          <h2>Administradores</h2>
        </div>

        <div className="role-legend">
          <div className="role-legend-item">
            <span className="role-chip role-chip-owner">
              <Crown size={13} aria-hidden="true" /> owner
            </span>
            <p className="muted small">Conecta o desconecta Mercado Pago y gestiona otros administradores.</p>
          </div>
          <div className="role-legend-item">
            <span className="role-chip role-chip-staff">
              <UserCog size={13} aria-hidden="true" /> staff
            </span>
            <p className="muted small">Accede al resto del panel: socios, importaciones y boletas.</p>
          </div>
        </div>

        <table className="socios-table admins-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Rol</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {admins.map((a) => {
              const isYou = a.id === currentAdmin?.id;
              return (
                <tr key={a.id}>
                  <td data-label="Email">
                    {a.email}
                    {isYou && <span className="you-badge">Tú</span>}
                  </td>
                  <td data-label="Rol">
                    <select
                      className={`role-select role-select-${a.role}`}
                      value={a.role}
                      onChange={(e) => handleChangeAdminRole(a, e.target.value as AdminRole)}
                      disabled={isYou}
                      title={isYou ? "No podés modificar tu propio rol" : undefined}
                    >
                      <option value="owner">owner</option>
                      <option value="staff">staff</option>
                    </select>
                  </td>
                  <td className="socios-table-actions">
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={isYou}
                      title={isYou ? "No podés eliminar tu propia cuenta" : undefined}
                      onClick={() => handleRemoveAdmin(a)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Eliminar
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="admins-divider" />

        <div className="admins-invite-head">
          <UserPlus size={16} aria-hidden="true" />
          <h3>Invitar nuevo administrador</h3>
        </div>
        <form className="settings-form" onSubmit={handleCreateAdmin}>
          <label>
            Email
            <input
              type="email"
              value={newAdminEmail}
              onChange={(e) => setNewAdminEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Contraseña
            <input
              type="password"
              value={newAdminPassword}
              onChange={(e) => setNewAdminPassword(e.target.value)}
              required
              minLength={8}
            />
          </label>
          <label>
            Rol
            <select value={newAdminRole} onChange={(e) => setNewAdminRole(e.target.value as AdminRole)}>
              <option value="staff">staff</option>
              <option value="owner">owner</option>
            </select>
          </label>
          <button type="submit" disabled={adminsSaving}>
            {adminsSaving ? "Creando..." : "Invitar administrador"}
          </button>
        </form>
        {adminsError && <p className="error">{adminsError}</p>}
      </div>
      )}

      {section === "config" && isOwner && (
      <div className="card">
        <div className="card-head">
          <h2>Actividad reciente</h2>
        </div>
        <p className="muted small">Últimas acciones sensibles realizadas en esta cooperativa.</p>
        {auditLog.length === 0 && <p className="muted small">Todavía no hay actividad registrada.</p>}
        {auditLog.length > 0 && (
          <ul className="audit-log-list">
            {auditLog.map((entry) => (
              <li key={entry.id}>
                <span className="muted small">{new Date(entry.created_at).toLocaleString("es-AR")}</span>{" "}
                — <strong>{entry.actor_email}</strong> ({entry.actor_type}): {entry.action}
                {entry.details ? ` — ${entry.details}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
      )}

      {section === "principal" && (
      <div className="card">
        <div className="card-head">
          <h2>Importar planilla del período</h2>
        </div>
        <p className="muted small">
          Columnas requeridas: <code>numero_socio</code>, <code>nombre</code>, <code>identificador</code>,{" "}
          <code>consumo</code>, <code>monto</code>. Opcional: <code>vencimiento</code>. Formato .csv o .xlsx.
        </p>
        <form className="import-form" onSubmit={handleImport} style={{ marginTop: "var(--space-4)" }}>
          <label>
            Año
            <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} required />
          </label>
          <label>
            Mes
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MESES.slice(1).map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <div className="file-field">
            <span>Planilla</span>
            <FilePicker id="import-file" file={file} onChange={setFile} accept=".csv,.xlsx,.xls" required />
          </div>
          <button type="submit" disabled={importing || !file}>
            {importing ? "Importando..." : "Importar"}
          </button>
        </form>
        {importError && <p className="error">{importError}</p>}
        {importResult && (
          <p className="success">
            Listo: {importResult.rows_processed} filas procesadas ({importResult.members_created} socios nuevos,{" "}
            {importResult.members_updated} actualizados) para {MESES[importResult.period_month]} {importResult.period_year}.
          </p>
        )}
      </div>
      )}

      {section === "socios" && (
      <div className="card">
        <div className="card-head">
          <h2>Socios ({filteredMembers.length}{sociosQuery && `/${members.length}`})</h2>
          <button
            type="button"
            className="btn-danger"
            disabled={selected.size === 0 || deleting}
            onClick={handleDeleteSelected}
          >
            Eliminar seleccionados ({selected.size})
          </button>
        </div>
        <div className="socios-search">
          <Search size={16} className="socios-search-icon" aria-hidden="true" />
          <input
            type="search"
            value={sociosQuery}
            onChange={(e) => setSociosQuery(e.target.value)}
            placeholder="Buscar por nombre, N° de socio o DNI/medidor..."
            aria-label="Buscar socios"
          />
          {sociosQuery && (
            <button
              type="button"
              className="socios-search-clear"
              onClick={() => setSociosQuery("")}
              aria-label="Limpiar búsqueda"
            >
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>
        {loadError && <p className="error">{loadError}</p>}
        {deleteError && <p className="error">{deleteError}</p>}
        {filteredMembers.length === 0 && members.length > 0 && (
          <p className="muted small socios-empty">Ningún socio coincide con “{sociosQuery}”.</p>
        )}
        <table className="socios-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={filteredMembers.length > 0 && filteredMembers.every((m) => selected.has(m.id))}
                  onChange={toggleSelectAll}
                  aria-label="Seleccionar todos"
                />
              </th>
              <th>N° Socio</th>
              <th>Nombre</th>
              <th>DNI / Medidor</th>
              <th>Saldo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filteredMembers.map((m) => (
              <tr key={m.id}>
                <td className="socios-table-check">
                  <input
                    type="checkbox"
                    checked={selected.has(m.id)}
                    onChange={() => toggleSelected(m.id)}
                    aria-label={`Seleccionar ${m.nombre}`}
                  />
                </td>
                <td data-label="N° Socio">{m.numero_socio}</td>
                <td data-label="Nombre">{m.nombre}</td>
                <td data-label="DNI / Medidor">{m.identificador}</td>
                <td data-label="Saldo">{money(m.saldo_total)}</td>
                <td className="socios-table-actions">
                  <button type="button" onClick={() => openInvoiceDrawer(m)}>
                    Ver facturas
                  </button>
                  <button
                    type="button"
                    className="btn-danger"
                    disabled={deleting}
                    onClick={() => handleDeleteOne(m)}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
        </div>
        </main>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={closeInvoiceDrawer}
        title={
          drawerMember ? (
            <div className="drawer-head-info">
              <span className="drawer-head-number">Socio N° {drawerMember.numero_socio}</span>
              <span className="drawer-head-name">{drawerMember.nombre}</span>
              <span className="drawer-head-balance">
                Saldo adeudado: <strong>{money(drawerMember.saldo_total)}</strong>
              </span>
            </div>
          ) : (
            "Facturas"
          )
        }
      >
        {invoicesLoading && <p className="muted small">Cargando facturas...</p>}
        {invoicesError && <p className="error">{invoicesError}</p>}
        {!invoicesLoading && !invoicesError && invoices.length === 0 && (
          <p className="muted small">Este socio no tiene facturas cargadas.</p>
        )}
        {!invoicesLoading && invoices.length > 0 && (
          <div className="invoice-list">
            {invoices.map((inv) => (
              <div className="invoice-item" key={inv.id}>
                <div className="invoice-item-row">
                  <span className="invoice-item-period">
                    {MESES[inv.period_month]} {inv.period_year}
                  </span>
                  <span className={`invoice-status ${inv.pagado ? "is-pagado" : "is-pendiente"}`}>
                    {inv.pagado ? "Pagada" : "Pendiente"}
                  </span>
                </div>
                <div className="invoice-item-details">
                  <div>
                    <span className="label">Consumo</span>
                    <span className="value">{inv.consumo}</span>
                  </div>
                  <div>
                    <span className="label">Monto</span>
                    <span className="value">{money(inv.monto)}</span>
                  </div>
                  <div>
                    <span className="label">Vencimiento</span>
                    <span className="value">{inv.vencimiento ?? "-"}</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={togglingId === inv.id}
                  onClick={() => handleTogglePagado(inv)}
                >
                  {inv.pagado ? "Marcar como pendiente" : "Marcar como pagada"}
                </button>
              </div>
            ))}
          </div>
        )}
      </Drawer>

      <ConfirmDialog
        open={confirmState !== null}
        title="Confirmar eliminación"
        message={confirmState?.message ?? ""}
        confirmLabel="Eliminar"
        danger
        busy={deleting}
        onConfirm={() => confirmState?.onConfirm()}
        onCancel={() => setConfirmState(null)}
      />
    </div>
  );
}
