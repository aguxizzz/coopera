import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate, useParams } from "react-router-dom";
import { ApiError, importSpreadsheet, listMembers, type ImportResult, type MemberRow } from "../lib/api";

const MESES = [
  "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function money(value: number) {
  return value.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
}

export default function AdminDashboard() {
  const { tenantSlug = "" } = useParams();
  const token = sessionStorage.getItem(`coopero_token_${tenantSlug}`);

  const [members, setMembers] = useState<MemberRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const refresh = useCallback(() => {
    if (!token) return;
    listMembers(tenantSlug, token)
      .then(setMembers)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "No se pudo cargar la lista de socios"));
  }, [tenantSlug, token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!token) {
    return <Navigate to={`/${tenantSlug}/admin`} replace />;
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

  return (
    <div className="admin-dashboard">
      <header className="tenant-header">
        <h1>Panel de administración</h1>
        <p className="muted">Subí la planilla mensual para actualizar el consumo y la deuda de tus socios.</p>
      </header>

      <div className="card">
        <h2>Importar planilla del período</h2>
        <p className="muted small">
          Columnas requeridas: <code>numero_socio</code>, <code>nombre</code>, <code>identificador</code>,{" "}
          <code>consumo</code>, <code>monto</code>. Opcional: <code>vencimiento</code>. Formato .csv o .xlsx.
        </p>
        <form className="import-form" onSubmit={handleImport}>
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
          <label className="file-label">
            Planilla
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
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

      <div className="card">
        <h2>Socios ({members.length})</h2>
        {loadError && <p className="error">{loadError}</p>}
        <table>
          <thead>
            <tr>
              <th>N° Socio</th>
              <th>Nombre</th>
              <th>DNI / Medidor</th>
              <th>Saldo</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.numero_socio}>
                <td>{m.numero_socio}</td>
                <td>{m.nombre}</td>
                <td>{m.identificador}</td>
                <td>{money(m.saldo_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
