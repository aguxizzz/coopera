import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Navigate, useParams } from "react-router-dom";
import { Search, X } from "lucide-react";
import {
  ApiError,
  deleteLogo,
  deleteMember,
  deleteMembers,
  getAdminSettings,
  importSpreadsheet,
  listMemberInvoices,
  listMembers,
  setInvoicePagado,
  updateAdminSettings,
  uploadLogo,
  type ImportResult,
  type InvoiceOut,
  type MemberRow,
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

export default function AdminDashboard() {
  const { tenantSlug = "" } = useParams();
  const token = sessionStorage.getItem(`coopera_token_${tenantSlug}`);

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
    <div className="admin-dashboard" style={{ ["--accent" as string]: accent }}>
      <LogoPlaceholder className="admin-logo-fixed" src={settings?.logo_primary_url} />

      <header className="tenant-header">
        <div className="admin-header-brand">
          <LogoPlaceholder className="admin-logo-inline" src={settings?.logo_primary_url} />
          <div>
            <h1>{settings?.name ?? "Panel de administración"}</h1>
            <p className="muted">Subí la planilla mensual para actualizar el consumo y la deuda de tus socios.</p>
          </div>
        </div>
      </header>

      <AdminNav active={section} onChange={setSection} />

      {section === "config" && (
      <div className="card">
        <div className="card-head">
          <h2>Configuración de la cooperativa</h2>
        </div>
        <p className="muted small">
          Estos datos se muestran en el portal de socios: logos, color destacado y forma de contacto.
        </p>

        <div className="settings-logos">
          <div className="settings-logo-field">
            <span className="settings-logo-label">Logo principal</span>
            <div className="settings-logo-row">
              <LogoPlaceholder className="settings-logo-preview" src={settings?.logo_primary_url} />
              <FilePicker
                id="logo-primary"
                file={null}
                onChange={(f) => handleLogoChange("primary", f)}
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                buttonLabel={logoUploading === "primary" ? "Subiendo..." : "Cambiar logo"}
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
          <div className="settings-logo-field">
            <span className="settings-logo-label">Logo secundario</span>
            <div className="settings-logo-row">
              <LogoPlaceholder className="settings-logo-preview" src={settings?.logo_secondary_url} />
              <FilePicker
                id="logo-secondary"
                file={null}
                onChange={(f) => handleLogoChange("secondary", f)}
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                buttonLabel={logoUploading === "secondary" ? "Subiendo..." : "Cambiar logo"}
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
        {logoError && <p className="error">{logoError}</p>}

        <form className="settings-form" onSubmit={handleSaveSettings}>
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
          </label>
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
        </form>
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

      <Drawer
        open={drawerOpen}
        onClose={closeInvoiceDrawer}
        title={drawerMember ? `Facturas de ${drawerMember.nombre}` : "Facturas"}
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
