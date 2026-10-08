import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, adminLogin, getTenant, type TenantPublic } from "../lib/api";
import LogoPlaceholder from "../components/LogoPlaceholder";

export default function AdminLogin() {
  const { tenantSlug = "" } = useParams();
  const navigate = useNavigate();
  const [tenant, setTenant] = useState<TenantPublic | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getTenant(tenantSlug).then(setTenant).catch(() => setTenant(null));
  }, [tenantSlug]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { access_token } = await adminLogin(tenantSlug, email, password);
      sessionStorage.setItem(`coopera_token_${tenantSlug}`, access_token);
      navigate(`/${tenantSlug}/admin/dashboard`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="tenant-search-view admin-ink">
      <div className="login-card">
        <header className="tenant-header-centered">
          <LogoPlaceholder className="tenant-logo-centered" src={tenant?.logo_primary_url} alt={tenant?.name} />
          <span className="admin-login-badge">Acceso administrador</span>
          <h1>{tenant?.name ?? "Cargando..."}</h1>
        </header>

        <form className="lookup-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Contraseña
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Ingresando..." : "Ingresar"}
          </button>
          {error && <p className="error">{error}</p>}
        </form>

        <footer className="tenant-footer-centered">
          <Link to={`/${tenantSlug}`}>volver al acceso de socios</Link>
        </footer>
      </div>
    </div>
  );
}
