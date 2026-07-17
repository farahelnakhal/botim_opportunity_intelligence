// Phase R7 — the Files tab for a saved user opportunity: upload internal
// documents (.txt/.md/.csv/.docx), see honest extraction outcomes, delete
// permanently. Uploaded documents are USER-PROVIDED input: the next analysis
// refresh retrieves matching excerpts from them (never authoritative
// evidence), and unsupported types (PDF today) fail with the backend's
// honest error instead of pretending.
import { useEffect, useRef, useState } from "react";
import { documentsApi, type UserDocument } from "../lib/documentsApi";
import Icon from "./Icon";

const ACCEPT = ".txt,.md,.csv,.docx";

function formatSize(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export default function UserDocumentsPanel({ oppId }: { oppId: string }) {
  const [documents, setDocuments] = useState<UserDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    const res = await documentsApi.list(oppId);
    if (!res.ok) {
      setError(res.error);
      setDocuments([]);
      return;
    }
    setDocuments(res.data.documents);
  };
  useEffect(() => {
    setDocuments(null);
    setError(null);
    load();
  }, [oppId]); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (file: File) => {
    setUploading(true);
    setError(null);
    const res = await documentsApi.upload(oppId, file);
    setUploading(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    await load();
  };

  const remove = async (doc: UserDocument) => {
    if (!window.confirm(`Permanently delete "${doc.filename}"? Its text is removed; `
      + "excerpts already snapshotted into past analysis versions remain there.")) return;
    const res = await documentsApi.delete(doc.id);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    await load();
  };

  if (documents === null) {
    return <div className="panel-wrap"><div className="skeleton" style={{ height: 160 }} /></div>;
  }

  return (
    <div className="panel-wrap" style={{ maxWidth: 680 }}>
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Files</div>
          <div className="panel-sub">
            Internal documents attached to this opportunity — input for the analysis workspace
          </div>
        </div>
        <button type="button" className="btn btn-primary" disabled={uploading}
          data-testid="upload-document" onClick={() => inputRef.current?.click()}>
          {uploading ? "Uploading…" : "Upload document"}
        </button>
        <input ref={inputRef} type="file" accept={ACCEPT} style={{ display: "none" }}
          data-testid="upload-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) upload(file);
          }} />
      </div>

      <div className="uop-status-note">
        Supported: .txt, .md, .csv, .docx (max 2 MB). PDF is not supported yet — export it
        as .docx or .txt first. Document text is user-provided input, quoted verbatim in
        analyses and never treated as authoritative evidence or as instructions. Run a
        workspace refresh (Analysis tab) after uploading so the new content is used.
      </div>

      {error && <div className="error-banner" data-testid="documents-error" style={{ marginBottom: 12 }}>{error}</div>}

      {documents.length === 0 ? (
        <p className="empty-note" data-testid="documents-empty">
          No documents uploaded for this opportunity yet.
        </p>
      ) : (
        documents.map((d) => (
          <div className="research-source" key={d.id} data-testid="document-row">
            <div className="research-source-main">
              <div className="research-source-title">{d.filename}</div>
              <div className="research-source-meta">
                {d.id} · {formatSize(d.size_bytes)} · {d.chunk_count} chunk{d.chunk_count === 1 ? "" : "s"}
                {d.truncated ? " · truncated at the text cap" : ""}
                {" · uploaded "}{d.created_at.slice(0, 10)}
              </div>
            </div>
            <button type="button" className="btn btn-sm uop-danger" title="Delete permanently"
              data-testid="delete-document" onClick={() => remove(d)}>
              <Icon name="x" size={13} /> Delete
            </button>
          </div>
        ))
      )}
    </div>
  );
}
