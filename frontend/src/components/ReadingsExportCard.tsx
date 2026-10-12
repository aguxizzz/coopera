import { useEffect, useState } from "react";
import {
  ApiError,
  exportReadings,
  getReadingsExportSummary,
  type ReadingsExportFormat,
  type ReadingsExportSummary,
} from "../lib/api";

const MESES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

type ReadingsExportCardProps = {
  tenantSlug: string;
  token: string;
  // Changes when the padrón does, so the count is fetched again.
  refreshKey?: number;
};

// Lets a cooperativa that bills in its own system take the month's readings
// with it: one row per meter, as loaded by the gestores from the app.
export default function ReadingsExportCard({ tenantSlug, token, refreshKey }: ReadingsExportCardProps) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [downloading, setDownloading] = useState<ReadingsExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<ReadingsExportSummary | null>(null);
  const yearOptions = Array.from({ length: 6 }, (_, i) => now.getFullYear() - 5 + i);

  useEffect(() => {
    let cancelled = false;
    setSummary(null);
    getReadingsExportSummary(tenantSlug, token, year, month)
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      // The count is a heads-up, not a requirement: without it the download still works.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [tenantSlug, token, year, month, refreshKey]);

  async function handleDownload(formato: ReadingsExportFormat) {
    setDownloading(formato);
    setError(null);
    try {
      const blob = await exportReadings(tenantSlug, token, year, month, formato);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `lecturas-${tenantSlug}-${year}-${String(month).padStart(2, "0")}.${formato}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo descargar la planilla");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="card readings-export">
      <h2>Exportar lecturas</h2>
      <p className="muted">
        Descargá las lecturas que cargaron los gestores en el mes, una fila por medidor, para llevarlas a tu
        sistema de facturación. Solo cuenta lo que los gestores ya sincronizaron desde la app.
      </p>
      <div className="import-period">
        <select value={month} onChange={(e) => setMonth(Number(e.target.value))} aria-label="Mes">
          {MESES.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </select>
        <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Año">
          {yearOptions.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
      {summary && summary.total === 0 && (
        <p className="readings-export-summary">No hay medidores cargados para ese mes.</p>
      )}
      {summary && summary.total > 0 && (
        <p className={`readings-export-summary${summary.sin_leer > 0 ? " is-incomplete" : " is-complete"}`}>
          <strong>
            {summary.leidos} de {summary.total} medidores leídos.
          </strong>{" "}
          {summary.sin_leer > 0
            ? `${summary.sin_leer === 1 ? "Falta 1, que sale" : `Faltan ${summary.sin_leer}, que salen`} en la planilla con la lectura vacía.`
            : "La planilla sale completa."}
        </p>
      )}
      <div className="readings-export-actions">
        <button type="button" disabled={downloading !== null} onClick={() => handleDownload("xlsx")}>
          {downloading === "xlsx" ? "Descargando..." : "Descargar Excel"}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={downloading !== null}
          onClick={() => handleDownload("csv")}
        >
          {downloading === "csv" ? "Descargando..." : "Descargar CSV"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
