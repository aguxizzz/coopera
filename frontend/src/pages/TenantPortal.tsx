import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  boletaUrl,
  getTenant,
  lookupMember,
  type MemberAccount,
  type TenantPublic,
} from "../lib/api";

const MESES = [
  "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function money(value: number) {
  return value.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
}

export default function TenantPortal() {
  const { tenantSlug = "" } = useParams();
  const [tenant, setTenant] = useState<TenantPublic | null>(null);
  const [tenantError, setTenantError] = useState<string | null>(null);

  const [numeroSocio, setNumeroSocio] = useState("");
  const [identificador, setIdentificador] = useState("");
  const [account, setAccount] = useState<MemberAccount | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getTenant(tenantSlug)
      .then(setTenant)
      .catch(() => setTenantError("No encontramos esta cooperativa."));
  }, [tenantSlug]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setAccount(null);
    setLoading(true);
    try {
      const data = await lookupMember(tenantSlug, numeroSocio, identificador);
      setAccount(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
    } finally {
      setLoading(false);
    }
  }

  function copyAlias(alias: string) {
    navigator.clipboard.writeText(alias).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (tenantError) {
    return (
      <div className="page-center">
        <p>{tenantError}</p>
        <Link to="/">Volver al inicio</Link>
      </div>
    );
  }

  const accent = tenant?.primary_color ?? "#2563eb";

  return (
    <div className="tenant-portal" style={{ ["--accent" as string]: accent }}>
      <header className="tenant-header">
        <h1>{tenant?.name ?? "Cargando..."}</h1>
        <p className="muted">Consultá tu consumo y tu saldo como socio.</p>
      </header>

      <form className="card lookup-form" onSubmit={handleSubmit}>
        <label>
          Número de socio
          <input
            value={numeroSocio}
            onChange={(e) => setNumeroSocio(e.target.value)}
            placeholder="Ej: 101"
            required
          />
        </label>
        <label>
          DNI o número de medidor
          <input
            value={identificador}
            onChange={(e) => setIdentificador(e.target.value)}
            placeholder="Ej: 30111222"
            required
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Buscando..." : "Consultar"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>

      {account && (
        <div className="card account-result">
          <h2>Hola, {account.nombre}</h2>
          <div className="balance-row">
            <div>
              <span className="label">Saldo total adeudado</span>
              <span className="balance">{money(account.saldo_total)}</span>
            </div>
            {account.ultima_factura && (
              <div>
                <span className="label">Último consumo</span>
                <span className="value">{account.ultima_factura.consumo}</span>
              </div>
            )}
          </div>

          {account.ultima_factura && (
            <a
              className="btn-secondary"
              href={boletaUrl(tenantSlug, numeroSocio, identificador)}
              target="_blank"
              rel="noreferrer"
            >
              Descargar última boleta (PDF)
            </a>
          )}

          {account.mp_alias && (
            <div className="mp-alias">
              <span className="label">Pagá por Mercado Pago con el alias</span>
              <div className="alias-box">
                <code>{account.mp_alias}</code>
                <button type="button" onClick={() => copyAlias(account.mp_alias!)}>
                  {copied ? "Copiado ✓" : "Copiar"}
                </button>
              </div>
            </div>
          )}

          <h3>Historial</h3>
          <table>
            <thead>
              <tr>
                <th>Período</th>
                <th>Consumo</th>
                <th>Monto</th>
                <th>Vencimiento</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {account.historial.map((inv) => (
                <tr key={`${inv.period_year}-${inv.period_month}`}>
                  <td>
                    {MESES[inv.period_month]} {inv.period_year}
                  </td>
                  <td>{inv.consumo}</td>
                  <td>{money(inv.monto)}</td>
                  <td>{inv.vencimiento ?? "-"}</td>
                  <td>{inv.pagado ? "Pagado" : "Pendiente"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer className="tenant-footer">
        <Link to={`/${tenantSlug}/admin`}>Acceso para la cooperativa</Link>
      </footer>
    </div>
  );
}
