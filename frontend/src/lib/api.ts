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
  logo_secondary_url: string | null;
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

export async function uploadLogo(slug: string, token: string, kind: "primary" | "secondary", file: File) {
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

export function deleteLogo(slug: string, token: string, kind: "primary" | "secondary") {
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
