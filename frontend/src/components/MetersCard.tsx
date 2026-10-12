import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  createAdminMeter,
  importMeters,
  listAdminMeters,
  resolveMeterSinUso,
  type AdminMeter,
  type MemberRow,
  type MeterImportResult,
} from "../lib/api";
import Drawer from "./Drawer";
import DropZone from "./DropZone";
import { TIPO_LABEL } from "./OrderCutDrawer";

const COLUMNS = ["numero_socio", "nombre", "medidor"];
const OPTIONAL_COLUMNS = ["tipo", "direccion", "unidad", "lectura_inicial", "identificador", "adicional"];

type MetersCardProps = {
  tenantSlug: string;
  token: string;
  members: MemberRow[];
  // The padrón changed (meters, and maybe socios, were created).
  onChanged: () => void;
  onToast: (message: string) => void;
};

// The meters the gestores read. Importing socios already gives each one a
// meter per measured service, so the padrón is optional: it loads the real
// meter numbers in bulk. One by one is for a new connection, and for the
// exception of a second meter of the same service.
export default function MetersCard({ tenantSlug, token, members, onChanged, onToast }: MetersCardProps) {
  const [meters, setMeters] = useState<AdminMeter[] | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [resolving, setResolving] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [result, setResult] = useState<MeterImportResult | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [numeroSocio, setNumeroSocio] = useState("");
  const [nombre, setNombre] = useState("");
  const [codigo, setCodigo] = useState("");
  const [tipo, setTipo] = useState<AdminMeter["tipo"]>("luz");
  const [direccion, setDireccion] = useState("");
  const [lecturaInicial, setLecturaInicial] = useState("");
  const [adicional, setAdicional] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAdminMeters(tenantSlug, token)
      .then((rows) => {
        if (!cancelled) setMeters(rows);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [tenantSlug, token, reloadKey]);

  const count = meters?.length ?? null;
  // Meters a gestor reported as "el socio no usa este servicio", still
  // waiting for the office to decide.
  const sinUso = useMemo(() => (meters ?? []).filter((m) => m.activo && m.sin_uso_reportado_at), [meters]);

  async function handleSinUso(meter: AdminMeter, baja: boolean) {
    setResolving(meter.id);
    try {
      const updated = await resolveMeterSinUso(tenantSlug, token, meter.id, baja);
      setMeters((prev) => prev?.map((m) => (m.id === updated.id ? updated : m)) ?? prev);
      onToast(baja ? `Medidor ${meter.codigo} dado de baja` : `Aviso del medidor ${meter.codigo} descartado`);
      if (baja) onChanged();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : "No se pudo resolver el aviso");
    } finally {
      setResolving(null);
    }
  }

  const existingMember = useMemo(
    () => members.find((m) => m.numero_socio === numeroSocio.trim()) ?? null,
    [members, numeroSocio],
  );

  async function handleImport(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setImporting(true);
    setImportError(null);
    setResult(null);
    try {
      const data = await importMeters(tenantSlug, token, file);
      setResult(data);
      setFile(null);
      setReloadKey((k) => k + 1);
      onChanged();
    } catch (err) {
      setImportError(err instanceof ApiError ? err.message : "Ocurrió un error al importar");
    } finally {
      setImporting(false);
    }
  }

  function openForm() {
    setNumeroSocio("");
    setNombre("");
    setCodigo("");
    setTipo("luz");
    setDireccion("");
    setLecturaInicial("");
    setAdicional(false);
    setFormError(null);
    setFormOpen(true);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const lectura = lecturaInicial.trim() ? Number(lecturaInicial.replace(",", ".")) : null;
    if (lectura !== null && (Number.isNaN(lectura) || lectura < 0)) {
      setFormError("La lectura inicial tiene que ser un número");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const meter = await createAdminMeter(tenantSlug, token, {
        numero_socio: numeroSocio.trim(),
        nombre: existingMember ? null : nombre.trim(),
        codigo: codigo.trim(),
        tipo,
        direccion: direccion.trim() || null,
        lectura_inicial: lectura,
        adicional,
      });
      setFormOpen(false);
      setReloadKey((k) => k + 1);
      onToast(`Medidor ${meter.codigo} agregado`);
      onChanged();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "No se pudo agregar el medidor");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card meters-card">
      <div className="card-head">
        <h2>Medidores</h2>
        <button type="button" className="btn-secondary" onClick={openForm}>
          Agregar medidor
        </button>
      </div>
      <p className="muted">
        {count === null
          ? "Los medidores son lo que los gestores ven en la app."
          : count === 0
            ? "Todavía no hay medidores cargados: los gestores no van a ver nada en la app. Se crean solos al importar los socios; el padrón es opcional."
            : `${count} ${count === 1 ? "medidor cargado" : "medidores cargados"}. Es lo que los gestores ven en la app.`}
      </p>

      {sinUso.length > 0 && (
        <div className="meters-sin-uso" role="status">
          <strong>
            {sinUso.length === 1
              ? "Un gestor informó que un socio no usa el servicio."
              : `Los gestores informaron ${sinUso.length} socios que no usan el servicio.`}
          </strong>
          <p className="muted small">
            Dar de baja saca el medidor de la app, las rutas y la exportación. Si fue un error, descartá el aviso.
          </p>
          <ul>
            {sinUso.map((m) => (
              <li key={m.id}>
                <span>
                  <strong>
                    {m.numero_socio} · {m.nombre_socio}
                  </strong>{" "}
                  <span className="muted small">
                    {TIPO_LABEL[m.tipo]} · medidor {m.codigo}
                    {m.sin_uso_reportado_por ? ` · informó ${m.sin_uso_reportado_por}` : ""}
                  </span>
                </span>
                <span className="meters-sin-uso-actions">
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={resolving === m.id}
                    onClick={() => handleSinUso(m, false)}
                  >
                    Descartar
                  </button>
                  <button type="button" disabled={resolving === m.id} onClick={() => handleSinUso(m, true)}>
                    Dar de baja
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <form className="meters-import" onSubmit={handleImport}>
        <h3>Importar padrón (opcional)</h3>
        <p className="muted small">
          Cada socio importado ya tiene su medidor, con un número provisorio. El padrón sirve para cargar los números
          reales: una fila por medidor, y podés volver a subirlo cuando quieras (los que ya están se actualizan y los
          nuevos se agregan).
        </p>
        <div className="import-columns">
          <span className="import-columns-label">Columnas:</span>
          {COLUMNS.map((c) => (
            <code key={c}>{c}</code>
          ))}
          <span className="import-columns-optional">{OPTIONAL_COLUMNS.join(", ")} (opcionales)</span>
        </div>
        <DropZone
          id="meters-file"
          files={file ? [file] : []}
          onChange={(files) => setFile(files[0] ?? null)}
          accept=".csv,.xlsx,.xls"
          hint=".csv o .xlsx · un archivo"
        />
        <p className="muted small">
          <code>lectura_inicial</code> es lo que marca el medidor hoy: con ese dato la primera lectura del gestor ya
          calcula el consumo. <code>adicional</code> con «si» carga un segundo medidor del mismo servicio para un socio
          que ya tiene uno (otra propiedad).
        </p>
        <button type="submit" disabled={!file || importing}>
          {importing ? "Importando..." : "Importar padrón"}
        </button>
        {importError && <p className="error">{importError}</p>}
        {result && (
          <p className="success">
            Listo: {result.meters_created} medidores nuevos y {result.meters_updated} actualizados
            {result.members_created > 0 ? `, ${result.members_created} socios nuevos` : ""}.
          </p>
        )}
        {result && result.errors.length > 0 && (
          <div className="meters-import-errors" role="alert">
            <strong>
              {result.errors.length === 1
                ? "1 fila no se cargó."
                : `${result.errors.length} filas no se cargaron.`}{" "}
              Corregilas y volvé a subir la planilla.
            </strong>
            <ul>
              {result.errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </div>
        )}
      </form>

      <Drawer open={formOpen} onClose={() => setFormOpen(false)} title="Agregar medidor">
        <form className="meters-form" onSubmit={handleCreate}>
          <label className="cut-field" htmlFor="meter-socio">
            <span className="cut-field-label">Número de socio</span>
            <input id="meter-socio" value={numeroSocio} onChange={(e) => setNumeroSocio(e.target.value)} required />
            {existingMember && <span className="muted small">{existingMember.nombre}</span>}
          </label>
          {!existingMember && (
            <label className="cut-field" htmlFor="meter-nombre">
              <span className="cut-field-label">Nombre del socio</span>
              <input id="meter-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
              <span className="muted small">Ese número todavía no existe: se crea el socio con este nombre.</span>
            </label>
          )}
          <label className="cut-field" htmlFor="meter-codigo">
            <span className="cut-field-label">Número de medidor</span>
            <input id="meter-codigo" value={codigo} onChange={(e) => setCodigo(e.target.value)} required />
          </label>
          <label className="cut-field" htmlFor="meter-tipo">
            <span className="cut-field-label">Servicio</span>
            <select id="meter-tipo" value={tipo} onChange={(e) => setTipo(e.target.value as AdminMeter["tipo"])}>
              {(Object.keys(TIPO_LABEL) as AdminMeter["tipo"][]).map((t) => (
                <option key={t} value={t}>
                  {TIPO_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
          <label className="cut-field" htmlFor="meter-direccion">
            <span className="cut-field-label">Dirección (opcional)</span>
            <input id="meter-direccion" value={direccion} onChange={(e) => setDireccion(e.target.value)} />
          </label>
          <label className="cut-field" htmlFor="meter-lectura">
            <span className="cut-field-label">Lectura inicial (opcional)</span>
            <input
              id="meter-lectura"
              inputMode="decimal"
              value={lecturaInicial}
              onChange={(e) => setLecturaInicial(e.target.value)}
            />
            <span className="muted small">Lo que marca el medidor hoy.</span>
          </label>
          <label className="meters-check" htmlFor="meter-adicional">
            <input
              id="meter-adicional"
              type="checkbox"
              checked={adicional}
              onChange={(e) => setAdicional(e.target.checked)}
            />
            <span>
              Es un medidor adicional
              <span className="muted small">
                {" "}
                El socio ya tiene uno de este servicio y este es de otra propiedad.
              </span>
            </span>
          </label>
          {formError && <p className="error">{formError}</p>}
          <button type="submit" className="cut-submit" disabled={saving}>
            {saving ? "Guardando..." : "Agregar medidor"}
          </button>
        </form>
      </Drawer>
    </div>
  );
}
