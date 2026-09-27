import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, devLogin } from "../lib/api";

export default function DevLogin() {
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
      const { access_token } = await devLogin(email, password);
      sessionStorage.setItem("coopera_dev_token", access_token);
      navigate("/dev/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="tenant-search-view">
      <div className="login-card">
        <header className="tenant-header-centered">
          <span className="admin-login-badge">Acceso equipo Coopera</span>
          <h1>Panel de plataforma</h1>
        </header>

        <form className="lookup-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
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
    </div>
  );
}
