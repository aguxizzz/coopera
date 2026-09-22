import { Link } from "react-router-dom";

const DEMO_TENANTS = [
  { slug: "rio-seco", name: "Cooperativa Eléctrica Río Seco" },
  { slug: "valle-verde", name: "Cooperativa de Servicios Valle Verde" },
];

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-hero">
        <h1>Coopero</h1>
        <p>
          La plataforma para que cooperativas de servicios gestionen socios, consumos y cobros
          en un solo lugar — y para que cada socio vea cuánto debe y pague en segundos.
        </p>
      </header>

      <section className="landing-demo">
        <h2>Prototipo — cooperativas de prueba</h2>
        <p className="muted">
          En producción cada cooperativa tiene su propio dominio (ej. rioseco.coop). Acá, para
          la demo, entrás por ruta:
        </p>
        <div className="tenant-grid">
          {DEMO_TENANTS.map((t) => (
            <div key={t.slug} className="tenant-card">
              <h3>{t.name}</h3>
              <div className="tenant-card-links">
                <Link to={`/${t.slug}`}>Portal del socio</Link>
                <Link to={`/${t.slug}/admin`}>Panel admin</Link>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-how">
        <h2>Cómo funciona</h2>
        <ol>
          <li>La cooperativa sube una planilla mensual con consumo y monto por socio.</li>
          <li>El sistema actualiza automáticamente el saldo de cada socio.</li>
          <li>El socio ingresa con su número de socio y DNI/medidor, ve cuánto debe y descarga su boleta.</li>
          <li>Copia el alias de Mercado Pago de su cooperativa y paga (el pago integrado queda para una próxima etapa).</li>
        </ol>
      </section>
    </div>
  );
}
