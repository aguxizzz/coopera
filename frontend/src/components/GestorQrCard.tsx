import { useEffect, useState } from "react";
import { Check, Clock, Lock, QrCode } from "lucide-react";
import type { GestorQrStatus } from "../lib/api";

type GestorQrCardProps = {
  qrDataUrl: string | null;
  status: GestorQrStatus | null;
  expiresAt: string | null;
  loading: boolean;
  error: string | null;
  onGenerate: () => void;
  onApprove: () => void;
  onDeny: () => void;
  onCancel: () => void;
};

const STEPS = [
  { title: "Generá el código", desc: "Dura unos minutos y sirve para un solo ingreso." },
  { title: "El gestor lo escanea", desc: "Desde la app de Coopera, con la opción Ingresar con QR." },
  { title: "Confirmás el ingreso", desc: "Antes de dejarlo entrar, confirmás que es esa persona." },
];

function currentStep(status: GestorQrStatus | null): number {
  if (status === "pending") return 1;
  if (status === "claimed") return 2;
  if (status === "approved") return 3;
  return 0;
}

function useSecondsLeft(expiresAt: string | null, active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, expiresAt]);
  if (!expiresAt) return 0;
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - now) / 1000));
}

export default function GestorQrCard({
  qrDataUrl,
  status,
  expiresAt,
  loading,
  error,
  onGenerate,
  onApprove,
  onDeny,
  onCancel,
}: GestorQrCardProps) {
  const waiting = status === "pending";
  const secondsLeft = useSecondsLeft(expiresAt, waiting);
  // The code's total lifetime is only known when it is generated: capture it
  // the first render that sees a new expiresAt so the bar drains from full.
  const [timing, setTiming] = useState({ expiresAt, total: 0 });
  if (timing.expiresAt !== expiresAt) {
    setTiming({ expiresAt, total: expiresAt ? Math.max(1, Math.round((new Date(expiresAt).getTime() - Date.now()) / 1000)) : 0 });
  }
  const totalSeconds = timing.total;

  const pct = totalSeconds ? Math.min(100, (secondsLeft / totalSeconds) * 100) : 0;
  const mm = Math.floor(secondsLeft / 60);
  const ss = String(secondsLeft % 60).padStart(2, "0");
  const step = currentStep(status);
  const idle = !status;

  return (
    <section className="gqr">
      <header className="gqr-head">
        <h2>Ingreso por QR</h2>
        <p>
          Un gestor entra a la app escaneando un código, sin usar la contraseña compartida. Vos
          confirmás el ingreso desde acá.
        </p>
      </header>

      <div className="gqr-body">
        <div className="gqr-stage">
          {idle && (
            <>
              <div className="gqr-empty-icon">
                <QrCode size={44} strokeWidth={1.6} aria-hidden="true" />
              </div>
              <div className="gqr-text">
                <strong>Listo para generar</strong>
                <span>El código expira solo a los pocos minutos y sirve para un solo ingreso.</span>
              </div>
              <button type="button" className="gqr-btn gqr-btn-primary" disabled={loading} onClick={onGenerate}>
                {loading ? "Generando..." : "Generar código QR"}
              </button>
            </>
          )}

          {waiting && qrDataUrl && (
            <>
              <div className="gqr-qr">
                <img src={qrDataUrl} alt="Código QR para ingreso de gestores" />
              </div>
              <div className="gqr-waiting">
                <span className="gqr-pulse" aria-hidden="true" />
                Esperando que el gestor lo escanee…
              </div>
              {expiresAt && (
                <div className="gqr-timer">
                  <div className="gqr-bar">
                    <div className={`gqr-bar-fill${secondsLeft <= 30 ? " is-low" : ""}`} style={{ width: `${pct}%` }} />
                  </div>
                  <div className="gqr-timer-row">
                    <span>Expira en</span>
                    <span className="gqr-mono">
                      {mm}:{ss}
                    </span>
                  </div>
                </div>
              )}
              <div className="gqr-row">
                <button type="button" className="gqr-btn gqr-btn-ghost" disabled={loading} onClick={onGenerate}>
                  Generar otro
                </button>
                <button type="button" className="gqr-btn gqr-btn-quiet" onClick={onCancel}>
                  Cancelar
                </button>
              </div>
            </>
          )}

          {status === "claimed" && (
            <div className="gqr-request">
              <span className="gqr-chip">Código escaneado</span>
              <div className="gqr-text">
                <strong className="gqr-title">Un dispositivo quiere ingresar como gestor</strong>
                <span>Confirmá solo si reconocés a esta persona.</span>
              </div>
              <div className="gqr-actions">
                <button type="button" className="gqr-btn gqr-btn-ghost gqr-btn-reject" disabled={loading} onClick={onDeny}>
                  Rechazar
                </button>
                <button type="button" className="gqr-btn gqr-btn-primary" disabled={loading} onClick={onApprove}>
                  Confirmar ingreso
                </button>
              </div>
            </div>
          )}

          {status === "approved" && (
            <>
              <div className="gqr-badge gqr-badge-ok">
                <Check size={30} strokeWidth={2.4} aria-hidden="true" />
              </div>
              <div className="gqr-text">
                <strong className="gqr-title">Ingreso confirmado</strong>
                <span>El gestor ya puede elegir su perfil en la app. Este código ya no se puede volver a usar.</span>
              </div>
              <button type="button" className="gqr-btn gqr-btn-ghost" disabled={loading} onClick={onGenerate}>
                {loading ? "Generando..." : "Generar otro código"}
              </button>
            </>
          )}

          {(status === "denied" || status === "expired") && (
            <>
              <div className="gqr-badge">
                <Clock size={28} strokeWidth={2} aria-hidden="true" />
              </div>
              <div className="gqr-text">
                <strong className="gqr-title">{status === "denied" ? "Ingreso rechazado" : "El código expiró"}</strong>
                <span>
                  {status === "denied"
                    ? "Nadie ingresó con ese código. Podés generar uno nuevo cuando quieras."
                    : "Pasó el tiempo sin que nadie lo escaneara."}
                </span>
              </div>
              <button type="button" className="gqr-btn gqr-btn-primary" disabled={loading} onClick={onGenerate}>
                {loading ? "Generando..." : "Generar uno nuevo"}
              </button>
            </>
          )}

          {error && <p className="error gqr-error">{error}</p>}
        </div>

        <div className="gqr-side">
          <span className="gqr-eyebrow">Cómo funciona</span>
          <ol className="gqr-steps">
            {STEPS.map((s, i) => {
              const done = i < step;
              const active = i === step;
              return (
                <li key={s.title} className={`gqr-step${active ? " is-active" : ""}${done ? " is-done" : ""}`}>
                  <span className="gqr-step-mark">{done ? <Check size={14} strokeWidth={3} aria-hidden="true" /> : i + 1}</span>
                  <div>
                    <strong>{s.title}</strong>
                    <span>{s.desc}</span>
                  </div>
                </li>
              );
            })}
          </ol>
          <div className="gqr-note">
            <Lock size={16} aria-hidden="true" />
            <span>Cada código es personal: confirmá el ingreso solo si reconocés a quien lo escaneó.</span>
          </div>
        </div>
      </div>
    </section>
  );
}
