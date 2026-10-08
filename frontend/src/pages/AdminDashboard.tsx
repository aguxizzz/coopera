import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Search, X } from "lucide-react";
import QRCode from "qrcode";
import {
  ApiError,
  approveGestorQr,
  connectHelipagos,
  connectMacroclick,
  createAdmin,
  deleteAdmin,
  deleteLogo,
  deleteMember,
  deleteMembers,
  denyGestorQr,
  disconnectHelipagos,
  disconnectMacroclick,
  disconnectMp,
  getAdminSettings,
  getAuditLog,
  getCurrentAdmin,
  getGestorQrStatus,
  getHelipagosStatus,
  getMacroclickStatus,
  getMpConnectUrl,
  getMpStatus,
  getPdfImportStatus,
  importPdf,
  importSpreadsheet,
  listAdmins,
  listMemberInvoices,
  listMembers,
  markOldestInvoicePaid,
  setInvoicePagado,
  startGestorQr,
  updateAdminRole,
  updateAdminSettings,
  uploadLogo,
  type AdminRole,
  type AdminUserOut,
  type AuditLogEntry,
  type GestorQrStatus,
  type HelipagosStatus,
  type ImportResult,
  type InvoiceOut,
  type MacroclickStatus,
  type MemberRow,
  type MpStatus,
  type PdfImportJob,
  type TenantSettings,
} from "../lib/api";
import Drawer from "../components/Drawer";
import ConfirmDialog from "../components/ConfirmDialog";
import Toast from "../components/Toast";
import FilePicker from "../components/FilePicker";
import DropZone from "../components/DropZone";
import LogoPlaceholder from "../components/LogoPlaceholder";
import AdminNav, { type AdminSection } from "../components/AdminNav";
import CutsSection, { ESTADO_LABEL } from "../components/CutsSection";
import OrderCutDrawer from "../components/OrderCutDrawer";

const MESES = [
  "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function money(value: number) {
  return value.toLocaleString("es-AR", { style: "currency", currency: "ARS" });
}

function parseAuditDetails(details: string | null): Record<string, string> {
  if (!details) return {};
  const parts = details.includes("|") ? details.split("|") : details.split(",");
  const result: Record<string, string> = {};
  for (const part of parts) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    const key = part.slice(0, eq).trim();
    const value = part.slice(eq + 1).trim();
    if (key) result[key] = value;
  }
  return result;
}

function auditBool(value: string | undefined, whenTrue: string, whenFalse: string) {
  if (value === "True" || value === "true") return whenTrue;
  if (value === "False" || value === "false") return whenFalse;
  return value ?? "";
}

function auditTargetId(target: string | null) {
  if (!target) return "";
  const idx = target.indexOf(":");
  return idx === -1 ? target : `#${target.slice(idx + 1)}`;
}

function formatAuditAction(entry: AuditLogEntry): string {
  const d = parseAuditDetails(entry.details);
  switch (entry.action) {
    case "invoice.pagado_updated": {
      const quien = d.socio ? ` de ${d.socio}` : "";
      const periodo = d.periodo ? ` (período ${d.periodo})` : "";
      return `marcó la factura ${auditTargetId(entry.target)}${quien}${periodo} como ${auditBool(d.pagado, "pagada", "no pagada")}`;
    }
    case "member.deleted":
      return `eliminó al socio ${auditTargetId(entry.target)}`;
    case "member.bulk_deleted":
      return `eliminó ${d.count ?? "varios"} socios`;
    case "settings.updated":
      return `actualizó la configuración (${d.fields ?? entry.details ?? "cambios generales"})`;
    case "mp.connect_url_requested":
      return "solicitó el enlace de conexión de Mercado Pago";
    case "mp.disconnected":
      return "desconectó Mercado Pago";
    case "helipagos.connected":
      return "conectó Helipagos";
    case "helipagos.disconnected":
      return "desconectó Helipagos";
    case "macroclick.connected":
      return "conectó Macro Click de Pago";
    case "macroclick.disconnected":
      return "desconectó Macro Click de Pago";
    case "admin.password_reset":
      return `restableció la contraseña del administrador ${auditTargetId(entry.target)}`;
    case "gestor.created":
      return `creó al gestor ${d.email ?? ""}`;
    case "gestor.shared_password_updated":
      return "actualizó la contraseña compartida de gestores";
    case "gestor.activo_updated":
      return `marcó al gestor ${auditTargetId(entry.target)} como ${auditBool(d.activo, "activo", "inactivo")}`;
    case "meter.created":
      return `creó el medidor ${d.codigo ?? ""}`;
    case "cut.ordered":
      return `ordenó el corte ${auditTargetId(entry.target)}`;
    case "gestor.profile_selected":
      return "ingresó con perfil gestor";
    case "gestor.qr_login_approved":
      return "aprobó un ingreso por QR";
    case "gestor.qr_login_denied":
      return "rechazó un ingreso por QR";
    case "gestor.reading_updated":
      return `actualizó la lectura ${auditTargetId(entry.target)}`;
    case "route.created":
      return "creó una ruta";
    case "route.auto_generated":
      return "generó rutas automáticamente";
    case "route.updated":
      return "modificó una ruta";
    case "route.deleted":
      return "eliminó una ruta";
    case "demo.reset":
      return "reinició la demo";
    case "cut.cancelled":
      return `canceló o retiró la orden del corte ${auditTargetId(entry.target)}`;
    case "cut.restore_ordered":
      return `ordenó la reposición del corte ${auditTargetId(entry.target)}`;
    case "cut.executed":
      return `ejecutó el corte ${auditTargetId(entry.target)}`;
    case "cut.restored":
      return `repuso el servicio del corte ${auditTargetId(entry.target)}`;
    default:
      return `${entry.action.replace(/[._]/g, " ")}${entry.details ? ` (${entry.details})` : ""}`;
  }
}

type AuditFilter = "todo" | "cortes" | "accesos" | "sistema";

const AUDIT_FILTERS: { key: AuditFilter; label: string }[] = [
  { key: "todo", label: "Todo" },
  { key: "cortes", label: "Cortes" },
  { key: "accesos", label: "Accesos" },
  { key: "sistema", label: "Sistema" },
];

function auditCategory(action: string): Exclude<AuditFilter, "todo"> {
  if (action.startsWith("cut.")) return "cortes";
  if (action === "gestor.profile_selected" || action.startsWith("gestor.qr_login")) return "accesos";
  return "sistema";
}

function auditTag(entry: AuditLogEntry): string | null {
  if (entry.action !== "cut.ordered") return null;
  const motivo = /motivo=(.*)$/.exec(entry.details ?? "")?.[1]?.trim();
  return !motivo || motivo === "None" ? "sin motivo" : motivo;
}

function auditTime(iso: string) {
  return new Date(iso).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function auditDayKey(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function auditDayLabel(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const date = d.toLocaleDateString("es-AR", { day: "numeric", month: "short" }).replace(".", "");
  if (auditDayKey(iso) === auditDayKey(today.toISOString())) return `Hoy · ${date}`;
  if (auditDayKey(iso) === auditDayKey(yesterday.toISOString())) return `Ayer · ${date}`;
  return date;
}

type AuditRow = { entry: AuditLogEntry; count: number; since: string };

// Colapsa ingresos repetidos consecutivos (mismo actor y acción) en una sola fila "×N desde HH:MM".
function groupAuditRows(entries: AuditLogEntry[]): { day: string; rows: AuditRow[] }[] {
  const days: { key: string; day: string; rows: AuditRow[] }[] = [];
  for (const entry of entries) {
    const key = auditDayKey(entry.created_at);
    let group = days[days.length - 1];
    if (!group || group.key !== key) {
      group = { key, day: auditDayLabel(entry.created_at), rows: [] };
      days.push(group);
    }
    const prev = group.rows[group.rows.length - 1];
    if (
      prev &&
      auditCategory(entry.action) === "accesos" &&
      prev.entry.action === entry.action &&
      prev.entry.actor_email === entry.actor_email
    ) {
      prev.count += 1;
      prev.since = entry.created_at;
    } else {
      group.rows.push({ entry, count: 1, since: entry.created_at });
    }
  }
  return days;
}

function generatePassword() {
  const chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

type ConfirmState = {
  message: string;
  title?: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
};

const ACCENT_SWATCHES = ["#1d6fa3", "#0f7a6a", "#2f5fe0", "#b4451f", "#5a3fa0"];

export default function AdminDashboard() {
  const { tenantSlug = "" } = useParams();
  const navigate = useNavigate();
  const token = sessionStorage.getItem(`coopera_token_${tenantSlug}`);

  function handleLogout() {
    sessionStorage.removeItem(`coopera_token_${tenantSlug}`);
    navigate(`/${tenantSlug}/admin`);
  }

  const [section, setSection] = useState<AdminSection>("principal");

  const [members, setMembers] = useState<MemberRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sociosQuery, setSociosQuery] = useState("");
  const [sociosFilter, setSociosFilter] = useState<"todos" | "saldo" | "aldia">("todos");
  const [selectMode, setSelectMode] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const [pdfFiles, setPdfFiles] = useState<File[]>([]);
  const [importKind, setImportKind] = useState<"planilla" | "pdf">("planilla");
  const [pdfImporting, setPdfImporting] = useState(false);
  const [pdfImportError, setPdfImportError] = useState<string | null>(null);
  const [pdfJob, setPdfJob] = useState<PdfImportJob | null>(null);

  const [qrCode, setQrCode] = useState<string | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [qrStatus, setQrStatus] = useState<GestorQrStatus | null>(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [qrError, setQrError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [markingPaidId, setMarkingPaidId] = useState<number | null>(null);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  const lastConfirmState = useRef<ConfirmState | null>(null);
  if (confirmState) lastConfirmState.current = confirmState;
  const [toast, setToast] = useState<string | null>(null);

  const [cutMember, setCutMember] = useState<MemberRow | null>(null);
  const [cutDrawerOpen, setCutDrawerOpen] = useState(false);
  const [cutsReloadKey, setCutsReloadKey] = useState(0);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMember, setDrawerMember] = useState<MemberRow | null>(null);
  const [invoices, setInvoices] = useState<InvoiceOut[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);
  const [invoicesError, setInvoicesError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const [settings, setSettings] = useState<TenantSettings | null>(null);
  const [settingsForm, setSettingsForm] = useState({
    contact_email: "",
    contact_phone: "",
    contact_whatsapp: "",
    contact_address: "",
    primary_color: "#2563eb",
  });
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [logoUploading, setLogoUploading] = useState<"primary" | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const [mpStatus, setMpStatus] = useState<MpStatus | null>(null);
  const [mpLoading, setMpLoading] = useState(false);
  const [mpError, setMpError] = useState<string | null>(null);
  const mpResult = searchParams.get("mp");

  const loadMpStatus = useCallback(() => {
    if (!token) return;
    getMpStatus(tenantSlug, token)
      .then(setMpStatus)
      .catch(() => setMpError("No se pudo cargar el estado de Mercado Pago"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadMpStatus();
  }, [loadMpStatus]);

  useEffect(() => {
    if (mpResult) {
      const next = new URLSearchParams(searchParams);
      next.delete("mp");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mpResult]);

  async function handleMpConnect() {
    if (!token) return;
    setMpLoading(true);
    setMpError(null);
    try {
      const { url } = await getMpConnectUrl(tenantSlug, token);
      window.location.href = url;
    } catch (err) {
      setMpError(err instanceof ApiError ? err.message : "No se pudo iniciar la conexión con Mercado Pago");
      setMpLoading(false);
    }
  }

  async function handleMpDisconnect() {
    if (!token) return;
    setMpLoading(true);
    setMpError(null);
    try {
      const status = await disconnectMp(tenantSlug, token);
      setMpStatus(status);
    } catch (err) {
      setMpError(err instanceof ApiError ? err.message : "No se pudo desconectar Mercado Pago");
    } finally {
      setMpLoading(false);
    }
  }

  const [helipagosStatus, setHelipagosStatus] = useState<HelipagosStatus | null>(null);
  const [helipagosLoading, setHelipagosLoading] = useState(false);
  const [helipagosError, setHelipagosError] = useState<string | null>(null);
  const [helipagosForm, setHelipagosForm] = useState({
    token: "",
    webhook_apikey: "",
    environment: "sandbox" as "sandbox" | "production",
  });

  const loadHelipagosStatus = useCallback(() => {
    if (!token) return;
    getHelipagosStatus(tenantSlug, token)
      .then(setHelipagosStatus)
      .catch(() => setHelipagosError("No se pudo cargar el estado de Helipagos"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadHelipagosStatus();
  }, [loadHelipagosStatus]);

  async function handleHelipagosConnect(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setHelipagosLoading(true);
    setHelipagosError(null);
    try {
      const status = await connectHelipagos(tenantSlug, token, helipagosForm);
      setHelipagosStatus(status);
      setHelipagosForm({ token: "", webhook_apikey: "", environment: "sandbox" });
    } catch (err) {
      setHelipagosError(err instanceof ApiError ? err.message : "No se pudo conectar Helipagos");
    } finally {
      setHelipagosLoading(false);
    }
  }

  async function handleHelipagosDisconnect() {
    if (!token) return;
    setHelipagosLoading(true);
    setHelipagosError(null);
    try {
      const status = await disconnectHelipagos(tenantSlug, token);
      setHelipagosStatus(status);
    } catch (err) {
      setHelipagosError(err instanceof ApiError ? err.message : "No se pudo desconectar Helipagos");
    } finally {
      setHelipagosLoading(false);
    }
  }

  // Macro Click de Pago (Banco Macro): integración NO OFICIAL, reconstruida a
  // partir de un plugin de terceros (ver backend/app/services/macroclick.py).
  const [macroclickStatus, setMacroclickStatus] = useState<MacroclickStatus | null>(null);
  const [macroclickLoading, setMacroclickLoading] = useState(false);
  const [macroclickError, setMacroclickError] = useState<string | null>(null);
  const [macroclickForm, setMacroclickForm] = useState({
    comercio_id: "",
    sucursal: "0000000000",
    secret_key: "",
    environment: "sandbox" as "sandbox" | "production",
  });

  const loadMacroclickStatus = useCallback(() => {
    if (!token) return;
    getMacroclickStatus(tenantSlug, token)
      .then(setMacroclickStatus)
      .catch(() => setMacroclickError("No se pudo cargar el estado de Macro Click de Pago"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadMacroclickStatus();
  }, [loadMacroclickStatus]);

  async function handleMacroclickConnect(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setMacroclickLoading(true);
    setMacroclickError(null);
    try {
      const status = await connectMacroclick(tenantSlug, token, macroclickForm);
      setMacroclickStatus(status);
      setMacroclickForm({ comercio_id: "", sucursal: "0000000000", secret_key: "", environment: "sandbox" });
    } catch (err) {
      setMacroclickError(err instanceof ApiError ? err.message : "No se pudo conectar Macro Click de Pago");
    } finally {
      setMacroclickLoading(false);
    }
  }

  async function handleMacroclickDisconnect() {
    if (!token) return;
    setMacroclickLoading(true);
    setMacroclickError(null);
    try {
      const status = await disconnectMacroclick(tenantSlug, token);
      setMacroclickStatus(status);
    } catch (err) {
      setMacroclickError(err instanceof ApiError ? err.message : "No se pudo desconectar Macro Click de Pago");
    } finally {
      setMacroclickLoading(false);
    }
  }

  const [currentAdmin, setCurrentAdmin] = useState<AdminUserOut | null>(null);
  const isOwner = currentAdmin?.role === "owner";

  const [admins, setAdmins] = useState<AdminUserOut[]>([]);
  const [adminsError, setAdminsError] = useState<string | null>(null);
  const [newAdminEmail, setNewAdminEmail] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [newAdminRole, setNewAdminRole] = useState<AdminRole>("staff");
  const [adminsSaving, setAdminsSaving] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [auditFilter, setAuditFilter] = useState<AuditFilter>("todo");

  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);

  const loadAdminsAndAudit = useCallback(() => {
    if (!token) return;
    getCurrentAdmin(tenantSlug, token)
      .then(setCurrentAdmin)
      .catch(() => undefined);
  }, [tenantSlug, token]);

  useEffect(() => {
    loadAdminsAndAudit();
  }, [loadAdminsAndAudit]);

  const loadAdmins = useCallback(() => {
    if (!token || !isOwner) return;
    listAdmins(tenantSlug, token)
      .then(setAdmins)
      .catch(() => setAdminsError("No se pudo cargar la lista de administradores"));
    getAuditLog(tenantSlug, token)
      .then(setAuditLog)
      .catch(() => undefined);
  }, [tenantSlug, token, isOwner]);

  useEffect(() => {
    loadAdmins();
  }, [loadAdmins]);

  async function handleCreateAdmin(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setAdminsSaving(true);
    setAdminsError(null);
    try {
      await createAdmin(tenantSlug, token, {
        email: newAdminEmail,
        password: newAdminPassword,
        role: newAdminRole,
      });
      setNewAdminEmail("");
      setNewAdminPassword("");
      setNewAdminRole("staff");
      setShowInvite(false);
      loadAdmins();
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo crear el administrador");
    } finally {
      setAdminsSaving(false);
    }
  }

  async function handleChangeAdminRole(admin: AdminUserOut, role: AdminRole) {
    if (!token) return;
    setAdminsError(null);
    try {
      await updateAdminRole(tenantSlug, token, admin.id, role);
      loadAdmins();
    } catch (err) {
      setAdminsError(err instanceof ApiError ? err.message : "No se pudo cambiar el rol");
    }
  }

  function handleRemoveAdmin(admin: AdminUserOut) {
    setConfirmState({
      message: `¿Eliminar al administrador ${admin.email}?`,
      onConfirm: async () => {
        if (!token) return;
        setAdminsError(null);
        try {
          await deleteAdmin(tenantSlug, token, admin.id);
          setConfirmState(null);
          loadAdmins();
        } catch (err) {
          setAdminsError(err instanceof ApiError ? err.message : "No se pudo eliminar el administrador");
          setConfirmState(null);
        }
      },
    });
  }

  const loadSettings = useCallback(() => {
    if (!token) return;
    getAdminSettings(tenantSlug, token)
      .then((s) => {
        setSettings(s);
        setSettingsForm({
          contact_email: s.contact_email ?? "",
          contact_phone: s.contact_phone ?? "",
          contact_whatsapp: s.contact_whatsapp ?? "",
          contact_address: s.contact_address ?? "",
          primary_color: s.primary_color,
        });
      })
      .catch(() => setSettingsError("No se pudo cargar la configuración"));
  }, [tenantSlug, token]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSettingsSaving(true);
    setSettingsError(null);
    setSettingsSaved(false);
    try {
      const updated = await updateAdminSettings(tenantSlug, token, settingsForm);
      setSettings(updated);
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch (err) {
      setSettingsError(err instanceof ApiError ? err.message : "No se pudo guardar la configuración");
    } finally {
      setSettingsSaving(false);
    }
  }

  async function handleLogoChange(kind: "primary", file: File | null) {
    if (!token || !file) return;
    setLogoUploading(kind);
    setLogoError(null);
    try {
      const updated = await uploadLogo(tenantSlug, token, kind, file);
      setSettings(updated);
    } catch (err) {
      setLogoError(err instanceof ApiError ? err.message : "No se pudo subir el logo");
    } finally {
      setLogoUploading(null);
    }
  }

  async function handleLogoRemove(kind: "primary") {
    if (!token) return;
    setLogoUploading(kind);
    setLogoError(null);
    try {
      const updated = await deleteLogo(tenantSlug, token, kind);
      setSettings(updated);
    } catch (err) {
      setLogoError(err instanceof ApiError ? err.message : "No se pudo eliminar el logo");
    } finally {
      setLogoUploading(null);
    }
  }

  const refresh = useCallback(() => {
    if (!token) return;
    listMembers(tenantSlug, token)
      .then((rows) => {
        setMembers(rows);
        setSelected(new Set());
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "No se pudo cargar la lista de socios"));
  }, [tenantSlug, token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filteredMembers = useMemo(() => {
    const q = sociosQuery.trim().toLowerCase();
    return members.filter((m) => {
      if (sociosFilter === "saldo" && m.saldo_total <= 0) return false;
      if (sociosFilter === "aldia" && m.saldo_total > 0) return false;
      if (!q) return true;
      return [m.nombre, m.identificador, m.numero_socio].some((field) =>
        field?.toLowerCase().includes(q),
      );
    });
  }, [members, sociosQuery, sociosFilter]);

  const sociosConSaldo = useMemo(() => members.filter((m) => m.saldo_total > 0).length, [members]);

  const stats = useMemo(
    () => ({
      socios: members.length,
      saldo: members.reduce((total, m) => total + m.saldo_total, 0),
    }),
    [members],
  );

  useEffect(() => {
    if (!pdfJob || !token || (pdfJob.status !== "pending" && pdfJob.status !== "running")) return;
    const timer = setInterval(() => {
      getPdfImportStatus(tenantSlug, token, pdfJob.id)
        .then((job) => {
          setPdfJob(job);
          if (job.status === "done") refresh();
        })
        .catch((err) => setPdfImportError(err instanceof ApiError ? err.message : "No se pudo consultar el progreso"));
    }, 1500);
    return () => clearInterval(timer);
  }, [pdfJob, token, tenantSlug, refresh]);

  // Polls while a QR code is live so the admin sees the moment a device
  // scans it (pending -> claimed) without having to refresh.
  useEffect(() => {
    if (!qrCode || !token || (qrStatus !== "pending" && qrStatus !== "claimed")) return;
    const timer = setInterval(() => {
      getGestorQrStatus(tenantSlug, token, qrCode)
        .then((result) => {
          if (result.status === "expired") {
            // El código venció solo: lo reemplazamos por uno nuevo sin que
            // el admin tenga que tocar nada.
            handleGenerateQr();
          } else {
            setQrStatus(result.status);
          }
        })
        .catch(() => {});
    }, 1500);
    return () => clearInterval(timer);
  }, [qrCode, qrStatus, token, tenantSlug]);

  if (!token) {
    return <Navigate to={`/${tenantSlug}/admin`} replace />;
  }

  async function handleImportPdf(e: FormEvent) {
    e.preventDefault();
    if (pdfFiles.length === 0 || !token) return;
    setPdfImporting(true);
    setPdfImportError(null);
    setPdfJob(null);
    try {
      const job = await importPdf(tenantSlug, token, pdfFiles, year, month);
      setPdfJob(job);
    } catch (err) {
      setPdfImportError(err instanceof ApiError ? err.message : "Ocurrió un error al importar");
    } finally {
      setPdfImporting(false);
    }
  }

  async function handleGenerateQr() {
    if (!token) return;
    setQrLoading(true);
    setQrError(null);
    try {
      const { code } = await startGestorQr(tenantSlug, token);
      const qrContent = `coopera-gestor://login?slug=${encodeURIComponent(tenantSlug)}&code=${encodeURIComponent(code)}`;
      const dataUrl = await QRCode.toDataURL(qrContent, { width: 280, margin: 1 });
      setQrCode(code);
      setQrDataUrl(dataUrl);
      setQrStatus("pending");
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : "No se pudo generar el código QR");
    } finally {
      setQrLoading(false);
    }
  }

  async function handleApproveQr() {
    if (!token || !qrCode) return;
    setQrLoading(true);
    setQrError(null);
    try {
      const result = await approveGestorQr(tenantSlug, token, qrCode);
      setQrStatus(result.status);
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : "No se pudo confirmar el dispositivo");
    } finally {
      setQrLoading(false);
    }
  }

  async function handleDenyQr() {
    if (!token || !qrCode) return;
    setQrLoading(true);
    setQrError(null);
    try {
      const result = await denyGestorQr(tenantSlug, token, qrCode);
      setQrStatus(result.status);
    } catch (err) {
      setQrError(err instanceof ApiError ? err.message : "No se pudo rechazar el dispositivo");
    } finally {
      setQrLoading(false);
    }
  }

  function toggleSelected(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    setSelected((prev) => {
      const visibleIds = filteredMembers.map((m) => m.id);
      const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => prev.has(id));
      if (allVisibleSelected) {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      }
      return new Set([...prev, ...visibleIds]);
    });
  }

  function handleMarkOldestPaid(member: MemberRow) {
    setConfirmState({
      title: "Confirmar pago",
      confirmLabel: "Marcar pagada",
      danger: false,
      message: `¿Marcar como pagada la factura impaga más antigua de ${member.nombre}? Si tiene varios períodos adeudados, las demás quedan impagas.`,
      onConfirm: async () => {
        setMarkingPaidId(member.id);
        setConfirmState(null);
        try {
          await markOldestInvoicePaid(tenantSlug, token!, member.id);
          refresh();
          setToast(`Factura de ${member.nombre} marcada como pagada`);
        } catch (err) {
          setDeleteError(
            err instanceof ApiError ? err.message : "No se pudo marcar la factura como pagada",
          );
        } finally {
          setMarkingPaidId(null);
        }
      },
    });
  }

  function handleDeleteOne(member: MemberRow) {
    setConfirmState({
      message: `¿Eliminar a ${member.nombre} y todas sus facturas asociadas?`,
      onConfirm: async () => {
        setDeleteError(null);
        setDeleting(true);
        try {
          await deleteMember(tenantSlug, token!, member.id);
          setConfirmState(null);
          refresh();
        } catch (err) {
          setDeleteError(err instanceof ApiError ? err.message : "No se pudo eliminar el socio");
          setConfirmState(null);
        } finally {
          setDeleting(false);
        }
      },
    });
  }

  function handleDeleteSelected() {
    if (selected.size === 0) return;
    setConfirmState({
      message: `¿Eliminar ${selected.size} socio(s) y sus facturas asociadas?`,
      onConfirm: async () => {
        setDeleteError(null);
        setDeleting(true);
        try {
          await deleteMembers(tenantSlug, token!, Array.from(selected));
          setConfirmState(null);
          refresh();
        } catch (err) {
          setDeleteError(err instanceof ApiError ? err.message : "No se pudieron eliminar los socios seleccionados");
          setConfirmState(null);
        } finally {
          setDeleting(false);
        }
      },
    });
  }

  async function openInvoiceDrawer(member: MemberRow) {
    setDrawerMember(member);
    setDrawerOpen(true);
    setInvoices([]);
    setInvoicesError(null);
    setInvoicesLoading(true);
    try {
      const rows = await listMemberInvoices(tenantSlug, token!, member.id);
      setInvoices(rows);
    } catch (err) {
      setInvoicesError(err instanceof ApiError ? err.message : "No se pudieron cargar las facturas");
    } finally {
      setInvoicesLoading(false);
    }
  }

  function closeInvoiceDrawer() {
    setDrawerOpen(false);
  }

  async function handleTogglePagado(invoice: InvoiceOut) {
    if (!token) return;
    setTogglingId(invoice.id);
    try {
      const updated = await setInvoicePagado(tenantSlug, token, invoice.id, !invoice.pagado);
      setInvoices((prev) => prev.map((inv) => (inv.id === updated.id ? updated : inv)));
      refresh();
    } catch (err) {
      setInvoicesError(err instanceof ApiError ? err.message : "No se pudo actualizar el pago");
    } finally {
      setTogglingId(null);
    }
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

  const yearOptions = Array.from({ length: 6 }, (_, i) => now.getFullYear() - 4 + i);
  const canImport = importKind === "planilla" ? !!file : pdfFiles.length > 0;
  const busy = importKind === "planilla" ? importing : pdfImporting;

  return (
    <div className="admin-panel">
      <aside className="admin-sidebar">
        <div className="admin-sidebar-brand">
          <LogoPlaceholder src={settings?.logo_primary_url} alt={settings?.name} />
          <div className="admin-sidebar-brand-text">
            <span className="admin-sidebar-name">{settings?.name ?? "Cooperativa"}</span>
            <span className="admin-sidebar-sub">Administración</span>
          </div>
        </div>

        <AdminNav variant="sidebar" active={section} onChange={setSection} />

        <div className="admin-sidebar-footer">
          <Link className="admin-sidebar-footer-link" to={`/${tenantSlug}`}>
            Ver portal de socios
          </Link>
          {currentAdmin && <span className="muted admin-sidebar-email">{currentAdmin.email}</span>}
          <button type="button" className="btn-ghost" onClick={handleLogout}>
            Cerrar sesión
          </button>
        </div>
      </aside>

      <div className="admin-content">
        <header className="admin-topbar">
          <div className="admin-topbar-row">
            <div className="admin-topbar-brand">
              <LogoPlaceholder src={settings?.logo_primary_url} alt={settings?.name} />
              <div className="admin-topbar-brand-text">
                <span>{settings?.name ?? "Cooperativa"}</span>
                <span>Administración</span>
              </div>
            </div>
            <button type="button" className="btn-ghost" onClick={handleLogout}>
              Salir
            </button>
          </div>
          <AdminNav variant="tabs" active={section} onChange={setSection} />
        </header>

        <main className="admin-main">
          <div className="admin-main-inner">
          {section === "principal" && (
            <header className="principal-header">
              <div>
                <h1 className="principal-title">Importar período</h1>
                <p className="principal-subtitle">Cargá los consumos o boletas del mes para tus socios.</p>
              </div>
              <div className="admin-stats">
                <div className="admin-stat-card">
                  <span className="admin-stat-label">Socios activos</span>
                  <span className="admin-stat-value">{stats.socios}</span>
                </div>
                <div className="admin-stat-card">
                  <span className="admin-stat-label">Saldo a cobrar</span>
                  <span className="admin-stat-value">{money(stats.saldo)}</span>
                </div>
              </div>
            </header>
          )}

          <div className="settings-panel">
      {section === "config" && (
      <form onSubmit={handleSaveSettings}>
      <div className="card settings-section">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Identidad</h2>
        </div>
        <p className="muted small">
          Logo y color destacado que se muestran en el portal de socios.
        </p>
        </div>
        <div className="settings-section-body">
        <div className="settings-logos">
          <div className="settings-logo-field">
            <div className="settings-logo-row">
              <LogoPlaceholder className="settings-logo-preview" src={settings?.logo_primary_url} />
              <div className="settings-logo-info">
                <span className="settings-logo-label">Logo principal</span>
                <div className="settings-logo-actions">
                  <FilePicker
                    id="logo-primary"
                    file={null}
                    onChange={(f) => handleLogoChange("primary", f)}
                    accept="image/png,image/jpeg,image/webp,image/svg+xml"
                    buttonLabel={logoUploading === "primary" ? "Subiendo..." : "Subir imagen"}
                  />
                  {settings?.logo_primary_url && (
                    <button
                      type="button"
                      className="btn-danger"
                      disabled={logoUploading === "primary"}
                      onClick={() => handleLogoRemove("primary")}
                    >
                      Eliminar
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
        {logoError && <p className="error">{logoError}</p>}

        <div className="settings-form">
          <label>
            Color destacado
            <div className="color-field">
              <input
                type="color"
                value={settingsForm.primary_color}
                onChange={(e) => setSettingsForm((f) => ({ ...f, primary_color: e.target.value }))}
              />
              <input
                type="text"
                value={settingsForm.primary_color}
                onChange={(e) => setSettingsForm((f) => ({ ...f, primary_color: e.target.value }))}
                pattern="^#[0-9a-fA-F]{6}$"
                placeholder="#2563eb"
              />
            </div>
            <div className="color-swatches">
              {ACCENT_SWATCHES.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  aria-label={hex}
                  className={`color-swatch${settingsForm.primary_color.toLowerCase() === hex ? " is-active" : ""}`}
                  style={{ background: hex }}
                  onClick={() => setSettingsForm((f) => ({ ...f, primary_color: hex }))}
                />
              ))}
            </div>
          </label>
          <div className="config-color-preview">
            <span className="muted small">Vista previa en el portal</span>
            <div className="color-preview-box" style={{ ["--accent" as string]: settingsForm.primary_color }}>
              <span>Total a pagar</span>
              <span className="color-preview-amount">{money(12500)}</span>
              <span className="color-preview-btn">Descargar boleta (PDF)</span>
            </div>
          </div>
        </div>
        </div>
      </div>

      <div className="card settings-section">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Contacto</h2>
        </div>
        <p className="muted small">
          Datos de contacto que se muestran en el portal de socios.
        </p>
        </div>
        <div className="settings-section-body">
        <div className="settings-form">
          <label>
            Email de contacto
            <input
              type="email"
              value={settingsForm.contact_email}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_email: e.target.value }))}
              placeholder="contacto@cooperativa.coop"
            />
          </label>
          <label>
            Teléfono
            <input
              value={settingsForm.contact_phone}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_phone: e.target.value }))}
              placeholder="+54 351 555-1234"
            />
          </label>
          <label>
            WhatsApp
            <input
              value={settingsForm.contact_whatsapp}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_whatsapp: e.target.value }))}
              placeholder="+54 9 351 555-1234"
            />
          </label>
          <label className="settings-form-address">
            Dirección
            <input
              value={settingsForm.contact_address}
              onChange={(e) => setSettingsForm((f) => ({ ...f, contact_address: e.target.value }))}
              placeholder="Calle 123, Localidad"
            />
          </label>
          <button type="submit" disabled={settingsSaving}>
            {settingsSaving ? "Guardando..." : "Guardar configuración"}
          </button>
          {settingsSaved && <p className="success">Configuración guardada.</p>}
          {settingsError && <p className="error">{settingsError}</p>}
        </div>
        </div>
      </div>
      </form>
      )}

      {section === "config" && (
      <div className="card settings-section">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Mercado Pago</h2>
        </div>
        <p className="muted small">
          Conectá la cuenta de Mercado Pago de la cooperativa para que los socios puedan pagar sus
          boletas online. El dinero se acredita directamente en tu cuenta de Mercado Pago — Coopera
          nunca lo recibe ni lo retiene.
        </p>
        </div>
        <div className="settings-section-body">
        {mpResult === "success" && <p className="success">Mercado Pago conectado correctamente.</p>}
        {mpResult === "error" && (
          <p className="error">No se pudo completar la conexión con Mercado Pago. Probá de nuevo.</p>
        )}

        {mpStatus && !mpStatus.configured && (
          <p className="muted small">
            Esta instancia de Coopera todavía no tiene configurada la integración con Mercado Pago
            (falta de lado del servidor). Contactá al equipo de Coopera.
          </p>
        )}

        {mpStatus?.configured && !isOwner && (
          <p className="muted small">
            Solo un administrador con rol "owner" puede conectar o desconectar Mercado Pago.
          </p>
        )}

        {mpStatus?.configured && isOwner && (
          <div className="mp-connect">
            {mpStatus.connected ? (
              <>
                <p className="success">
                  Conectado {mpStatus.mp_user_id ? `(cuenta MP #${mpStatus.mp_user_id})` : ""}
                </p>
                <button type="button" className="btn-danger" disabled={mpLoading} onClick={handleMpDisconnect}>
                  {mpLoading ? "Desconectando..." : "Desconectar Mercado Pago"}
                </button>
              </>
            ) : (
              <button type="button" disabled={mpLoading} onClick={handleMpConnect}>
                {mpLoading ? "Redirigiendo..." : "Conectar con Mercado Pago"}
              </button>
            )}
          </div>
        )}
        {mpError && <p className="error">{mpError}</p>}
        </div>
      </div>
      )}

      {section === "config" && (
      <div className="card settings-section">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Helipagos</h2>
        </div>
        <p className="muted small">
          Conectá el token de Helipagos de la cooperativa para que los socios puedan pagar sus
          boletas online (tarjeta, código de barras, QR). A diferencia de Mercado Pago, no hace
          falta autorizar nada: pegá el token y el apikey de webhook que te dio Helipagos al darte
          de alta.
        </p>
        </div>
        <div className="settings-section-body">
        {helipagosStatus && !isOwner && (
          <p className="muted small">
            Solo un administrador con rol "owner" puede conectar o desconectar Helipagos.
          </p>
        )}

        {helipagosStatus?.connected && isOwner && (
          <div className="mp-connect">
            <p className="success">
              Conectado ({helipagosStatus.environment === "production" ? "producción" : "sandbox"})
            </p>
            <button
              type="button"
              className="btn-danger"
              disabled={helipagosLoading}
              onClick={handleHelipagosDisconnect}
            >
              {helipagosLoading ? "Desconectando..." : "Desconectar Helipagos"}
            </button>
          </div>
        )}

        {helipagosStatus && !helipagosStatus.connected && isOwner && (
          <form className="settings-form" onSubmit={handleHelipagosConnect}>
            <label>
              Token
              <input
                value={helipagosForm.token}
                onChange={(e) => setHelipagosForm((f) => ({ ...f, token: e.target.value }))}
                placeholder="Token Bearer provisto por Helipagos"
                required
              />
            </label>
            <label>
              Apikey de webhook
              <input
                value={helipagosForm.webhook_apikey}
                onChange={(e) => setHelipagosForm((f) => ({ ...f, webhook_apikey: e.target.value }))}
                placeholder="Valor del header 'apikey' que envía Helipagos"
                required
              />
            </label>
            <label>
              Entorno
              <select
                value={helipagosForm.environment}
                onChange={(e) =>
                  setHelipagosForm((f) => ({
                    ...f,
                    environment: e.target.value as "sandbox" | "production",
                  }))
                }
              >
                <option value="sandbox">Sandbox (pruebas)</option>
                <option value="production">Producción</option>
              </select>
            </label>
            <button type="submit" disabled={helipagosLoading}>
              {helipagosLoading ? "Conectando..." : "Conectar Helipagos"}
            </button>
          </form>
        )}
        {helipagosError && <p className="error">{helipagosError}</p>}
        </div>
      </div>
      )}

      {section === "config" && (
      <div className="card settings-section">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Macro Click de Pago (no oficial)</h2>
        </div>
        <p className="muted small">
          Conectá las credenciales de Macro Click de Pago (Banco Macro) que te dio tu ejecutivo
          de cuenta: Id de comercio, sucursal y secret key. ⚠️ A diferencia de Mercado Pago y
          Helipagos, esta integración no está basada en documentación oficial del banco — se
          reconstruyó a partir de un plugin de terceros, así que puede haber diferencias con el
          comportamiento real. Probala en sandbox antes de usarla en producción.
        </p>
        </div>
        <div className="settings-section-body">
        {macroclickStatus && !isOwner && (
          <p className="muted small">
            Solo un administrador con rol "owner" puede conectar o desconectar Macro Click de Pago.
          </p>
        )}

        {macroclickStatus?.connected && isOwner && (
          <div className="mp-connect">
            <p className="success">
              Conectado ({macroclickStatus.environment === "production" ? "producción" : "sandbox"})
            </p>
            <button
              type="button"
              className="btn-danger"
              disabled={macroclickLoading}
              onClick={handleMacroclickDisconnect}
            >
              {macroclickLoading ? "Desconectando..." : "Desconectar Macro Click de Pago"}
            </button>
          </div>
        )}

        {macroclickStatus && !macroclickStatus.connected && isOwner && (
          <form className="settings-form" onSubmit={handleMacroclickConnect}>
            <label>
              Id de comercio
              <input
                value={macroclickForm.comercio_id}
                onChange={(e) => setMacroclickForm((f) => ({ ...f, comercio_id: e.target.value }))}
                placeholder="IdComercio provisto por Banco Macro"
                required
              />
            </label>
            <label>
              Sucursal
              <input
                value={macroclickForm.sucursal}
                onChange={(e) => setMacroclickForm((f) => ({ ...f, sucursal: e.target.value }))}
                placeholder="0000000000"
                required
              />
            </label>
            <label>
              Secret key
              <input
                value={macroclickForm.secret_key}
                onChange={(e) => setMacroclickForm((f) => ({ ...f, secret_key: e.target.value }))}
                placeholder="Secret key provista por Banco Macro"
                required
              />
            </label>
            <label>
              Entorno
              <select
                value={macroclickForm.environment}
                onChange={(e) =>
                  setMacroclickForm((f) => ({
                    ...f,
                    environment: e.target.value as "sandbox" | "production",
                  }))
                }
              >
                <option value="sandbox">Sandbox (pruebas)</option>
                <option value="production">Producción</option>
              </select>
            </label>
            <button type="submit" disabled={macroclickLoading}>
              {macroclickLoading ? "Conectando..." : "Conectar Macro Click de Pago"}
            </button>
          </form>
        )}
        {macroclickError && <p className="error">{macroclickError}</p>}
        </div>
      </div>
      )}

      {section === "config" && isOwner && (
      <div className="card settings-section admins-card">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Administradores</h2>
        </div>
        <p className="muted small">Quiénes pueden entrar al panel y qué pueden hacer.</p>
        <dl className="role-legend">
          <div className="role-legend-item">
            <dt>Owner</dt>
            <dd className="muted small">Medios de cobro (Mercado Pago) y gestión del equipo.</dd>
          </div>
          <div className="role-legend-item">
            <dt>Staff</dt>
            <dd className="muted small">Socios, importaciones y boletas.</dd>
          </div>
        </dl>
        </div>
        <div className="settings-section-body">
        <ul className="admin-list">
          {admins.map((a) => {
            const isYou = a.id === currentAdmin?.id;
            return (
              <li key={a.id} className="admin-row">
                <span className="admin-avatar" aria-hidden="true">{a.email.charAt(0).toUpperCase()}</span>
                <div className="admin-id">
                  <span className="admin-email">
                    {a.email}
                    {isYou && <span className="you-badge">Vos</span>}
                  </span>
                  <span className="muted small">{isYou ? "Tu cuenta" : "Activo"}</span>
                </div>
                <div
                  className="role-toggle"
                  role="group"
                  aria-label={`Rol de ${a.email}`}
                  title={isYou ? "No podés modificar tu propio rol" : undefined}
                >
                  {(["owner", "staff"] as AdminRole[]).map((r) => (
                    <button
                      key={r}
                      type="button"
                      className={a.role === r ? "active" : ""}
                      aria-pressed={a.role === r}
                      disabled={isYou}
                      onClick={() => a.role !== r && handleChangeAdminRole(a, r)}
                    >
                      {r === "owner" ? "Owner" : "Staff"}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="admin-remove"
                  disabled={isYou}
                  title={isYou ? "No podés eliminar tu propia cuenta" : undefined}
                  onClick={() => handleRemoveAdmin(a)}
                >
                  Quitar
                </button>
              </li>
            );
          })}
        </ul>

        {!showInvite && (
          <button type="button" className="admin-invite-open" onClick={() => setShowInvite(true)}>
            + Invitar administrador
          </button>
        )}

        {showInvite && (
        <form className="admin-invite" onSubmit={handleCreateAdmin}>
          <div className="admin-invite-head">
            <h3>Nuevo administrador</h3>
            <button type="button" className="link-btn" onClick={() => setShowInvite(false)}>
              Cancelar
            </button>
          </div>
          <div className="admin-invite-fields">
            <label>
              <span className="field-label">Email</span>
              <input
                type="email"
                value={newAdminEmail}
                onChange={(e) => setNewAdminEmail(e.target.value)}
                placeholder="nombre@cooperativa.coop"
                required
              />
            </label>
            <label>
              <span className="field-label field-label-row">
                Contraseña temporal
                <button
                  type="button"
                  className="link-btn link-btn-strong"
                  onClick={() => setNewAdminPassword(generatePassword())}
                >
                  Generar
                </button>
              </span>
              <input
                type="text"
                className="mono"
                value={newAdminPassword}
                onChange={(e) => setNewAdminPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                required
                minLength={8}
              />
            </label>
          </div>
          <div className="field-label">Rol</div>
          <div className="role-options">
            {(
              [
                ["staff", "Staff", "Socios, importaciones y boletas."],
                ["owner", "Owner", "Medios de cobro y gestión del equipo."],
              ] as [AdminRole, string, string][]
            ).map(([value, label, hint]) => (
              <label key={value} className={`role-option${newAdminRole === value ? " selected" : ""}`}>
                <input
                  type="radio"
                  name="new-admin-role"
                  value={value}
                  checked={newAdminRole === value}
                  onChange={() => setNewAdminRole(value)}
                />
                <span className="role-option-radio" aria-hidden="true" />
                <span className="role-option-text">
                  <strong>{label}</strong>
                  <span className="muted small">{hint}</span>
                </span>
              </label>
            ))}
          </div>
          <div className="admin-invite-actions">
            <button type="submit" disabled={adminsSaving || !newAdminEmail || newAdminPassword.length < 8}>
              {adminsSaving ? "Creando..." : "Invitar"}
            </button>
            <span className="muted small">
              Compartí la contraseña por un canal seguro; se pide cambiarla al primer ingreso.
            </span>
          </div>
        </form>
        )}
        {adminsError && <p className="error">{adminsError}</p>}
        </div>
      </div>
      )}

      {section === "config" && isOwner && (
      <div className="card settings-section">
        <div className="settings-section-info">
        <div className="card-head">
          <h2>Actividad reciente</h2>
        </div>
        <p className="muted small">Acciones sensibles realizadas en esta cooperativa.</p>
        <div className="audit-filters" role="group" aria-label="Filtrar actividad">
          {AUDIT_FILTERS.map(({ key, label }) => {
            const count = key === "todo" ? auditLog.length : auditLog.filter((e) => auditCategory(e.action) === key).length;
            return (
              <button
                key={key}
                type="button"
                className={auditFilter === key ? "active" : ""}
                aria-pressed={auditFilter === key}
                onClick={() => setAuditFilter(key)}
              >
                <span>{label}</span>
                <span className="audit-filter-count">{count}</span>
              </button>
            );
          })}
        </div>
        </div>
        <div className="settings-section-body audit-scroll">
        {auditLog.length === 0 && <p className="muted small">Todavía no hay actividad registrada.</p>}
        {auditLog.length > 0 &&
          groupAuditRows(
            auditFilter === "todo" ? auditLog : auditLog.filter((e) => auditCategory(e.action) === auditFilter),
          ).map((group) => (
            <section key={group.day} className="audit-day">
              <h3>{group.day}</h3>
              <ul className="audit-log-list">
                {group.rows.map(({ entry, count, since }) => {
                  const tag = auditTag(entry);
                  return (
                    <li key={entry.id}>
                      <span className="audit-time">{auditTime(entry.created_at)}</span>
                      <span className={`audit-dot audit-dot-${auditCategory(entry.action)}`} aria-hidden="true" />
                      <span className="audit-text">
                        <strong>{entry.actor_email}</strong> {formatAuditAction(entry)}
                        {tag && <span className="audit-tag">{tag}</span>}
                        {count > 1 && <span className="audit-tag">×{count} desde {auditTime(since)}</span>}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      </div>
      )}

      </div>

      {section === "principal" && (
      <form className="import-panel" onSubmit={importKind === "planilla" ? handleImport : handleImportPdf}>
        <section className="import-step">
          <span className="import-step-num">1</span>
          <div className="import-step-body">
            <h2>Período</h2>
            <p className="import-step-desc">Mes al que corresponden los datos.</p>
            <div className="import-period">
              <select value={month} onChange={(e) => setMonth(Number(e.target.value))} aria-label="Mes">
                {MESES.slice(1).map((m, i) => (
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
          </div>
        </section>

        <section className="import-step">
          <span className="import-step-num">2</span>
          <div className="import-step-body">
            <h2>Tipo de archivo</h2>
            <p className="import-step-desc">Elegí cómo vas a cargar la información.</p>
            <div className="import-kinds" role="radiogroup" aria-label="Tipo de archivo">
              {(
                [
                  { key: "planilla", title: "Planilla de consumos", desc: "Un archivo .csv o .xlsx con una fila por socio." },
                  { key: "pdf", title: "Boletas en PDF", desc: "Uno o varios PDF; cada página corresponde a un socio." },
                ] as const
              ).map((opt) => (
                <label key={opt.key} className={`import-kind${importKind === opt.key ? " is-active" : ""}`}>
                  <input
                    type="radio"
                    name="import-kind"
                    checked={importKind === opt.key}
                    onChange={() => setImportKind(opt.key)}
                  />
                  <span className="import-kind-radio" aria-hidden="true" />
                  <span className="import-kind-text">
                    <span className="import-kind-title">{opt.title}</span>
                    <span className="import-kind-desc">{opt.desc}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
        </section>

        <section className="import-step">
          <span className="import-step-num">3</span>
          <div className="import-step-body">
            <h2>Archivo</h2>
            {importKind === "planilla" ? (
              <>
                <p className="import-step-desc">La primera fila debe tener estos encabezados.</p>
                <div className="import-columns">
                  <span className="import-columns-label">Columnas:</span>
                  {["numero_socio", "nombre", "identificador", "consumo", "monto"].map((c) => (
                    <code key={c}>{c}</code>
                  ))}
                  <span className="import-columns-optional">vencimiento (opcional)</span>
                </div>
                <DropZone
                  id="import-file"
                  files={file ? [file] : []}
                  onChange={(files) => setFile(files[0] ?? null)}
                  accept=".csv,.xlsx,.xls"
                  hint=".csv o .xlsx · un archivo"
                />
              </>
            ) : (
              <>
                <p className="import-step-desc">
                  Un PDF por boleta, o uno con varias páginas donde cada página sea un socio.
                </p>
                <DropZone
                  id="import-pdf-files"
                  files={pdfFiles}
                  onChange={setPdfFiles}
                  accept=".pdf"
                  multiple
                  hint=".pdf · uno o varios archivos"
                />
              </>
            )}

            {importKind === "planilla" && importError && <p className="error">{importError}</p>}
            {importKind === "planilla" && importResult && (
              <p className="success">
                Listo: {importResult.rows_processed} filas procesadas ({importResult.members_created} socios nuevos,{" "}
                {importResult.members_updated} actualizados) para {MESES[importResult.period_month]} {importResult.period_year}.
              </p>
            )}
            {importKind === "pdf" && pdfImportError && <p className="error">{pdfImportError}</p>}
            {importKind === "pdf" && pdfJob && (pdfJob.status === "pending" || pdfJob.status === "running") && (
              <p className="muted small">
                Procesando... {pdfJob.processed_pages}/{pdfJob.total_pages} páginas.
              </p>
            )}
            {importKind === "pdf" && pdfJob && pdfJob.status === "done" && (
              <p className="success">
                Listo: {pdfJob.processed_pages} páginas procesadas para {MESES[month]} {year}.
              </p>
            )}
            {importKind === "pdf" && pdfJob && pdfJob.status === "error" && (
              <p className="error">{pdfJob.error ?? "Ocurrió un error al importar"}</p>
            )}
          </div>
        </section>

        <footer className="import-footer">
          <span className="import-footer-hint">
            {canImport ? "Todo listo para importar" : importKind === "planilla" ? "Elegí un archivo para continuar" : "Elegí al menos un PDF para continuar"}
          </span>
          <button type="submit" disabled={!canImport || busy}>
            {busy ? "Importando..." : `Importar ${MESES[month]} ${year}`}
          </button>
        </footer>
      </form>
      )}

      {section === "socios" && (
      <div className="card socios-card">
        <div className="card-head">
          <h2>Socios ({filteredMembers.length}{(sociosQuery || sociosFilter !== "todos") && `/${members.length}`})</h2>
          <button
            type="button"
            className="socios-select-toggle"
            onClick={() => {
              if (selectMode) setSelected(new Set());
              setSelectMode((v) => !v);
            }}
          >
            {selectMode ? "Cancelar" : "Seleccionar"}
          </button>
          <button
            type="button"
            className="btn-danger socios-delete-btn"
            disabled={selected.size === 0 || deleting}
            onClick={handleDeleteSelected}
          >
            Eliminar seleccionados ({selected.size})
          </button>
        </div>
        <div className="socios-search">
          <Search size={16} className="socios-search-icon" aria-hidden="true" />
          <input
            type="search"
            value={sociosQuery}
            onChange={(e) => setSociosQuery(e.target.value)}
            placeholder="Buscar por nombre, N° de socio o DNI/medidor..."
            aria-label="Buscar socios"
          />
          {sociosQuery && (
            <button
              type="button"
              className="socios-search-clear"
              onClick={() => setSociosQuery("")}
              aria-label="Limpiar búsqueda"
            >
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="socios-chips" role="group" aria-label="Filtrar socios">
          {(
            [
              ["todos", "Todos", members.length],
              ["saldo", "Con saldo", sociosConSaldo],
              ["aldia", "Al día", members.length - sociosConSaldo],
            ] as const
          ).map(([key, label, count]) => (
            <button
              key={key}
              type="button"
              className={`socios-chip${sociosFilter === key ? " is-active" : ""}`}
              aria-pressed={sociosFilter === key}
              onClick={() => setSociosFilter(key)}
            >
              {label} <span className="socios-chip-count">{count}</span>
            </button>
          ))}
        </div>
        {loadError && <p className="error">{loadError}</p>}
        {deleteError && <p className="error">{deleteError}</p>}
        {filteredMembers.length === 0 && members.length > 0 && (
          <p className="muted small socios-empty">Ningún socio coincide con la búsqueda.</p>
        )}
        {selectMode && (
          <div className="socios-select-bar">
            <span>{selected.size} seleccionados</span>
            <button type="button" className="socios-table-link" onClick={toggleSelectAll}>
              Seleccionar todos
            </button>
          </div>
        )}
        <table className={`socios-table${selectMode ? " is-selecting" : ""}`}>
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={filteredMembers.length > 0 && filteredMembers.every((m) => selected.has(m.id))}
                  onChange={toggleSelectAll}
                  aria-label="Seleccionar todos"
                />
              </th>
              <th>N° Socio</th>
              <th>Nombre</th>
              <th>DNI / Medidor</th>
              <th>Saldo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filteredMembers.map((m) => (
              <tr key={m.id} onClick={() => openInvoiceDrawer(m)}>
                <td className="socios-table-check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(m.id)}
                    onChange={() => toggleSelected(m.id)}
                    aria-label={`Seleccionar ${m.nombre}`}
                  />
                </td>
                <td data-label="N° Socio" className="socios-table-num">{m.numero_socio}</td>
                <td data-label="Nombre" className="socios-table-name">{m.nombre}</td>
                <td data-label="DNI / Medidor" className="socios-table-id">{m.identificador}</td>
                <td data-label="Saldo" className="socios-table-saldo">
                  <span className={`saldo-pill${m.saldo_total > 0 ? "" : " saldo-pill-ok"}`}>
                    {m.saldo_total > 0 ? money(m.saldo_total) : "Al día"}
                  </span>
                  {m.corte_estado && (
                    <span className={`cut-pill is-${m.corte_estado}`}>{ESTADO_LABEL[m.corte_estado]}</span>
                  )}
                </td>
                <td className="socios-table-actions">
                  <button
                    type="button"
                    className="socios-table-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      setCutMember(m);
                      setCutDrawerOpen(true);
                    }}
                  >
                    Ordenar corte
                  </button>
                  <button type="button" className="socios-table-link" onClick={() => openInvoiceDrawer(m)}>
                    Facturas →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}

      {section === "cortes" && token && (
        <CutsSection
          tenantSlug={tenantSlug}
          token={token}
          reloadKey={cutsReloadKey}
          onChanged={refresh}
          onToast={setToast}
        />
      )}

      {section === "gestores" && (
      <div className="card">
        <div className="card-head">
          <h2>Ingreso por QR</h2>
        </div>
        <p className="muted small">
          En vez de tipear la contraseña compartida de gestores, un gestor puede escanear este
          código desde la app y vos confirmás el ingreso acá. El código expira solo a los pocos
          minutos y sirve una única vez.
        </p>

        {!qrCode && (
          <button type="button" disabled={qrLoading} onClick={handleGenerateQr}>
            {qrLoading ? "Generando..." : "Generar código QR"}
          </button>
        )}

        {qrCode && qrDataUrl && (
          <div className="gestor-qr">
            {(qrStatus === "pending" || qrStatus === "claimed") && (
              <img src={qrDataUrl} alt="Código QR para ingreso de gestores" width={220} height={220} />
            )}

            {qrStatus === "pending" && (
              <p className="muted small">Esperando que un gestor escanee el código...</p>
            )}

            {qrStatus === "claimed" && (
              <div className="gestor-qr-confirm">
                <p>Un dispositivo escaneó el código. ¿Confirmás que es el gestor?</p>
                <div className="gestor-qr-confirm-actions">
                  <button type="button" disabled={qrLoading} onClick={handleApproveQr}>
                    Confirmar
                  </button>
                  <button type="button" className="btn-danger" disabled={qrLoading} onClick={handleDenyQr}>
                    Rechazar
                  </button>
                </div>
              </div>
            )}

            {qrStatus === "approved" && <p className="success">Ingreso confirmado. El gestor ya puede elegir su perfil en la app.</p>}
            {qrStatus === "denied" && <p className="error">Rechazaste este intento de ingreso.</p>}
            {qrStatus === "expired" && <p className="muted small">El código expiró.</p>}

            {(qrStatus === "approved" || qrStatus === "denied" || qrStatus === "expired") && (
              <button type="button" disabled={qrLoading} onClick={handleGenerateQr}>
                {qrLoading ? "Generando..." : "Generar otro código"}
              </button>
            )}
          </div>
        )}

        {qrError && <p className="error">{qrError}</p>}
      </div>
      )}
        </div>
        </main>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={closeInvoiceDrawer}
        title={
          drawerMember ? (
            <div className="drawer-head-info">
              <span className="drawer-head-number">Socio N° {drawerMember.numero_socio}</span>
              <span className="drawer-head-name">{drawerMember.nombre}</span>
              <span className="drawer-head-balance">
                Saldo adeudado: <strong>{money(drawerMember.saldo_total)}</strong>
              </span>
            </div>
          ) : (
            "Facturas"
          )
        }
      >
        {invoicesLoading && <p className="muted small">Cargando facturas...</p>}
        {invoicesError && <p className="error">{invoicesError}</p>}
        {!invoicesLoading && !invoicesError && invoices.length === 0 && (
          <p className="muted small">Este socio no tiene facturas cargadas.</p>
        )}
        {!invoicesLoading && invoices.length > 0 && (
          <div className="invoice-list">
            {invoices.map((inv) => (
              <div className="invoice-item" key={inv.id}>
                <div className="invoice-item-row">
                  <span className="invoice-item-period">
                    {MESES[inv.period_month]} {inv.period_year}
                  </span>
                  <span className={`invoice-status ${inv.pagado ? "is-pagado" : "is-pendiente"}`}>
                    {inv.pagado ? "Pagada" : "Pendiente"}
                  </span>
                </div>
                <div className="invoice-item-amount">
                  <span className="invoice-item-total">{money(inv.monto)}</span>
                  <span className="invoice-item-meta">
                    {inv.consumo} kWh · vence {inv.vencimiento ?? "-"}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={togglingId === inv.id}
                  onClick={() => handleTogglePagado(inv)}
                >
                  {inv.pagado ? "Marcar como pendiente" : "Marcar como pagada"}
                </button>
              </div>
            ))}
          </div>
        )}
      </Drawer>

      {token && (
        <OrderCutDrawer
          open={cutDrawerOpen}
          onClose={() => setCutDrawerOpen(false)}
          tenantSlug={tenantSlug}
          token={token}
          member={cutMember}
          onOrdered={(count) => {
            setToast(count === 1 ? "Corte ordenado" : `${count} cortes ordenados`);
            setCutsReloadKey((k) => k + 1);
            refresh();
          }}
        />
      )}

      <ConfirmDialog
        open={confirmState !== null}
        title={lastConfirmState.current?.title ?? "Confirmar eliminación"}
        message={lastConfirmState.current?.message ?? ""}
        confirmLabel={lastConfirmState.current?.confirmLabel ?? "Eliminar"}
        danger={lastConfirmState.current?.danger ?? true}
        busy={deleting}
        onConfirm={() => lastConfirmState.current?.onConfirm()}
        onCancel={() => setConfirmState(null)}
      />

      <Toast message={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
