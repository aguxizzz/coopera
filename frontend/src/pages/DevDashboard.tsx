import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  ApiError,
  createTenant,
  createTenantAdmin,
  deleteTenantAdmin,
  listTenantAdmins,
  listTenants,
  resetTenantAdminPassword,
  type AdminUserOut,
  type TenantSummary,
} from "../lib/api";
import Drawer from "../components/Drawer";
import ConfirmDialog from "../components/ConfirmDialog";

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
