const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail ?? "Ocurrió un error");
  }
  return res.json();
}

export interface TenantPublic {
  slug: string;
  name: string;
  primary_color: string;
  contact_email: string | null;
  contact_phone: string | null;
  contact_whatsapp: string | null;
  contact_address: string | null;
  logo_primary_url: string | null;
}

export type TenantSettings = TenantPublic;

export interface TenantSettingsUpdate {
  contact_email?: string | null;
  contact_phone?: string | null;
  contact_whatsapp?: string | null;
  contact_address?: string | null;
  primary_color?: string | null;
}

export interface InvoiceOut {
  id: number;
  period_year: number;
  period_month: number;
  consumo: number;
  monto: number;
  vencimiento: string | null;
  pagado: boolean;
}

export interface MemberAccount {
  numero_socio: string;
  nombre: string;
  saldo_total: number;
  ultima_factura: InvoiceOut | null;
  historial: InvoiceOut[];
  mp_alias: string | null;
  mp_cbu: string | null;
  mp_titular: string | null;
  mp_connected: boolean;
  helipagos_connected: boolean;
  macroclick_connected: boolean;
}

export interface MpStatus {
  configured: boolean;
  connected: boolean;
  mp_user_id: string | null;
}

export interface HelipagosStatus {
  connected: boolean;
  environment: "sandbox" | "production";
}

// Macro Click de Pago (Banco Macro) - integración NO OFICIAL, reconstruida a
// partir de un plugin de terceros (ver backend/app/services/macroclick.py).
export interface MacroclickStatus {
  connected: boolean;
  environment: "sandbox" | "production";
}

export type AdminRole = "owner" | "staff";

export interface AdminUserOut {
  id: number;
  email: string;
  role: AdminRole;
  created_at: string;
}

export interface AuditLogEntry {
  id: number;
  actor_type: "admin" | "platform";
  actor_email: string;
  action: string;
  target: string | null;
  details: string | null;
  created_at: string;
}

export interface MemberRow {
  id: number;
  numero_socio: string;
  nombre: string;
  identificador: string;
  saldo_total: number;
  corte_estado: CutEstado | null;
}

export type CutEstado = "ordenado" | "ejecutado" | "reposicion_ordenada" | "repuesto" | "cancelado";
export type CutMotivo = "impago" | "multa" | "otro";

export interface AdminMeter {
  id: number;
  codigo: string;
  tipo: "luz" | "agua" | "gas";
  direccion: string | null;
  activo: boolean;
  member_id: number;
  corte_estado: CutEstado | null;
  corte_id: number | null;
}

export interface ServiceCut {
  id: number;
  meter_id: number;
  codigo: string;
  tipo: "luz" | "agua" | "gas";
  direccion: string | null;
  member_id: number;
  numero_socio: string;
  nombre_socio: string;
  motivo: CutMotivo;
  detalle: string | null;
  estado: CutEstado;
  ordenado_por_email: string;
  created_at: string;
  ejecutado_por_nombre: string | null;
  ejecutado_at: string | null;
  ejecucion_nota: string | null;
  ejecucion_foto_urls: string[] | null;
  reposicion_ordenada_por_email: string | null;
  reposicion_ordenada_at: string | null;
  repuesto_por_nombre: string | null;
  repuesto_at: string | null;
  reposicion_nota: string | null;
  reposicion_foto_urls: string[] | null;
  cancelado_por_email: string | null;
  cancelado_at: string | null;
}

export interface ImportResult {
  period_year: number;
  period_month: number;
  rows_processed: number;
  members_created: number;
  members_updated: number;
}

export interface TenantSummary {
  id: number;
  slug: string;
  name: string;
  admin_count: number;
  member_count: number;
  created_at: string;
}

export interface PdfProfile {
  tenant_id: number;
  field_patterns: Record<string, string>;
  updated_at: string;
}

export interface PdfProfilePreviewPage {
  page: number;
  raw_text: string;
  fields: Record<string, string | null>;
}

export interface PdfImportJob {
  id: number;
  status: "pending" | "running" | "done" | "error";
  total_pages: number;
  processed_pages: number;
  error: string | null;
  import_batch_id: number | null;
}

export interface TenantCreate {
  slug: string;
  name: string;
  admin_email: string;
  admin_password: string;
  mp_alias?: string | null;
  mp_cbu?: string | null;
  mp_titular?: string | null;
  primary_color?: string;
}

export interface AdminUserOut {
  id: number;
  email: string;
  created_at: string;
}

export function getTenant(slug: string) {
  return request<TenantPublic>(`/api/t/${slug}`);
}

export function lookupMember(slug: string, numeroSocio: string, identificador: string) {
  return request<MemberAccount>(`/api/t/${slug}/lookup`, {
    method: "POST",
    body: JSON.stringify({ numero_socio: numeroSocio, identificador }),
  });
}

export function boletaUrl(slug: string, numeroSocio: string, identificador: string) {
  const params = new URLSearchParams({ numero_socio: numeroSocio, identificador });
  return `${API_BASE}/api/t/${slug}/boleta.pdf?${params.toString()}`;
}

export function payInvoice(
  slug: string,
  invoiceId: number,
  numeroSocio: string,
  identificador: string,
) {
  return request<{ init_point: string }>(`/api/t/${slug}/invoices/${invoiceId}/pay`, {
    method: "POST",
    body: JSON.stringify({ numero_socio: numeroSocio, identificador }),
  });
}

export function payInvoiceHelipagos(
  slug: string,
  invoiceId: number,
  numeroSocio: string,
  identificador: string,
) {
  return request<{ init_point: string }>(`/api/t/${slug}/invoices/${invoiceId}/pay-helipagos`, {
    method: "POST",
    body: JSON.stringify({ numero_socio: numeroSocio, identificador }),
  });
}

export function payInvoiceMacroclick(
  slug: string,
  invoiceId: number,
  numeroSocio: string,
  identificador: string,
) {
  return request<{ init_point: string }>(`/api/t/${slug}/invoices/${invoiceId}/pay-macroclick`, {
    method: "POST",
    body: JSON.stringify({ numero_socio: numeroSocio, identificador }),
  });
}

export function adminLogin(slug: string, email: string, password: string) {
  return request<{ access_token: string }>(`/api/t/${slug}/admin/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function listMembers(slug: string, token: string) {
  return request<MemberRow[]>(`/api/t/${slug}/admin/members`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function deleteMember(slug: string, token: string, memberId: number) {
  return request<{ deleted: number }>(`/api/t/${slug}/admin/members/${memberId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function deleteMembers(slug: string, token: string, memberIds: number[]) {
  return request<{ deleted: number }>(`/api/t/${slug}/admin/members/delete`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ member_ids: memberIds }),
  });
}

export function listMemberInvoices(slug: string, token: string, memberId: number) {
  return request<InvoiceOut[]>(`/api/t/${slug}/admin/members/${memberId}/invoices`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function setInvoicePagado(slug: string, token: string, invoiceId: number, pagado: boolean) {
  return request<InvoiceOut>(`/api/t/${slug}/admin/invoices/${invoiceId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ pagado }),
  });
}

export function markOldestInvoicePaid(slug: string, token: string, memberId: number) {
  return request<InvoiceOut>(`/api/t/${slug}/admin/members/${memberId}/mark-oldest-invoice-paid`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getAdminSettings(slug: string, token: string) {
  return request<TenantSettings>(`/api/t/${slug}/admin/settings`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function updateAdminSettings(slug: string, token: string, payload: TenantSettingsUpdate) {
  return request<TenantSettings>(`/api/t/${slug}/admin/settings`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
}

export async function uploadLogo(slug: string, token: string, kind: "primary", file: File) {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/t/${slug}/admin/logo`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail ?? "Ocurrió un error al subir el logo");
  }
  return res.json() as Promise<TenantSettings>;
}

export function deleteLogo(slug: string, token: string, kind: "primary") {
  return request<TenantSettings>(`/api/t/${slug}/admin/logo?kind=${kind}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getMpStatus(slug: string, token: string) {
  return request<MpStatus>(`/api/t/${slug}/admin/mp/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getMpConnectUrl(slug: string, token: string) {
  return request<{ url: string }>(`/api/t/${slug}/admin/mp/connect-url`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function disconnectMp(slug: string, token: string) {
  return request<MpStatus>(`/api/t/${slug}/admin/mp`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getHelipagosStatus(slug: string, token: string) {
  return request<HelipagosStatus>(`/api/t/${slug}/admin/helipagos/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function connectHelipagos(
  slug: string,
  token: string,
  payload: { token: string; webhook_apikey: string; environment: "sandbox" | "production" },
) {
  return request<HelipagosStatus>(`/api/t/${slug}/admin/helipagos`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
}

export function disconnectHelipagos(slug: string, token: string) {
  return request<HelipagosStatus>(`/api/t/${slug}/admin/helipagos`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getMacroclickStatus(slug: string, token: string) {
  return request<MacroclickStatus>(`/api/t/${slug}/admin/macroclick/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function connectMacroclick(
  slug: string,
  token: string,
  payload: { comercio_id: string; sucursal: string; secret_key: string; environment: "sandbox" | "production" },
) {
  return request<MacroclickStatus>(`/api/t/${slug}/admin/macroclick`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
}

export function disconnectMacroclick(slug: string, token: string) {
  return request<MacroclickStatus>(`/api/t/${slug}/admin/macroclick`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getCurrentAdmin(slug: string, token: string) {
  return request<AdminUserOut>(`/api/t/${slug}/admin/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function listAdmins(slug: string, token: string) {
  return request<AdminUserOut[]>(`/api/t/${slug}/admin/admins`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function createAdmin(
  slug: string,
  token: string,
  payload: { email: string; password: string; role: AdminRole },
) {
  return request<AdminUserOut>(`/api/t/${slug}/admin/admins`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
}

export function updateAdminRole(slug: string, token: string, adminId: number, role: AdminRole) {
  return request<AdminUserOut>(`/api/t/${slug}/admin/admins/${adminId}/role`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ role }),
  });
}

export function deleteAdmin(slug: string, token: string, adminId: number) {
  return request<AdminUserOut>(`/api/t/${slug}/admin/admins/${adminId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function resetAdminPassword(slug: string, token: string, adminId: number, password: string) {
  return request<AdminUserOut>(`/api/t/${slug}/admin/admins/${adminId}/reset-password`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ password }),
  });
}

export type GestorQrStatus = "pending" | "claimed" | "approved" | "denied" | "expired";

export interface GestorQrStart {
  code: string;
  expires_at: string;
}

export interface GestorQrAdminStatus {
  status: GestorQrStatus;
  expires_at: string;
}

export function startGestorQr(slug: string, token: string) {
  return request<GestorQrStart>(`/api/t/${slug}/admin/gestor-qr/start`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getGestorQrStatus(slug: string, token: string, code: string) {
  return request<GestorQrAdminStatus>(`/api/t/${slug}/admin/gestor-qr/${code}/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function approveGestorQr(slug: string, token: string, code: string) {
  return request<GestorQrAdminStatus>(`/api/t/${slug}/admin/gestor-qr/${code}/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function denyGestorQr(slug: string, token: string, code: string) {
  return request<GestorQrAdminStatus>(`/api/t/${slug}/admin/gestor-qr/${code}/deny`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function listAdminMeters(slug: string, token: string) {
  return request<AdminMeter[]>(`/api/t/${slug}/admin/meters`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function listCuts(slug: string, token: string) {
  return request<ServiceCut[]>(`/api/t/${slug}/admin/cuts`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// meterIds null = todos los medidores del socio que no tengan un corte vigente.
export function orderCuts(
  slug: string,
  token: string,
  memberId: number,
  payload: { meter_ids: number[] | null; motivo: CutMotivo; detalle: string | null },
) {
  return request<ServiceCut[]>(`/api/t/${slug}/admin/members/${memberId}/cuts`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
}

export function cancelCut(slug: string, token: string, cutId: number) {
  return request<ServiceCut>(`/api/t/${slug}/admin/cuts/${cutId}/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function orderCutRestore(slug: string, token: string, cutId: number) {
  return request<ServiceCut>(`/api/t/${slug}/admin/cuts/${cutId}/order-restore`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getAuditLog(slug: string, token: string) {
  return request<AuditLogEntry[]>(`/api/t/${slug}/admin/audit-log`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function importSpreadsheet(
  slug: string,
  token: string,
  file: File,
  periodYear: number,
  periodMonth: number,
) {
  const form = new FormData();
  form.append("file", file);
  form.append("period_year", String(periodYear));
  form.append("period_month", String(periodMonth));

  const res = await fetch(`${API_BASE}/api/t/${slug}/admin/import`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail ?? "Ocurrió un error al importar");
  }
  return res.json() as Promise<ImportResult>;
}

export async function importPdf(
  slug: string,
  token: string,
  files: File[],
  periodYear: number,
  periodMonth: number,
) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  form.append("period_year", String(periodYear));
  form.append("period_month", String(periodMonth));

  const res = await fetch(`${API_BASE}/api/t/${slug}/admin/import-pdf`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail ?? "Ocurrió un error al importar");
  }
  return res.json() as Promise<PdfImportJob>;
}

export function getPdfImportStatus(slug: string, token: string, jobId: number) {
  return request<PdfImportJob>(`/api/t/${slug}/admin/import-pdf/status/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// -- Dev (plataforma) --------------------------------------------------

export function devLogin(email: string, password: string) {
  return request<{ access_token: string }>(`/api/dev/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function listTenants(devToken: string) {
  return request<TenantSummary[]>(`/api/dev/tenants`, {
    headers: { Authorization: `Bearer ${devToken}` },
  });
}

export function createTenant(devToken: string, payload: TenantCreate) {
  return request<TenantSettings>(`/api/dev/tenants`, {
    method: "POST",
    headers: { Authorization: `Bearer ${devToken}` },
    body: JSON.stringify(payload),
  });
}

export function listTenantAdmins(devToken: string, slug: string) {
  return request<AdminUserOut[]>(`/api/dev/tenants/${slug}/admins`, {
    headers: { Authorization: `Bearer ${devToken}` },
  });
}

export function createTenantAdmin(devToken: string, slug: string, email: string, password: string) {
  return request<AdminUserOut>(`/api/dev/tenants/${slug}/admins`, {
    method: "POST",
    headers: { Authorization: `Bearer ${devToken}` },
    body: JSON.stringify({ email, password }),
  });
}

export function resetTenantAdminPassword(devToken: string, slug: string, adminId: number, password: string) {
  return request<AdminUserOut>(`/api/dev/tenants/${slug}/admins/${adminId}/reset-password`, {
    method: "POST",
    headers: { Authorization: `Bearer ${devToken}` },
    body: JSON.stringify({ password }),
  });
}

export function deleteTenantAdmin(devToken: string, slug: string, adminId: number) {
  return request<AdminUserOut>(`/api/dev/tenants/${slug}/admins/${adminId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${devToken}` },
  });
}

export function getPdfProfile(devToken: string, slug: string) {
  return request<PdfProfile | null>(`/api/dev/tenants/${slug}/pdf-profile`, {
    headers: { Authorization: `Bearer ${devToken}` },
  });
}

export function savePdfProfile(devToken: string, slug: string, fieldPatterns: Record<string, string>) {
  return request<PdfProfile>(`/api/dev/tenants/${slug}/pdf-profile`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${devToken}` },
    body: JSON.stringify({ field_patterns: fieldPatterns }),
  });
}

export async function testPdfProfile(
  devToken: string,
  slug: string,
  fieldPatterns: Record<string, string>,
  file: File,
) {
  const form = new FormData();
  form.append("field_patterns", JSON.stringify(fieldPatterns));
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/dev/tenants/${slug}/pdf-profile/test`, {
    method: "POST",
    headers: { Authorization: `Bearer ${devToken}` },
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail ?? "Ocurrió un error al probar el perfil");
  }
  return res.json() as Promise<PdfProfilePreviewPage[]>;
}
