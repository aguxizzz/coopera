import { useEffect, useState } from "react";
import {
  ApiError,
  listAdminMeters,
  orderCuts,
  type AdminMeter,
  type CutMotivo,
  type MemberRow,
} from "../lib/api";
import ConfirmDialog from "./ConfirmDialog";
import Drawer from "./Drawer";

export const TIPO_LABEL = { luz: "Luz", agua: "Agua", gas: "Gas" } as const;

const TIPO_UNIT = { luz: "kWh", agua: "m³", gas: "m³" } as const;

const MOTIVOS: { value: CutMotivo; label: string }[] = [
  { value: "impago", label: "Falta de pago" },
  { value: "multa", label: "Multa" },
  { value: "otro", label: "Otro problema" },
];

type Props = {
  open: boolean;
  onClose: () => void;
  tenantSlug: string;
  token: string;
  member: MemberRow | null;
  onOrdered: (count: number) => void;
};

export default function OrderCutDrawer({ open, onClose, tenantSlug, token, member, onOrdered }: Props) {
  const [meters, setMeters] = useState<AdminMeter[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [motivo, setMotivo] = useState<CutMotivo>("impago");
  const [detalle, setDetalle] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const memberId = member?.id;
  useEffect(() => {
    if (!open || memberId === undefined) return;
    setLoading(true);
    setError(null);
    setSelected(new Set());
    setMotivo("impago");
    setDetalle("");
    listAdminMeters(tenantSlug, token)
      .then((rows) => setMeters(rows.filter((m) => m.member_id === memberId && m.activo)))
      .catch((err) => setError(err instanceof ApiError ? err.message : "No se pudieron cargar los medidores"))
      .finally(() => setLoading(false));
  }, [open, memberId, tenantSlug, token]);

  const available = meters.filter((m) => !m.corte_estado);
  const allSelected = available.length > 0 && available.every((m) => selected.has(m.id));

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(available.map((m) => m.id)));
  }

  async function submit() {
    if (!member) return;
    setBusy(true);
    setError(null);
    try {
      const created = await orderCuts(tenantSlug, token, member.id, {
        meter_ids: allSelected ? null : [...selected],
        motivo,
        detalle: detalle.trim() || null,
      });
      setConfirming(false);
      onOrdered(created.length);
      onClose();
    } catch (err) {
      setConfirming(false);
      setError(err instanceof ApiError ? err.message : "No se pudo ordenar el corte");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Drawer
        open={open}
        onClose={onClose}
        title={
          member ? (
            <div className="drawer-head-info">
              <span className="drawer-head-number">Socio N° {member.numero_socio}</span>
              <span className="drawer-head-name">{member.nombre}</span>
              <span className="drawer-head-balance">Ordenar corte de servicio</span>
            </div>
          ) : (
            "Ordenar corte"
          )
        }
      >
        {loading && <p className="muted small">Cargando medidores...</p>}
        {!loading && meters.length === 0 && !error && (
          <p className="muted small">Este socio no tiene medidores activos cargados.</p>
        )}

        {meters.length > 0 && (
          <>
            <div className="cut-meters-head">
              <span className="cut-field-label">Medidores a cortar</span>
              {available.length > 1 && (
                <button type="button" className="socios-table-link" onClick={toggleAll}>
                  {allSelected ? "Quitar todos" : "Seleccionar todos"}
                </button>
              )}
            </div>
            <div className="cut-meter-list">
              {meters.map((m) => {
                const checked = selected.has(m.id);
                return (
                  <label
                    key={m.id}
                    className={`cut-meter tipo-${m.tipo}${checked ? " is-selected" : ""}${m.corte_estado ? " is-disabled" : ""}`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      disabled={!!m.corte_estado}
                      checked={checked}
                      onChange={() => toggle(m.id)}
                    />
                    <span className="cut-check" aria-hidden="true">
                      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 8.5l3.2 3.2L13 4.8" />
                      </svg>
                    </span>
                    <span className="cut-meter-info">
                      <strong className="cut-meter-code">{m.codigo}</strong>
                      <span className="cut-meter-address">{m.direccion ?? "Sin dirección"}</span>
                      {m.corte_estado && <span className="cut-pill is-ordenado">Ya tiene corte vigente</span>}
                    </span>
                    <span className="cut-strip" aria-hidden="true">
                      <span className="cut-strip-label">{TIPO_LABEL[m.tipo].toUpperCase()}</span>
                      <span className="cut-strip-rule" />
                      <span className="cut-strip-unit">{TIPO_UNIT[m.tipo]}</span>
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="cut-field" role="radiogroup" aria-label="Motivo">
              <span className="cut-field-label">Motivo</span>
              <div className="cut-motivos">
                {MOTIVOS.map((o) => (
                  <label key={o.value} className={`cut-motivo${motivo === o.value ? " is-selected" : ""}`}>
                    <input
                      type="radio"
                      className="sr-only"
                      name="cut-motivo"
                      checked={motivo === o.value}
                      onChange={() => setMotivo(o.value)}
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </div>

            <label className="cut-field" htmlFor="cut-detalle">
              <span className="cut-field-label">Detalle (opcional)</span>
              <input
                id="cut-detalle"
                type="text"
                maxLength={500}
                value={detalle}
                onChange={(e) => setDetalle(e.target.value)}
                placeholder="Ej: 3 facturas impagas, intimación del 02/10"
              />
            </label>

            {error && <p className="error">{error}</p>}

            <button
              type="button"
              className="btn-danger cut-submit"
              disabled={selected.size === 0 || busy}
              onClick={() => setConfirming(true)}
            >
              Ordenar corte{selected.size > 0 ? ` (${selected.size})` : ""}
            </button>
          </>
        )}
        {meters.length === 0 && error && <p className="error">{error}</p>}
      </Drawer>

      <ConfirmDialog
        open={confirming}
        title="Ordenar corte de servicio"
        message={`Se ordenará el corte de ${selected.size} medidor(es) de ${member?.nombre ?? "este socio"}. Los gestores recibirán la orden en la app.`}
        confirmLabel="Ordenar corte"
        danger
        busy={busy}
        onConfirm={submit}
        onCancel={() => setConfirming(false)}
      />
    </>
  );
}
