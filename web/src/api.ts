// Typed client for api-service, chat-service and preprocess-service (docs/contract.md).

import { getToken } from "./auth";

export type AnalysisStatus = "waiting" | "queued" | "processing" | "done" | "failed";
export type ReviewStatus = "draft" | "submitted" | "approved" | "changes_requested";

export interface Fields {
  merchant_name?: string | null;
  business_number?: string | null;
  transaction_at?: string | null;
  supply_amount?: number | null;
  vat_amount?: number | null;
  exempt_amount?: number | null; // tax-exempt part (marts, post, books)
  total_amount?: number | null;
  payment_method?: string | null;
  card_issuer?: string | null;
  card_number?: string | null; // exactly as printed (partial, full or masked)
  approval_number?: string | null;
  category?: CategoryCode | null;
  purpose?: string | null;
  department?: string | null;
}
export type FieldKey = keyof Fields;

export interface Check {
  code: string;
  level: "error" | "warn";
  message: string;
}

export interface HistoryEvent {
  at: string;
  actor: string;
  action: string;
  note: string | null;
}

export type Point = [number, number];
/** Top-left, top-right, bottom-right, bottom-left, in original-photo pixels. */
export type Quad = [Point, Point, Point, Point];

/** What preprocess-service found on the uploaded original (shown for the user to confirm). */
export interface Detection {
  found: boolean;
  corners: Quad; // suggested frame when nothing was found
  width: number;
  height: number;
  blur_score: number;
  blurry: boolean;
  elapsed_ms: number;
}

/** The crop that was applied (stored on the receipt as `preprocess`). */
export interface PreprocessMeta {
  where: "server";
  corners: Quad | null;
  detected_corners: Quad | null;
  adjusted: boolean;
  blur_score: number;
  width: number;
  height: number;
  elapsed_ms: number;
}

export interface Receipt {
  id: string;
  owner_sub: string;
  owner_name: string;
  owner_profile?: OwnerProfile;
  analysis_status: AnalysisStatus;
  analysis_error?: string | null;
  review_status: ReviewStatus;
  review_note?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  fields: Fields;
  needs_check: FieldKey[];
  ai_filled?: FieldKey[]; // filled by the AI and not edited by a person since
  result_confirmed_at?: string | null; // the employee confirmed the AI's reading (result card)
  review_fields?: string[]; // fields the reviewer asked to look at again ("photo" = retake)
  review_points?: ReviewPoint[]; // what a reviewer should look at first (server rules)
  checks: Check[];
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  timings: Record<string, string>;
  model_usage?: { input_tokens: number; output_tokens: number; latency_ms: number };
  preprocess?: PreprocessMeta | null;
  image_url?: string | null; // cropped image the AI read
  original_url?: string | null; // the photo as taken
  history?: HistoryEvent[];
}

export interface Upload {
  url: string;
  method: "PUT";
  headers: Record<string, string>;
}

export type CategoryCode =
  | "food"
  | "entertainment"
  | "travel"
  | "delivery"
  | "supplies"
  | "education"
  | "welfare_event"
  | "subscription"
  | "marketing"
  | "other";

/** Login profile (Cognito attributes). Employees can read it; admins change it. */
export interface Me {
  sub: string;
  email: string;
  name: string;
  employee_no: string | null;
  department: string | null;
  position: string | null;
  role: "employee" | "reviewer" | "admin";
  role_label: string;
}

export interface OwnerProfile {
  employee_no: string | null;
  department: string | null;
  position: string | null;
}

export interface ReviewPoint {
  level: "error" | "warn" | "info";
  code: string; // kind of point (docs/contract.md), used to suggest a change request
  text: string;
  fields: FieldKey[]; // the fields it is about
}

export interface ChatMessage {
  at: string;
  /** "tool" lines are shown only while the page is open (what the assistant changed). */
  role: "user" | "assistant" | "tool";
  text: string;
  slot?: string | null;
  /** Buttons the assistant attached to this reply (shown again when the page is reopened). */
  choices?: string[];
  suggestions?: ExpenseSuggestion[];
  /** ["submit"]: the final review card sits right after this message. */
  actions?: string[];
}

/** A purpose · category pair the assistant suggests from the receipt context. */
export interface ExpenseSuggestion {
  purpose: string;
  category: string;
  category_label: string;
}

export interface ChatDone {
  text: string;
  slot: string | null;
  choices: string[];
  finished: boolean;
  repeat: boolean;
  suggestions: ExpenseSuggestion[];
  /** ["submit"]: show the submit button. */
  actions: string[];
  /** The assistant changed the receipt with a tool: reload it. */
  changed: boolean;
  fields: Fields;
}

export type ChatEvent = "start" | "analysis_done" | "changes_requested";

/** One of: what the employee said, a screen event, or a suggestion button (saved without the model). */
export interface ChatTurn {
  message?: string;
  event?: ChatEvent;
  choice?: { purpose: string; category: string };
}

export interface ChatTool {
  name: string;
  summary: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields?: FieldKey[],
  ) {
    super(message);
  }
}

async function headers(extra: Record<string, string> = {}) {
  const token = await getToken();
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const send = async () =>
    fetch(path, {
      method,
      headers: await headers(body !== undefined ? { "Content-Type": "application/json" } : {}),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  let resp = await send();
  if (resp.status === 401 && (await getToken(true))) resp = await send(); // token expired mid-session
  if (resp.status === 401) window.dispatchEvent(new Event("rf:unauthorized"));
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const e = err.error ?? {};
    throw new ApiError(resp.status, e.code ?? "http_error", e.message ?? `요청 실패 (${resp.status})`, e.fields);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const api = {
  me: () => request<Me>("GET", "/api/me"),
  meta: () =>
    request<{ categories: { code: string; label: string; hint: string }[]; departments: { code: string; name: string }[] }>(
      "GET", "/api/meta"),
  create: () => request<{ receipt: Receipt; upload: Upload }>("POST", "/api/receipts"),
  reuploadUrl: (id: string) => request<{ receipt: Receipt; upload: Upload }>("POST", `/api/receipts/${id}/upload-url`),
  uploaded: (id: string) => request<Receipt>("POST", `/api/receipts/${id}/uploaded`),
  mine: () => request<{ items: Receipt[] }>("GET", "/api/receipts"),
  get: (id: string) => request<Receipt>("GET", `/api/receipts/${id}`),
  patch: (id: string, fields: Fields) => request<Receipt>("PATCH", `/api/receipts/${id}`, { fields }),
  submit: (id: string) => request<Receipt>("POST", `/api/receipts/${id}/submit`),
  /** Drafts only (never submitted): the record, chat, history and both photos are removed for good. */
  remove: (id: string) => request<void>("DELETE", `/api/receipts/${id}`),
  reviewList: (status: ReviewStatus) => request<{ items: Receipt[] }>("GET", `/api/review/receipts?status=${status}`),
  approve: (id: string) => request<Receipt>("POST", `/api/review/receipts/${id}/approve`),
  /** fields: what the employee should look at again ("photo" = retake). */
  requestChanges: (id: string, reason: string, fields: string[] = []) =>
    request<Receipt>("POST", `/api/review/receipts/${id}/request-changes`, { reason, fields }),
  detect: (id: string) => request<Detection>("POST", `/preprocess/receipts/${id}/detect`),
  applyCrop: (id: string, corners: Quad | null) =>
    request<PreprocessMeta>("POST", `/preprocess/receipts/${id}/apply`, { corners }),
  chatMessages: (id: string) => request<{ items: ChatMessage[] }>("GET", `/chat/receipts/${id}/messages`),
};

// ── admin (/api/admin) ──────────────────────────────
export type AccountRole = "employee" | "reviewer" | "admin";

export interface Account {
  username: string;
  sub: string | null;
  email: string | null;
  name: string | null;
  employee_no: string | null;
  department: string | null;
  position: string | null;
  role: AccountRole;
  role_label: string;
  status: string; // Cognito: FORCE_CHANGE_PASSWORD (first sign-in pending), CONFIRMED, ...
  enabled: boolean;
  created_at: string | null;
}

export interface AccountInput {
  email?: string;
  name?: string;
  department?: string;
  position?: string;
  role?: AccountRole;
}

export interface OrgOptions {
  departments: { code: string; name: string; description: string }[];
  positions: string[];
  reviewer_department: string; // 검수 담당자 must belong here
}

export interface DevProfile {
  id: string;
  name: string;
  role: AccountRole;
  role_label: string;
  department: string | null;
  position: string;
  employee_no: string;
}

export interface Deletion {
  key: string;
  receipt_id: string;
  deleted_at: string;
  deleted_by: string;
  owner_name: string | null;
  merchant_name: string | null;
  total_amount: number | null;
  review_status: ReviewStatus | null;
}

const enc = encodeURIComponent;

/** Local developer login: the test accounts (404 when the server has it off). No sign-in needed. */
export async function devProfiles(): Promise<DevProfile[]> {
  const resp = await fetch("/api/dev/profiles");
  if (!resp.ok) throw new Error(resp.status === 404 ? "off" : `요청 실패 (${resp.status})`);
  return (await resp.json()).items;
}

export const admin = {
  options: () => request<OrgOptions>("GET", "/api/admin/options"),
  users: () => request<{ items: Account[] }>("GET", "/api/admin/users"),
  /** The temporary password comes back once, here only. */
  createUser: (body: AccountInput) =>
    request<{ user: Account; temporary_password: string }>("POST", "/api/admin/users", body),
  updateUser: (username: string, body: AccountInput) =>
    request<{ user: Account }>("PATCH", `/api/admin/users/${enc(username)}`, body),
  resetPassword: (username: string) =>
    request<{ temporary_password: string }>("POST", `/api/admin/users/${enc(username)}/temporary-password`),
  /** For good; receipts the person made stay. */
  deleteUser: (username: string) => request<void>("DELETE", `/api/admin/users/${enc(username)}`),
  setEnabled: (username: string, enabled: boolean) =>
    request<{ user: Account }>("POST", `/api/admin/users/${enc(username)}/${enabled ? "enable" : "disable"}`),
  receipts: (status: ReviewStatus) => request<{ items: Receipt[] }>("GET", `/api/admin/receipts?status=${status}`),
  deleteReceipt: (id: string) => request<void>("DELETE", `/api/admin/receipts/${id}`),
  deletions: () => request<{ items: Deletion[] }>("GET", "/api/admin/deletions"),
  deleteDeletion: (key: string) => request<void>("DELETE", `/api/admin/deletions/${enc(key)}`),
  clearDeletions: () => request<void>("DELETE", "/api/admin/deletions"),
};

export async function putImage(upload: Upload, blob: Blob) {
  const resp = await fetch(upload.url, { method: "PUT", headers: upload.headers, body: blob });
  if (!resp.ok) throw new ApiError(resp.status, "upload_failed", "사진 업로드에 실패했습니다. 다시 시도해 주세요.");
}

export async function downloadCsv(month: string) {
  const resp = await fetch(`/api/review/export.csv?month=${month}`, { headers: await headers() });
  if (!resp.ok) throw new ApiError(resp.status, "export_failed", "내보내기에 실패했습니다.");
  const url = URL.createObjectURL(await resp.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: `receipts-${month}.csv` });
  a.click();
  URL.revokeObjectURL(url);
}

/** POST a chat turn and read the SSE stream (fetch, since EventSource cannot POST or send headers). */
export async function chatTurn(
  id: string,
  turn: ChatTurn,
  onDelta: (text: string) => void,
  onTool: (tool: ChatTool) => void = () => {},
): Promise<ChatDone> {
  const resp = await fetch(`/chat/receipts/${id}/turn`, {
    method: "POST",
    headers: await headers({ "Content-Type": "application/json", Accept: "text/event-stream" }),
    body: JSON.stringify(turn),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new ApiError(resp.status, err.error?.code ?? "chat_failed", err.error?.message ?? "챗봇 응답에 실패했습니다.");
  }
  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let done: ChatDone | null = null;
  for (;;) {
    const { value, done: end } = await reader.read();
    if (value) buffer += value;
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "delta") onDelta(payload.text);
      if (event === "tool") onTool(payload);
      if (event === "done") done = payload;
    }
    if (end) break;
  }
  if (!done) throw new ApiError(500, "chat_incomplete", "챗봇 응답이 끊겼습니다.");
  return done;
}
