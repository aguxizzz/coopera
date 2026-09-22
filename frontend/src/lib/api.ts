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
}

export interface InvoiceOut {
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
}

export interface MemberRow {
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
