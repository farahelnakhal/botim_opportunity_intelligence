// Phase R7 — uploaded-document client. Files are base64-encoded client-side
// and extracted server-side (synchronous, honest failure). Same result shape
// as the other clients.

export interface UserDocument {
  id: string;
  opportunity_id: string;
  owner_user_id: string | null;
  filename: string;
  extension: string;
  size_bytes: number;
  text_chars: number;
  truncated: boolean;
  chunk_count: number;
  status: "extracted" | "failed";
  error: string | null;
  created_at: string;
}

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type DocumentsResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function request<T>(path: string, init?: RequestInit): Promise<DocumentsResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the documents API" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the documents API is unreachable" };
  }
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.slice(result.indexOf(",") + 1)); // strip data: prefix
    };
    reader.onerror = () => reject(new Error("could not read the file"));
    reader.readAsDataURL(file);
  });
}

export const documentsApi = {
  list(oppId: string) {
    return request<{ documents: UserDocument[] }>(
      `/user-opportunities/${encodeURIComponent(oppId)}/documents`,
    );
  },

  async upload(oppId: string, file: File): Promise<DocumentsResult<UserDocument>> {
    let content: string;
    try {
      content = await toBase64(file);
    } catch {
      return { ok: false, error: "could not read the selected file" };
    }
    return request<UserDocument>(
      `/user-opportunities/${encodeURIComponent(oppId)}/documents`,
      { method: "POST", body: JSON.stringify({ filename: file.name, content_base64: content }) },
    );
  },

  delete(docId: string) {
    return request<{ deleted: boolean; id: string }>(
      `/documents/${encodeURIComponent(docId)}`, { method: "DELETE" },
    );
  },
};
