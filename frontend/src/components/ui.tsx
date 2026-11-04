import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

/* ---- toasts ---- */

interface Toast {
  id: number;
  text: string;
  kind: "success" | "error";
}

const ToastContext = createContext<(text: string, kind?: Toast["kind"]) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const remove = useCallback((id: number) => setToasts((items) => items.filter((item) => item.id !== id)), []);
  const show = useCallback(
    (text: string, kind: Toast["kind"] = "success") => {
      counter.current += 1;
      const id = counter.current;
      setToasts((items) => [...items, { id, text, kind }]);
      window.setTimeout(() => remove(id), 6000);
    },
    [remove],
  );
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast ${toast.kind === "error" ? "error" : ""}`}>
            <span>{toast.text}</span>
            <button type="button" aria-label="Close message" title="Close" onClick={() => remove(toast.id)}>
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/* ---- modal ---- */

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input, textarea, select, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);
  return (
    <div className="modal-back" role="presentation">
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <div className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="icon" aria-label="Close" title="Close" onClick={onClose}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ConfirmDelete({
  title,
  message,
  onConfirm,
  onClose,
}: {
  title: string;
  message: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <p>{message}</p>
      <div className="form-actions">
        <button type="button" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
            } finally {
              setBusy(false);
            }
          }}
        >
          Delete
        </button>
      </div>
    </Modal>
  );
}

/* ---- fields ---- */

interface FieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: (props: { id: string; "aria-invalid": boolean; "aria-describedby"?: string }) => ReactNode;
}

export function Field({ label, required, error, hint, children }: FieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required ? <span className="required">*</span> : null}
      </label>
      {children({ id, "aria-invalid": Boolean(error), "aria-describedby": error ? errorId : undefined })}
      {error ? (
        <p className="field-error" id={errorId}>
          {error}
        </p>
      ) : hint ? (
        <p className="field-hint">{hint}</p>
      ) : null}
    </div>
  );
}

export function PasswordInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-field">
      <input {...props} type={visible ? "text" : "password"} />
      <button
        type="button"
        aria-label={visible ? "Hide password" : "Show password"}
        title={visible ? "Hide password" : "Show password"}
        onClick={() => setVisible((value) => !value)}
      >
        {visible ? "Hide" : "Show"}
      </button>
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <div className="search-field">
      <input
        type="search"
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        maxLength={120}
        onChange={(event) => onChange(event.target.value)}
      />
      {value ? (
        <button type="button" aria-label="Clear search" title="Clear search" onClick={() => onChange("")}>
          ✕
        </button>
      ) : null}
    </div>
  );
}

/* ---- table ---- */

export interface Column<T> {
  header: string;
  cell: (item: T, serial: number) => ReactNode;
}

export function DataTable<T extends { id?: string | number }>({
  columns,
  load,
  searchPlaceholder,
  refreshKey,
  rowKey,
}: {
  columns: Column<T>[];
  load: (query: string) => Promise<{ items: T[]; total: number }>;
  searchPlaceholder: string;
  refreshKey?: number;
  rowKey?: (item: T, index: number) => string | number;
}) {
  const [search, setSearch] = useState("");
  const [typed, setTyped] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [data, setData] = useState<{ items: T[]; total: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(typed.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [typed]);

  const query = useMemo(() => new URLSearchParams({ page: String(page), size: String(size), search }).toString(), [page, size, search]);

  useEffect(() => {
    let current = true;
    load(query)
      .then((result) => {
        if (current) {
          setData(result);
          setError("");
        }
      })
      .catch((problem: Error) => {
        if (current) setError(problem.message);
      });
    return () => {
      current = false;
    };
  }, [query, load, refreshKey]);

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="card">
      <div className="table-tools">
        <SearchInput value={typed} onChange={setTyped} placeholder={searchPlaceholder} />
        <span className="muted">Total Records: {total.toLocaleString("en-IN")}</span>
      </div>
      {error ? <div className="notice error">{error}</div> : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">SR. No.</th>
              {columns.map((column) => (
                <th scope="col" key={column.header}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data && data.items.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="muted">
                  No records found
                </td>
              </tr>
            ) : null}
            {data?.items.map((item, index) => (
              <tr key={rowKey ? rowKey(item, index) : (item.id ?? index)}>
                <td>{(page - 1) * size + index + 1}</td>
                {columns.map((column) => (
                  <td key={column.header}>{column.cell(item, (page - 1) * size + index + 1)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <label className="switch-row">
          Records per page:
          <select
            value={size}
            onChange={(event) => {
              setSize(Number(event.target.value));
              setPage(1);
            }}
          >
            {[10, 20, 50, 100].map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <div className="controls">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="muted">
            Page {page} of {pages}
          </span>
          <button type="button" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
