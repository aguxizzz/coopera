import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, adminLogin } from "../lib/api";

export default function AdminLogin() {
  const { tenantSlug = "" } = useParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { access_token } = await adminLogin(tenantSlug, email, password);
      sessionStorage.setItem(`coopero_token_${tenantSlug}`, access_token);
      navigate(`/${tenantSlug}/admin/dashboard`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-center">
      <form className="card lookup-form" onSubmit={handleSubmit}>
        <h1>Panel de la cooperativa</h1>
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
    </div>
  );
}
