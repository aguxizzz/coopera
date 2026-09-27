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
import LogoPlaceholder from "../components/LogoPlaceholder";

const MESES = [
  "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function money(value: number) {
  return value.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
}

function moneyParts(value: number) {
  const formatted = money(value);
  const commaIndex = formatted.lastIndexOf(",");
  if (commaIndex === -1) return { main: formatted, cents: "" };
  return { main: formatted.slice(0, commaIndex), cents: formatted.slice(commaIndex) };
}

function CopyButton({ copied, onClick }: { copied: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className={`copy-btn${copied ? " is-copied" : ""}`}
      onClick={onClick}
      aria-live="polite"
    >
      <span className="copy-btn-icon">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="icon-copy">
          <path
            d="M9 9h10v10H9zM6 15H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v2"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="icon-check">
          <path
            d="m5 13 4 4L19 7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="copy-btn-label">{copied ? "Copiado" : "Copiar"}</span>
    </button>
  );
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
  const [copiedField, setCopiedField] = useState<"alias" | "cbu" | null>(null);

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

  function copyValue(field: "alias" | "cbu", value: string) {
    navigator.clipboard.writeText(value).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField((current) => (current === field ? null : current)), 1600);
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

  const accent = tenant?.primary_color ?? "#2f5fe0";

  if (!account) {
    return (
      <div className="tenant-search-view" style={{ ["--accent" as string]: accent }}>
        <div className="login-card">
          <header className="tenant-header-centered">
            <LogoPlaceholder className="tenant-logo-centered" src={tenant?.logo_primary_url} alt={tenant?.name} />
            <h1>{tenant?.name ?? "Cargando..."}</h1>
          </header>

          <form className="lookup-form" onSubmit={handleSubmit}>
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
              {loading ? "Buscando..." : "Iniciar sesión"}
            </button>
            {error && <p className="error">{error}</p>}
          </form>

          <footer className="tenant-footer-centered">
            <Link to={`/${tenantSlug}/admin`}>acceso administrador</Link>
          </footer>
        </div>
      </div>
    );
  }

  const importe = account.ultima_factura ? moneyParts(account.ultima_factura.monto) : null;

  return (
    <div className="tenant-portal-v2" style={{ ["--accent" as string]: accent }}>
      <div className="portal-hero">
        <div className="portal-hero-top">
          <span className="portal-hero-brand">{tenant?.name ?? "Cargando..."}</span>
        </div>

        <div className="portal-hero-greeting">
          <h1>
            Hola
            <br />
            {account.nombre}!
          </h1>
          <p>
            Bienvenido/a a {tenant?.name ?? "tu cooperativa"}. Acá vas a poder consultar tus
            consumos y tu última factura.
          </p>
        </div>

        <div className="portal-summary-card">
          <div className="portal-summary-block">
            <span className="portal-summary-label">Socio número</span>
            <span className="portal-summary-sub">{account.numero_socio}</span>
          </div>

          {account.ultima_factura && importe && (
            <div className="portal-summary-block">
              <span className="portal-summary-label">
                Tu importe de {MESES[account.ultima_factura.period_month]}
              </span>
              <span className="portal-summary-value">
                {importe.main}
                <span className="portal-summary-cents">{importe.cents}</span>
              </span>
            </div>
          )}

          <div className="portal-summary-footnote">
            Saldo total adeudado: <strong>{money(account.saldo_total)}</strong>
          </div>
        </div>
      </div>

      <div className="portal-body">
        {account.ultima_factura && (
          <div className="card portal-download-card">
            <h3>Tu factura, siempre a mano</h3>
            <p className="muted">Accedé de forma rápida y sencilla a tu boleta del mes.</p>
            <a
              className="portal-download-box"
              href={boletaUrl(tenantSlug, numeroSocio, identificador)}
              target="_blank"
              rel="noreferrer"
              aria-label="Descargar última boleta en PDF"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5M4 18v1.5A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5V18"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>Descargar boleta (PDF)</span>
            </a>
          </div>
        )}

        {account.mp_alias && (
          <div className="card portal-pay-card">
            <div className="pay-card-head">
              <div>
                <h3>Pagá con Mercado Pago</h3>
                <p className="muted">Transferí directamente a la cuenta de la cooperativa.</p>
              </div>
            </div>

            <div className="pay-fields">
              <div className="pay-field">
                <span className="pay-field-label">Alias</span>
                <div className="pay-field-value">
                  <code>{account.mp_alias}</code>
                  <CopyButton
                    copied={copiedField === "alias"}
                    onClick={() => copyValue("alias", account.mp_alias!)}
                  />
                </div>
              </div>

              {account.mp_cbu && (
                <div className="pay-field">
                  <span className="pay-field-label">CBU</span>
                  <div className="pay-field-value">
                    <code>{account.mp_cbu}</code>
                    <CopyButton
                      copied={copiedField === "cbu"}
                      onClick={() => copyValue("cbu", account.mp_cbu!)}
                    />
                  </div>
                </div>
              )}
            </div>

            {account.mp_titular && (
              <div className="pay-owner">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>
                  A nombre de <strong>{account.mp_titular}</strong>. Verificá el titular antes de transferir.
                </span>
              </div>
            )}
          </div>
        )}

        <div className="card">
          <h3>Historial</h3>
          <table className="historial-table">
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
                  <td data-label="Período">
                    {MESES[inv.period_month]} {inv.period_year}
                  </td>
                  <td data-label="Consumo">{inv.consumo}</td>
                  <td data-label="Monto">{money(inv.monto)}</td>
                  <td data-label="Vencimiento">{inv.vencimiento ?? "-"}</td>
                  <td data-label="Estado">
                    <span className={`invoice-status ${inv.pagado ? "is-pagado" : "is-pendiente"}`}>
                      {inv.pagado ? "Pagado" : "Pendiente"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {(tenant?.contact_email || tenant?.contact_phone || tenant?.contact_whatsapp || tenant?.contact_address) && (
          <div className="card portal-contact-card">
            <h3>Contacto</h3>
            <ul className="contact-list">
              {tenant.contact_address && <li>{tenant.contact_address}</li>}
              {tenant.contact_phone && <li>Tel: {tenant.contact_phone}</li>}
              {tenant.contact_whatsapp && <li>WhatsApp: {tenant.contact_whatsapp}</li>}
              {tenant.contact_email && (
                <li>
                  <a href={`mailto:${tenant.contact_email}`}>{tenant.contact_email}</a>
                </li>
              )}
            </ul>
          </div>
        )}

        <footer className="tenant-footer tenant-footer-centered">
          {tenant?.logo_secondary_url && (
            <img className="tenant-footer-secondary-logo" src={tenant.logo_secondary_url} alt="" />
          )}
          <Link to={`/${tenantSlug}/admin`}>Acceso para la cooperativa</Link>
        </footer>
      </div>
    </div>
  );
}
