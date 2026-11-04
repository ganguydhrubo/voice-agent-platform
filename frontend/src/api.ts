// Small typed wrappers around the server API.

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let body: { detail?: unknown } & Record<string, unknown> = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = {};
  }
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

export async function api<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = options;
  const response = await fetch(path, {
    credentials: "same-origin",
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  return parse<T>(response);
}

export interface VoiceOption {
  id: string;
  label: string;
  gender: string;
}

export interface LanguageOption {
  code: string;
  label: string;
  voices: VoiceOption[];
}

export interface AgentCard {
  slug: string;
  industry: string;
  name: string;
  role: string;
  organisation: string;
  languages: LanguageOption[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "editor" | "viewer";
}

export const roleRank: Record<User["role"], number> = { viewer: 0, editor: 1, admin: 2, owner: 3 };

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${date.getFullYear()}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const hours = date.getHours();
  const hh = String(hours % 12 || 12).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${formatDate(value)} ${hh}:${min} ${hours < 12 ? "AM" : "PM"}`;
}

export function formatNumber(value: number): string {
  return value.toLocaleString("en-IN");
}
