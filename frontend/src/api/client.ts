import type {
  ExclusionRow,
  GroqSuggestResponse,
  IngestionBatch,
  NormalizedActivity,
  NormalizedActivityDetail,
  Paginated,
  RawRecord,
  ReviewSummary,
} from "./types";

const BASE = ""; // same-origin; Vite dev server proxies /api to :8000

function parseErrorDetail(body: string): string {
  if (!body) return "No response body returned.";
  try {
    const data = JSON.parse(body);
    if (typeof data.detail === "string") return data.detail;
    if (typeof data.error === "string") return data.error;
    return JSON.stringify(data);
  } catch {
    return body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    const detail = parseErrorDetail(body);
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

// -------- Ingestion --------

export function uploadSap(file: File, kind: "mb51" | "me2m"): Promise<IngestionBatch> {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  return request<IngestionBatch>("/api/ingestion/sap/upload/", { method: "POST", body: form });
}

export function uploadUtility(file: File): Promise<IngestionBatch> {
  const form = new FormData();
  form.append("file", file);
  return request<IngestionBatch>("/api/ingestion/utility/upload/", { method: "POST", body: form });
}

export function travelSync(startDate?: string, endDate?: string): Promise<IngestionBatch> {
  return request<IngestionBatch>("/api/ingestion/travel-sync/", {
    method: "POST",
    body: JSON.stringify({ start_date: startDate || null, end_date: endDate || null }),
  });
}

export function listBatches(params: Record<string, string> = {}): Promise<Paginated<IngestionBatch>> {
  const qs = new URLSearchParams(params).toString();
  return request<Paginated<IngestionBatch>>(`/api/ingestion/batches/${qs ? `?${qs}` : ""}`);
}

export function getBatch(id: string): Promise<IngestionBatch> {
  return request<IngestionBatch>(`/api/ingestion/batches/${id}/`);
}

export function listBatchRaw(id: string): Promise<Paginated<RawRecord>> {
  return request<Paginated<RawRecord>>(`/api/ingestion/batches/${id}/raw-records/`);
}

export function listBatchExclusions(id: string): Promise<Paginated<ExclusionRow>> {
  return request<Paginated<ExclusionRow>>(`/api/ingestion/batches/${id}/exclusions/`);
}

// -------- Mock travel preview / upload --------

export function mockTravelSync(start?: string, end?: string) {
  const params = new URLSearchParams();
  if (start) params.set("start_date", start);
  if (end) params.set("end_date", end);
  return request<{
    total_count: number;
    returned_count: number;
    fixture_trip_count?: number;
    uploaded_trip_count?: number;
    trips: unknown[];
  }>(
    `/api/mock-travel/sync/${params.toString() ? `?${params.toString()}` : ""}`,
  );
}

export type MockTravelUploadResult = {
  accepted_count: number;
  rejected_count: number;
  rejected: Array<{ index: number; reason: string }>;
  total_uploaded_count: number;
  source_label: string;
};

export function mockTravelUpload(file: File, sourceLabel?: string) {
  const form = new FormData();
  form.append("file", file);
  if (sourceLabel) form.append("source_label", sourceLabel);
  return request<MockTravelUploadResult>("/api/mock-travel/upload/", {
    method: "POST",
    body: form,
  });
}

export function mockTravelClearUploads() {
  return request<{ deleted_count: number }>("/api/mock-travel/uploads/", {
    method: "DELETE",
  });
}

// -------- Review --------

export function reviewSummary(): Promise<ReviewSummary> {
  return request<ReviewSummary>("/api/review/summary/");
}

export function listActivities(params: Record<string, string> = {}): Promise<Paginated<NormalizedActivity>> {
  const qs = new URLSearchParams(params).toString();
  return request<Paginated<NormalizedActivity>>(`/api/review/activities/${qs ? `?${qs}` : ""}`);
}

export function getActivity(id: string): Promise<NormalizedActivityDetail> {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/`);
}

export function approveActivity(id: string, comment?: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/approve/`, {
    method: "POST", body: JSON.stringify({ comment }),
  });
}
export function rejectActivity(id: string, comment: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/reject/`, {
    method: "POST", body: JSON.stringify({ comment }),
  });
}
export function markNotRelevant(id: string, comment?: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/mark-not-relevant/`, {
    method: "POST", body: JSON.stringify({ comment }),
  });
}
export function requestClarification(id: string, comment: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/request-clarification/`, {
    method: "POST", body: JSON.stringify({ comment }),
  });
}
export function overrideActivity(id: string, field: string, value: unknown, comment: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/override/`, {
    method: "POST", body: JSON.stringify({ field, value, comment }),
  });
}
export function lockActivity(id: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/lock/`, { method: "POST" });
}
export function groqSuggest(id: string, force = false) {
  return request<GroqSuggestResponse>(`/api/review/activities/${id}/groq-suggest/`, {
    method: "POST", body: JSON.stringify({ force }),
  });
}
export function acceptLlm(id: string, field: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/accept-llm-suggestion/`, {
    method: "POST", body: JSON.stringify({ field }),
  });
}
export function rejectLlm(id: string, field: string, comment?: string) {
  return request<NormalizedActivityDetail>(`/api/review/activities/${id}/reject-llm-suggestion/`, {
    method: "POST", body: JSON.stringify({ field, comment }),
  });
}
