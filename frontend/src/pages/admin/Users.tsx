import { useCallback, useState } from "react";
import { api, formatDate, roleRank } from "../../api";
import type { Paged } from "../../api";
import { useSession } from "../../App";
import { ConfirmDelete, DataTable, Field, Modal, PasswordInput, useToast } from "../../components/ui";
import type { Column } from "../../components/ui";

interface UserRow {
  id: string;
  full_name: string;
  email: string;
  role: "owner" | "admin" | "editor" | "viewer";
  is_active: boolean;
  created_at: string;
}

const EMPTY = { full_name: "", email: "", role: "viewer", password: "", is_active: true };
const NAME_PATTERN = /^[^\W\d_][\p{L}\p{M} .'-]{1,79}$/u;
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{10,128}$/;

function UserForm({ user, onClose, onSaved }: { user: UserRow | null; onClose: () => void; onSaved: () => void }) {
  const [values, setValues] = useState(user ? { ...EMPTY, ...user, password: "" } : EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    const name = values.full_name.trim();
    if (!name) found.full_name = "Full Name is required.";
    else if (name.length < 2 || !NAME_PATTERN.test(name)) found.full_name = "Full Name must contain letters only.";
    if (!values.email.trim()) found.email = "Email ID is required.";
    else if (!EMAIL_PATTERN.test(values.email.trim())) found.email = "Enter a valid Email ID.";
    if (!user && !values.password) found.password = "Password is required.";
    else if (!user && !PASSWORD_PATTERN.test(values.password)) {
      found.password = "Password must be 10 to 128 characters with at least one letter and one number.";
    }
    return found;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    setProblem("");
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      const body = { ...values, full_name: values.full_name.trim(), email: values.email.trim(), password: user ? null : values.password };
      const result = await api<{ message: string }>(user ? `/api/admin/users/${user.id}` : "/api/admin/users", {
        method: user ? "PUT" : "POST",
        json: body,
      });
      toast(result.message);
      onSaved();
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={user ? "Edit User" : "Add User"} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        {problem ? <div className="notice error">{problem}</div> : null}
        <Field label="Full Name" required error={errors.full_name}>
          {(props) => <input {...props} placeholder="Enter Full Name" maxLength={80} value={values.full_name} onChange={(event) => setValues({ ...values, full_name: event.target.value })} />}
        </Field>
        <Field label="Email ID" required error={errors.email}>
          {(props) => <input {...props} type="email" placeholder="Enter Email ID" maxLength={120} value={values.email} onChange={(event) => setValues({ ...values, email: event.target.value })} />}
        </Field>
        <Field label="Role" required>
          {(props) => (
            <select {...props} value={values.role} onChange={(event) => setValues({ ...values, role: event.target.value })}>
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </select>
          )}
        </Field>
        {user ? null : (
          <Field label="Password" required error={errors.password}>
            {(props) => <PasswordInput {...props} placeholder="Enter Password" maxLength={128} autoComplete="new-password" value={values.password} onChange={(event) => setValues({ ...values, password: event.target.value })} />}
          </Field>
        )}
        <label className="switch-row">
          <input type="checkbox" checked={values.is_active} onChange={(event) => setValues({ ...values, is_active: event.target.checked })} />
          Active
        </label>
        <div className="form-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {user ? "Update User" : "Add User"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function Users() {
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [removing, setRemoving] = useState<UserRow | null>(null);
  const { user: me } = useSession();
  const toast = useToast();
  const load = useCallback((query: string) => api<Paged<UserRow>>(`/api/admin/users?${query}`), []);
  const reload = () => setRefresh((value) => value + 1);

  const columns: Column<UserRow>[] = [
    { header: "Full Name", cell: (row) => row.full_name },
    { header: "Email ID", cell: (row) => row.email },
    { header: "Role", cell: (row) => row.role.charAt(0).toUpperCase() + row.role.slice(1) },
    { header: "Status", cell: (row) => <span className={`badge ${row.is_active ? "good" : "bad"}`}>{row.is_active ? "Active" : "Inactive"}</span> },
    { header: "Created", cell: (row) => formatDate(row.created_at) },
    {
      header: "Actions",
      cell: (row) => {
        const protectedUser = row.role === "owner" || row.id === me?.id || roleRank[row.role] > roleRank[me?.role ?? "viewer"];
        if (protectedUser) return "-";
        return (
          <div className="row-actions">
            <button type="button" className="icon" title={`Edit ${row.full_name}`} onClick={() => setEditing(row)}>
              Edit
            </button>
            <button type="button" className="icon delete" title={`Delete ${row.full_name}`} onClick={() => setRemoving(row)}>
              Delete
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <>
      <div className="page-head">
        <h1>Users</h1>
        <button type="button" className="primary" onClick={() => setEditing("new")}>
          Add User
        </button>
      </div>
      <DataTable columns={columns} load={load} searchPlaceholder="Search Full Name or Email ID" refreshKey={refresh} />
      {editing ? (
        <UserForm
          key={editing === "new" ? "new" : editing.id}
          user={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      ) : null}
      {removing ? (
        <ConfirmDelete
          title="Delete User"
          message={`Are you sure you want to delete User ${removing.full_name}?`}
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              const result = await api<{ message: string }>(`/api/admin/users/${removing.id}`, { method: "DELETE" });
              toast(result.message);
              reload();
            } catch (error) {
              toast((error as Error).message, "error");
            }
            setRemoving(null);
          }}
        />
      ) : null}
    </>
  );
}
