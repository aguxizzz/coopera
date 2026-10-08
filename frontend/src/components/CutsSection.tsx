import { useCallback, useEffect, useMemo, useState } from "react";
import { PowerOff } from "lucide-react";
import { ApiError, cancelCut, listCuts, orderCutRestore, type CutEstado, type ServiceCut } from "../lib/api";
import ConfirmDialog from "./ConfirmDialog";
import { TIPO_LABEL } from "./OrderCutDrawer";

export const ESTADO_LABEL: Record<CutEstado, string> = {
  ordenado: "Por ejecutar",
  ejecutado: "Cortado",
  reposicion_ordenada: "Reposición pendiente",
  repuesto: "Repuesto",
  cancelado: "Cancelado",
};

const MOTIVO_LABEL = { impago: "Falta de pago", multa: "Multa", otro: "Otro problema" } as const;

type Filter = "vigentes" | "ordenado" | "ejecutado" | "reposicion_ordenada" | "cerrados";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "vigentes", label: "Vigentes" },
  { key: "ordenado", label: "Por ejecutar" },
  { key: "ejecutado", label: "Cortados" },
  { key: "reposicion_ordenada", label: "Reposición" },
  { key: "cerrados", label: "Cerrados" },
];

function matches(cut: ServiceCut, filter: Filter) {
  const closed = cut.estado === "repuesto" || cut.estado === "cancelado";
  if (filter === "vigentes") return !closed;
  if (filter === "cerrados") return closed;
  return cut.estado === filter;
}

const EMPTY_COPY: Record<Filter, string> = {
  vigentes: "No hay cortes vigentes. Para ordenar uno, abrí Socios y elegí «Ordenar corte».",
  ordenado: "No hay cortes esperando que un gestor los ejecute.",
  ejecutado: "No hay servicios cortados.",
  reposicion_ordenada: "No hay reposiciones pendientes.",
  cerrados: "Todavía no hay cortes cerrados.",
};

function parse(iso: string) {
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
}

function when(iso: string) {
  const d = parse(iso);
  const date = d.toLocaleDateString("es-AR", { day: "numeric", month: "numeric", year: "2-digit" });
  return `${date} · ${d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}`;
}

type Step = {
  key: string;
  label: string;
  who?: string | null;
  at?: string | null;
  nota?: string | null;
  fotos?: string[] | null;
};

// Pasos ya cumplidos del corte, en orden cronológico.
function history(c: ServiceCut): Step[] {
  const steps: Step[] = [{ key: "ordenado", label: "Ordenado", who: c.ordenado_por_email, at: c.created_at }];
  if (c.ejecutado_at) {
    steps.push({
      key: "ejecutado",
      label: "Corte realizado",
      who: c.ejecutado_por_nombre,
      at: c.ejecutado_at,
      nota: c.ejecucion_nota,
      fotos: c.ejecucion_foto_urls,
    });
  }
  if (c.reposicion_ordenada_at && (c.estado === "reposicion_ordenada" || c.estado === "repuesto")) {
    steps.push({
      key: "reposicion_ordenada",
      label: "Reposición ordenada",
      who: c.reposicion_ordenada_por_email,
      at: c.reposicion_ordenada_at,
    });
  }
  if (c.repuesto_at) {
    steps.push({
      key: "repuesto",
      label: "Servicio repuesto",
      who: c.repuesto_por_nombre,
      at: c.repuesto_at,
      nota: c.reposicion_nota,
      fotos: c.reposicion_foto_urls,
    });
  }
  return steps;
}

// Cuántos de los 4 tramos (ordenado → cortado → reposición ordenada → repuesto) lleva el corte.
const PROGRESS_STEPS = 4;

type Props = {
  tenantSlug: string;
  token: string;
  reloadKey: number;
  onChanged: () => void;
  onToast: (message: string) => void;
};

export default function CutsSection({ tenantSlug, token, reloadKey, onChanged, onToast }: Props) {
  const [cuts, setCuts] = useState<ServiceCut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("vigentes");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<{ cut: ServiceCut; action: "cancel" | "restore" } | null>(null);

  const load = useCallback(() => {
    listCuts(tenantSlug, token)
      .then((rows) => {
        setCuts(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "No se pudieron cargar los cortes"))
      .finally(() => setLoading(false));
  }, [tenantSlug, token]);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.key, cuts.filter((c) => matches(c, f.key)).length])) as Record<Filter, number>,
    [cuts],
  );
  const shown = cuts.filter((c) => matches(c, filter));


  async function run() {
    if (!confirm) return;
    const { cut, action } = confirm;
    setBusyId(cut.id);
    setError(null);
    try {
      if (action === "cancel") await cancelCut(tenantSlug, token, cut.id);
      else await orderCutRestore(tenantSlug, token, cut.id);
      onToast(action === "restore" ? "Reposición ordenada" : cut.estado === "ordenado" ? "Corte cancelado" : "Reposición anulada");
      load();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo completar la acción");
    } finally {
      setBusyId(null);
      setConfirm(null);
    }
  }

  const confirmCopy = confirm
    ? confirm.action === "restore"
      ? {
          title: "Ordenar reposición",
          message: `Se le pedirá a los gestores reponer el servicio de ${confirm.cut.nombre_socio} (${confirm.cut.codigo}). Usalo cuando el socio regularizó su situación.`,
          label: "Ordenar reposición",
          danger: false,
        }
      : confirm.cut.estado === "ordenado"
        ? {
            title: "Cancelar orden de corte",
            message: `El corte de ${confirm.cut.nombre_socio} (${confirm.cut.codigo}) dejará de estar pendiente para los gestores.`,
            label: "Cancelar orden",
            danger: true,
          }
        : {
            title: "Anular reposición",
            message: `El servicio de ${confirm.cut.nombre_socio} (${confirm.cut.codigo}) seguirá cortado.`,
            label: "Anular reposición",
            danger: true,
          }
    : null;

  return (
    <section className="card cuts-card" aria-labelledby="cuts-title">
      <header className="cuts-head">
        <h2 id="cuts-title">Cortes de servicio</h2>
        <p>Se ordenan desde la lista de socios. Los gestores los ejecutan en la app con foto y nota como evidencia.</p>
      </header>

      <div className="cuts-tabs" role="group" aria-label="Filtrar cortes">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`cuts-tab${filter === f.key ? " is-active" : ""}`}
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label} <span className="cuts-tab-count">{counts[f.key]}</span>
          </button>
        ))}
      </div>

      <div className="cuts-body">
        {error && (
          <div className="error cuts-error" role="alert">
            <span>{error}</span>
            <button type="button" className="socios-table-link" onClick={load}>
              Reintentar
            </button>
          </div>
        )}

        {loading && (
          <ul className="cut-list" aria-busy="true" aria-label="Cargando cortes">
            {[0, 1, 2].map((i) => (
              <li className="cut-card cut-skeleton" key={i} aria-hidden="true">
                <span />
                <span />
                <span />
              </li>
            ))}
          </ul>
        )}

        {!loading && shown.length === 0 && (
          <div className="cuts-empty">
            <PowerOff size={22} aria-hidden="true" />
            <p>{EMPTY_COPY[filter]}</p>
          </div>
        )}

        {!loading && shown.length > 0 && (
          <ul className="cut-list">
            {shown.map((c) => {
              const steps = history(c);
              const last = steps[steps.length - 1];
              const evidence = steps.filter((s) => s.nota || (s.fotos && s.fotos.length > 0));
              const waiting = c.estado === "ordenado" || c.estado === "reposicion_ordenada";
              const cancelled = c.estado === "cancelado";
              return (
                <li className={`cut-card is-${c.estado}`} key={c.id}>
                  <div className="cut-who">
                    <div className="cut-title">
                      <strong>{c.nombre_socio}</strong>
                      <span className={`cut-pill is-${c.estado}`}>{ESTADO_LABEL[c.estado]}</span>
                    </div>
                    <span className="cut-meta">
                      {MOTIVO_LABEL[c.motivo]}
                      {c.detalle ? `: ${c.detalle}` : ""} · N° {c.numero_socio} · {TIPO_LABEL[c.tipo]} {c.codigo}
                      {c.direccion ? ` · ${c.direccion}` : ""}
                    </span>
                  </div>

                  {(c.estado === "ordenado" || c.estado === "ejecutado" || c.estado === "reposicion_ordenada") && (
                    <div className="cut-action">
                      {c.estado === "ordenado" && (
                        <button type="button" className="cut-action-quiet" disabled={busyId === c.id} onClick={() => setConfirm({ cut: c, action: "cancel" })}>
                          Cancelar orden
                        </button>
                      )}
                      {c.estado === "ejecutado" && (
                        <button type="button" disabled={busyId === c.id} onClick={() => setConfirm({ cut: c, action: "restore" })}>
                          Ordenar reposición
                        </button>
                      )}
                      {c.estado === "reposicion_ordenada" && (
                        <button type="button" className="cut-action-quiet" disabled={busyId === c.id} onClick={() => setConfirm({ cut: c, action: "cancel" })}>
                          Anular reposición
                        </button>
                      )}
                    </div>
                  )}

                  <div className="cut-progress" aria-hidden="true">
                    {Array.from({ length: PROGRESS_STEPS }, (_, i) => (
                      <span key={i} className={i < steps.length ? "is-done" : undefined} />
                    ))}
                  </div>

                  <p className="cut-status">
                    {cancelled ? (
                      <>
                        <strong>Cancelado</strong>
                        {c.cancelado_por_email ? ` · ${c.cancelado_por_email}` : ""}
                        {c.cancelado_at ? ` · ${when(c.cancelado_at)}` : ""}
                      </>
                    ) : (
                      <>
                        <strong>{last.label}</strong>
                        {last.who ? ` · ${last.who}` : ""}
                        {last.at ? ` · ${when(last.at)}` : ""}
                        {waiting ? " · esperando al gestor" : ""}
                      </>
                    )}
                  </p>

                  {evidence.length > 0 && (
                    <div className="cut-evidence">
                      {evidence.map((s) => (
                        <div className="cut-evidence-item" key={s.key}>
                          {evidence.length > 1 && <span className="cut-evidence-label">{s.label}</span>}
                          {s.fotos && s.fotos.length > 0 && (
                            <span className="cut-photos">
                              {s.fotos.map((url, i) => (
                                <a key={url} href={url} target="_blank" rel="noreferrer" title="Abrir foto en tamaño completo">
                                  <img src={url} alt={`Foto ${i + 1} · ${s.label.toLowerCase()}`} loading="lazy" />
                                </a>
                              ))}
                            </span>
                          )}
                          {s.nota && <span className="cut-note">“{s.nota}”</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title={confirmCopy?.title}
        message={confirmCopy?.message ?? ""}
        confirmLabel={confirmCopy?.label}
        danger={confirmCopy?.danger ?? false}
        busy={busyId !== null}
        onConfirm={run}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}
