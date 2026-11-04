import { useCallback, useState } from "react";
import { api, formatDate, formatNumber } from "../../api";
import type { Paged } from "../../api";
import { useSession } from "../../App";
import { ConfirmDelete, DataTable, Field, Modal, useToast } from "../../components/ui";
import type { Column } from "../../components/ui";

interface BaseRow {
  id: string;
  name: string;
  description: string;
  documents: number;
  chunks: number;
}

interface DocumentRow {
  id: string;
  title: string;
  source_type: string;
  status: string;
  error: string;
  chunk_count: number;
  created_at: string;
}

interface Hit {
  title: string;
  section: string;
  text: string;
  language: string;
}

function AddBase({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const toast = useToast();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setError("Knowledge Base Name is required.");
    if (name.trim().length < 2) return setError("Knowledge Base Name must have at least 2 characters.");
    setError("");
    try {
      const result = await api<{ message: string }>("/api/admin/knowledge-bases", {
        method: "POST",
        json: { name: name.trim(), description: description.trim() },
      });
      toast(result.message);
      onSaved();
    } catch (problem) {
      setError((problem as Error).message);
    }
    return undefined;
  }

  return (
    <Modal title="Add Knowledge Base" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <Field label="Knowledge Base Name" required error={error}>
          {(props) => <input {...props} placeholder="Enter Knowledge Base Name" maxLength={60} value={name} onChange={(event) => setName(event.target.value)} />}
        </Field>
        <Field label="Description">
          {(props) => <textarea {...props} placeholder="Enter Description" maxLength={300} value={description} onChange={(event) => setDescription(event.target.value)} />}
        </Field>
        <div className="form-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary">
            Add Knowledge Base
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Documents({ base, canEdit, onClose, onChanged }: { base: BaseRow; canEdit: boolean; onClose: () => void; onChanged: () => void }) {
  const [refresh, setRefresh] = useState(0);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [fileError, setFileError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [queryError, setQueryError] = useState("");
  const [found, setFound] = useState<{ confidence: number; hits: Hit[] } | null>(null);
  const [removing, setRemoving] = useState<DocumentRow | null>(null);
  const toast = useToast();
  const load = useCallback((text: string) => api<Paged<DocumentRow>>(`/api/admin/knowledge-bases/${base.id}/documents?${text}`), [base.id]);
  const changed = () => {
    setRefresh((value) => value + 1);
    onChanged();
  };

  async function upload(file: File | undefined) {
    if (!file) return;
    setFileError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api<{ message: string }>(`/api/admin/knowledge-bases/${base.id}/documents`, { method: "POST", body: form });
      toast(result.message);
      changed();
    } catch (problem) {
      setFileError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addUrl(event: React.FormEvent) {
    event.preventDefault();
    if (!/^https?:\/\/\S+\.\S+/.test(url.trim())) return setUrlError("Enter a valid Web Page Link.");
    setUrlError("");
    setBusy(true);
    try {
      const result = await api<{ message: string }>(`/api/admin/knowledge-bases/${base.id}/urls`, { method: "POST", json: { url: url.trim() } });
      toast(result.message);
      setUrl("");
      changed();
    } catch (problem) {
      setUrlError((problem as Error).message);
    } finally {
      setBusy(false);
    }
    return undefined;
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return setQueryError("Question must have at least 2 characters.");
    setQueryError("");
    try {
      setFound(await api(`/api/admin/knowledge-bases/${base.id}/search`, { method: "POST", json: { query: query.trim() } }));
    } catch (problem) {
      setQueryError((problem as Error).message);
    }
    return undefined;
  }

  const columns: Column<DocumentRow>[] = [
    { header: "Title", cell: (row) => row.title },
    { header: "Type", cell: (row) => row.source_type.toUpperCase() },
    { header: "Passages", cell: (row) => formatNumber(row.chunk_count) },
    { header: "Status", cell: (row) => <span className={`badge ${row.status === "ready" ? "good" : row.status === "failed" ? "bad" : ""}`}>{row.status}</span> },
    { header: "Added", cell: (row) => formatDate(row.created_at) },
  ];
  if (canEdit) {
    columns.push({
      header: "Action",
      cell: (row) => (
        <button type="button" className="icon delete" title={`Delete ${row.title}`} onClick={() => setRemoving(row)}>
          Delete
        </button>
      ),
    });
  }

  return (
    <Modal title={base.name} onClose={onClose} wide>
      {canEdit ? (
        <div className="grid two">
          <Field label="Upload Document" error={fileError} hint="PDF, DOCX, TXT, CSV, JSON or MD.">
            {(props) => <input {...props} type="file" accept=".pdf,.docx,.txt,.csv,.json,.md" disabled={busy} onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }} />}
          </Field>
          <form onSubmit={addUrl} noValidate>
            <Field label="Web Page Link" error={urlError}>
              {(props) => <input {...props} placeholder="Enter Web Page Link" maxLength={500} value={url} onChange={(event) => setUrl(event.target.value)} />}
            </Field>
            <button type="submit" disabled={busy}>
              Add Web Page
            </button>
          </form>
        </div>
      ) : null}
      <DataTable columns={columns} load={load} searchPlaceholder="Search Title" refreshKey={refresh} />
      <form onSubmit={search} noValidate style={{ marginTop: "1rem" }}>
        <Field label="Test a Question" error={queryError} hint="See which passages the agent would use.">
          {(props) => <input {...props} placeholder="Enter Question" maxLength={300} value={query} onChange={(event) => setQuery(event.target.value)} />}
        </Field>
        <button type="submit">Search</button>
      </form>
      {found ? (
        <div style={{ marginTop: "0.75rem" }}>
          <p>
            <strong>Confidence: {Math.round(found.confidence * 100)}%</strong>
          </p>
          {found.hits.length === 0 ? <p className="muted">No records found</p> : null}
          {found.hits.map((hit, index) => (
            <div key={index} className="notice">
              <strong>{hit.title}</strong>
              {hit.section ? `, ${hit.section}` : ""}
              <p style={{ margin: "0.25rem 0 0" }}>{hit.text}</p>
            </div>
          ))}
        </div>
      ) : null}
      {removing ? (
        <ConfirmDelete
          title="Delete Document"
          message={`Are you sure you want to delete Document ${removing.title}?`}
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              const result = await api<{ message: string }>(`/api/admin/documents/${removing.id}`, { method: "DELETE" });
              toast(result.message);
              changed();
            } catch (problem) {
              toast((problem as Error).message, "error");
            }
            setRemoving(null);
          }}
        />
      ) : null}
    </Modal>
  );
}

export function Knowledge() {
  const [refresh, setRefresh] = useState(0);
  const [adding, setAdding] = useState(false);
  const [viewing, setViewing] = useState<BaseRow | null>(null);
  const [removing, setRemoving] = useState<BaseRow | null>(null);
  const { user } = useSession();
  const toast = useToast();
  const load = useCallback((query: string) => api<Paged<BaseRow>>(`/api/admin/knowledge-bases?${query}`), []);
  const reload = () => setRefresh((value) => value + 1);
  const canEdit = user?.role !== "viewer";
  const canDelete = user?.role === "admin" || user?.role === "owner";

  const columns: Column<BaseRow>[] = [
    { header: "Name", cell: (row) => row.name },
    { header: "Description", cell: (row) => row.description || "-" },
    { header: "Documents", cell: (row) => formatNumber(row.documents) },
    { header: "Passages", cell: (row) => formatNumber(row.chunks) },
    {
      header: canDelete ? "Actions" : "Action",
      cell: (row) => (
        <div className="row-actions">
          <button type="button" className="icon" title={`Open ${row.name}`} onClick={() => setViewing(row)}>
            Open
          </button>
          {canDelete ? (
            <button type="button" className="icon delete" title={`Delete ${row.name}`} onClick={() => setRemoving(row)}>
              Delete
            </button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="page-head">
        <h1>Knowledge</h1>
        {canEdit ? (
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            Add Knowledge Base
          </button>
        ) : null}
      </div>
      <DataTable columns={columns} load={load} searchPlaceholder="Search Name" refreshKey={refresh} />
      {adding ? (
        <AddBase
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            reload();
          }}
        />
      ) : null}
      {viewing ? <Documents base={viewing} canEdit={canEdit} onClose={() => setViewing(null)} onChanged={reload} /> : null}
      {removing ? (
        <ConfirmDelete
          title="Delete Knowledge Base"
          message={`Are you sure you want to delete Knowledge Base ${removing.name} and all ${formatNumber(removing.documents)} of its documents?`}
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              const result = await api<{ message: string }>(`/api/admin/knowledge-bases/${removing.id}`, { method: "DELETE" });
              toast(result.message);
              reload();
            } catch (problem) {
              toast((problem as Error).message, "error");
            }
            setRemoving(null);
          }}
        />
      ) : null}
    </>
  );
}
