import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  ApiError,
  createTenant,
  createTenantAdmin,
  deleteTenantAdmin,
  getPdfProfile,
  listTenantAdmins,
  listTenants,
  resetTenantAdminPassword,
  savePdfProfile,
  testPdfProfile,
  type AdminUserOut,
  type PdfProfilePreviewPage,
  type TenantSummary,
} from "../lib/api";
import Drawer from "../components/Drawer";
import ConfirmDialog from "../components/ConfirmDialog";
import FilePicker from "../components/FilePicker";

const NEW_TENANT_INITIAL = {
  slug: "",
  name: "",
  admin_email: "",
  admin_password: "",
};

export default function DevDashboard() {
  const navigate = useNavigate();
  const token = sessionStorage.getItem("coopera_dev_token");

  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [newTenant, setNewTenant] = useState(NEW_TENANT_INITIAL);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [drawerSlug, setDrawerSlug] = useState<string | null>(null);
  const [admins, setAdmins] = useState<AdminUserOut[]>([]);
  const [adminsError, setAdminsError] = useState<string | null>(null);
  const [adminsLoading, setAdminsLoading] = useState(false);

  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [addingAdmin, setAddingAdmin] = useState(false);

  const [resetTarget, setResetTarget] = useState<AdminUserOut | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetting, setResetting] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState<AdminUserOut | null>(null);
  const [deletingAdmin, setDeletingAdmin] = useState(false);

  const [pdfSlug, setPdfSlug] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfFields, setPdfFields] = useState<{ field: string; pattern: string }[]>([
    { field: "numero_socio", pattern: "" },
  ]);
  const [pdfSampleFile, setPdfSampleFile] = useState<File | null>(null);
  const [pdfTesting, setPdfTesting] = useState(false);
  const [pdfPreview, setPdfPreview] = useState<PdfProfilePreviewPage[] | null>(null);
  const [pdfSaving, setPdfSaving] = useState(false);
  const [pdfSaved, setPdfSaved] = useState(false);

  const refresh = useCallback(() => {
    if (!token) return;
    listTenants(token)
      .then(setTenants)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "No se pudieron cargar las cooperativas"));
  }, [token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!token) {
    return <Navigate to="/dev" replace />;
  }

  async function handleCreateTenant(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      await createTenant(token!, newTenant);
      setNewTenant(NEW_TENANT_INITIAL);
      refresh();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "No se pudo crear la cooperativa");
    } finally {
      setCreating(false);
    }
  }

  function openAdmins(slug: string) {
    setDrawerSlug(slug);
    setAdmins([]);
    setAdminsError(null);
    setNewAdminEmail("");
    setNewAdminPassword("");
    setAdminsLoading(true);
    listTenantAdmins(token!, slug)
      .then(setAdmins)
      .catch((err) => setAdminsError(err instanceof ApiError ? err.message : "No se pudieron cargar los admins"))
      .finally(() => setAdminsLoading(false));
  }

  async function handleAddAdmin(e: FormEvent) {
    e.preventDefault();
    if (!drawerSlug) return;
    setAddingAdmin(true);
    setAdminsError(null);
    try {
      const admin = await createTenantAdmin(token!, drawerSlug, newAdminEmail, newAdminPassword);
      setAdmins((prev) => [...prev, admin]);
      setNewAdminEmail("");
      setNewAdminPassword("");
      refresh();
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo crear el admin");
    } finally {
      setAddingAdmin(false);
    }
  }

  async function handleResetPassword(e: FormEvent) {
    e.preventDefault();
    if (!drawerSlug || !resetTarget) return;
    setResetting(true);
    try {
      await resetTenantAdminPassword(token!, drawerSlug, resetTarget.id, resetPassword);
      setResetTarget(null);
      setResetPassword("");
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo restablecer la contraseña");
    } finally {
      setResetting(false);
    }
  }

  async function handleDeleteAdmin() {
    if (!drawerSlug || !confirmDelete) return;
    setDeletingAdmin(true);
    try {
      await deleteTenantAdmin(token!, drawerSlug, confirmDelete.id);
      setAdmins((prev) => prev.filter((a) => a.id !== confirmDelete.id));
      setConfirmDelete(null);
      refresh();
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo eliminar el admin");
    } finally {
      setDeletingAdmin(false);
    }
  }

  function openPdfProfile(slug: string) {
    setPdfSlug(slug);
    setPdfError(null);
    setPdfPreview(null);
    setPdfSampleFile(null);
    setPdfSaved(false);
    setPdfLoading(true);
    getPdfProfile(token!, slug)
      .then((profile) => {
        const entries = profile ? Object.entries(profile.field_patterns) : [];
        setPdfFields(
          entries.length > 0
            ? entries.map(([field, pattern]) => ({ field, pattern }))
            : [{ field: "numero_socio", pattern: "" }],
        );
      })
      .catch((err) => setPdfError(err instanceof ApiError ? err.message : "No se pudo cargar el perfil"))
      .finally(() => setPdfLoading(false));
  }

  function fieldPatternsObject() {
    const obj: Record<string, string> = {};
    for (const { field, pattern } of pdfFields) {
      if (field.trim()) obj[field.trim()] = pattern;
    }
    return obj;
  }

  function updatePdfField(index: number, key: "field" | "pattern", value: string) {
    setPdfFields((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }

  function addPdfFieldRow() {
    setPdfFields((prev) => [...prev, { field: "", pattern: "" }]);
  }

  function removePdfFieldRow(index: number) {
    setPdfFields((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleTestPdfProfile(e: FormEvent) {
    e.preventDefault();
    if (!pdfSlug || !pdfSampleFile) return;
    setPdfTesting(true);
    setPdfError(null);
    setPdfPreview(null);
    try {
      const pages = await testPdfProfile(token!, pdfSlug, fieldPatternsObject(), pdfSampleFile);
      setPdfPreview(pages);
    } catch (err) {
      setPdfError(err instanceof ApiError ? err.message : "No se pudo probar el perfil");
    } finally {
      setPdfTesting(false);
    }
  }

  async function handleSavePdfProfile() {
    if (!pdfSlug) return;
    setPdfSaving(true);
    setPdfError(null);
    setPdfSaved(false);
    try {
      await savePdfProfile(token!, pdfSlug, fieldPatternsObject());
      setPdfSaved(true);
    } catch (err) {
      setPdfError(err instanceof ApiError ? err.message : "No se pudo guardar el perfil");
    } finally {
      setPdfSaving(false);
    }
  }

  function openTenantPanel(slug: string) {
    sessionStorage.setItem(`coopera_token_${slug}`, token!);
    navigate(`/${slug}/admin/dashboard`);
  }

  return (
    <div className="admin-dashboard">
      <header className="tenant-header">
        <div>
          <h1>Panel de plataforma</h1>
          <p className="muted">Cooperativas dadas de alta en Coopera. Acceso completo para soporte.</p>
        </div>
      </header>

      <div className="card">
        <div className="card-head">
          <h2>Nueva cooperativa</h2>
        </div>
        <form className="settings-form" onSubmit={handleCreateTenant}>
          <label>
            Slug
            <input
              value={newTenant.slug}
              onChange={(e) => setNewTenant((f) => ({ ...f, slug: e.target.value }))}
              placeholder="mi-cooperativa"
              required
            />
          </label>
          <label>
            Nombre
            <input
              value={newTenant.name}
              onChange={(e) => setNewTenant((f) => ({ ...f, name: e.target.value }))}
              placeholder="Cooperativa de Servicios..."
              required
            />
          </label>
          <label>
            Email del primer admin
            <input
              type="email"
              value={newTenant.admin_email}
              onChange={(e) => setNewTenant((f) => ({ ...f, admin_email: e.target.value }))}
              required
            />
          </label>
          <label>
            Contraseña del primer admin
            <input
              type="password"
              value={newTenant.admin_password}
              onChange={(e) => setNewTenant((f) => ({ ...f, admin_password: e.target.value }))}
              required
            />
          </label>
          <button type="submit" disabled={creating}>
            {creating ? "Creando..." : "Crear cooperativa"}
          </button>
          {createError && <p className="error">{createError}</p>}
        </form>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Cooperativas ({tenants.length})</h2>
        </div>
        {loadError && <p className="error">{loadError}</p>}
        <table className="socios-table">
          <thead>
            <tr>
              <th>Slug</th>
              <th>Nombre</th>
              <th>Admins</th>
              <th>Socios</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.id}>
                <td data-label="Slug">{t.slug}</td>
                <td data-label="Nombre">{t.name}</td>
                <td data-label="Admins">{t.admin_count}</td>
                <td data-label="Socios">{t.member_count}</td>
                <td className="socios-table-actions">
                  <button type="button" onClick={() => openAdmins(t.slug)}>
                    Admins
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => openPdfProfile(t.slug)}>
                    Perfil PDF
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => openTenantPanel(t.slug)}>
                    Abrir panel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Drawer open={drawerSlug !== null} onClose={() => setDrawerSlug(null)} title={`Admins de ${drawerSlug}`}>
        {adminsLoading && <p className="muted small">Cargando...</p>}
        {adminsError && <p className="error">{adminsError}</p>}
        {!adminsLoading && (
          <div className="invoice-list">
            {admins.map((a) => (
              <div className="invoice-item" key={a.id}>
                <div className="invoice-item-row">
                  <span>{a.email}</span>
                </div>
                <button type="button" className="btn-secondary" onClick={() => setResetTarget(a)}>
                  Restablecer contraseña
                </button>
                <button type="button" className="btn-danger" onClick={() => setConfirmDelete(a)}>
                  Eliminar
                </button>
              </div>
            ))}
          </div>
        )}

        <form className="lookup-form" onSubmit={handleAddAdmin} style={{ marginTop: "var(--space-4)" }}>
          <h3>Agregar admin</h3>
          <label>
            Email
            <input type="email" value={newAdminEmail} onChange={(e) => setNewAdminEmail(e.target.value)} required />
          </label>
          <label>
            Contraseña
            <input
              type="password"
              value={newAdminPassword}
              onChange={(e) => setNewAdminPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={addingAdmin}>
            {addingAdmin ? "Agregando..." : "Agregar admin"}
          </button>
        </form>

        {resetTarget && (
          <form className="lookup-form" onSubmit={handleResetPassword} style={{ marginTop: "var(--space-4)" }}>
            <h3>Nueva contraseña para {resetTarget.email}</h3>
            <label>
              Contraseña
              <input
                type="password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                required
              />
            </label>
            <button type="submit" disabled={resetting}>
              {resetting ? "Guardando..." : "Guardar"}
            </button>
            <button type="button" className="btn-ghost" onClick={() => setResetTarget(null)}>
              Cancelar
            </button>
          </form>
        )}
      </Drawer>

      <Drawer open={pdfSlug !== null} onClose={() => setPdfSlug(null)} title={`Perfil de importación PDF — ${pdfSlug}`}>
        {pdfLoading && <p className="muted small">Cargando...</p>}
        {pdfError && <p className="error">{pdfError}</p>}

        {!pdfLoading && (
          <>
            <p className="muted small">
              Un patrón por campo (regex con un grupo de captura). Cada página del PDF es un socio; se usa el{" "}
              <strong>último</strong> match de cada patrón en la página. <code>numero_socio</code> es obligatorio.
            </p>

            <div className="invoice-list">
              {pdfFields.map((row, i) => (
                <div className="invoice-item-row" key={i} style={{ gap: "var(--space-2)" }}>
                  <input
                    placeholder="campo (ej. consumo)"
                    value={row.field}
                    onChange={(e) => updatePdfField(i, "field", e.target.value)}
                    style={{ flex: "0 0 40%" }}
                  />
                  <input
                    placeholder="regex con (grupo)"
                    value={row.pattern}
                    onChange={(e) => updatePdfField(i, "pattern", e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="btn-ghost" onClick={() => removePdfFieldRow(i)}>
                    Quitar
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="btn-secondary" onClick={addPdfFieldRow} style={{ marginTop: "var(--space-2)" }}>
              Agregar campo
            </button>

            <form className="lookup-form" onSubmit={handleTestPdfProfile} style={{ marginTop: "var(--space-4)" }}>
              <h3>Probar con un PDF de muestra</h3>
              <div className="file-field">
                <span>PDF de muestra</span>
                <FilePicker id="pdf-sample-file" file={pdfSampleFile} onChange={setPdfSampleFile} accept=".pdf" required />
              </div>
              <button type="submit" disabled={pdfTesting || !pdfSampleFile}>
                {pdfTesting ? "Probando..." : "Probar"}
              </button>
            </form>

            {pdfPreview && (
              <div className="invoice-list" style={{ marginTop: "var(--space-4)" }}>
                <h3>Resultado ({pdfPreview.length} páginas)</h3>
                {pdfPreview.map((p) => (
                  <div className="invoice-item" key={p.page}>
                    <div className="invoice-item-row">
                      <strong>Página {p.page}</strong>
                    </div>
                    <ul className="audit-log-list">
                      {Object.entries(p.fields).map(([field, value]) => (
                        <li key={field}>
                          <code>{field}</code>: {value ?? <span className="muted">(sin match)</span>}
                        </li>
                      ))}
                    </ul>
                    <details>
                      <summary className="muted small">Texto crudo</summary>
                      <pre className="small" style={{ whiteSpace: "pre-wrap" }}>
                        {p.raw_text}
                      </pre>
                    </details>
                  </div>
                ))}
              </div>
            )}

            <button
              type="button"
              onClick={handleSavePdfProfile}
              disabled={pdfSaving}
              style={{ marginTop: "var(--space-4)" }}
            >
              {pdfSaving ? "Guardando..." : "Guardar perfil"}
            </button>
            {pdfSaved && <p className="success">Perfil guardado.</p>}
          </>
        )}
      </Drawer>

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Eliminar admin"
        message={confirmDelete ? `¿Eliminar el acceso de ${confirmDelete.email}?` : ""}
        confirmLabel="Eliminar"
        danger
        busy={deletingAdmin}
        onConfirm={handleDeleteAdmin}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
