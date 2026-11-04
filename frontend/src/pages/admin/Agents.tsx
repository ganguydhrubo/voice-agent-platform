import { useCallback, useState } from "react";
import { api, formatDate } from "../../api";
import type { Paged } from "../../api";
import { useSession } from "../../App";
import { ConfirmDelete, DataTable, Field, Modal, useToast } from "../../components/ui";
import type { Column } from "../../components/ui";

interface AgentRow {
  id: string;
  slug: string;
  name: string;
  industry: string;
  organisation: string;
  languages: string[];
  published: boolean;
  version: number;
  updated_at: string;
}

type Language = "en" | "hi" | "bn";
const LANGUAGES: { code: Language; label: string }[] = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "bn", label: "Bengali" },
];

interface Config {
  slug: string;
  industry: string;
  name: string;
  role: string;
  organisation: string;
  personality: string;
  system_instructions: string;
  languages: Language[];
  greeting: Partial<Record<Language, string>>;
  no_answer: Partial<Record<Language, string>>;
  knowledge_bases: string[];
  business_policies: string[];
  min_confidence: number;
  memory: { keep_turns: number; store_transcripts: boolean };
  [key: string]: unknown;
}

const BLANK: Config = {
  slug: "",
  industry: "",
  name: "",
  role: "",
  organisation: "",
  personality: "",
  system_instructions: "",
  languages: ["en"],
  greeting: {},
  no_answer: {},
  knowledge_bases: [],
  business_policies: [],
  min_confidence: 0.62,
  memory: { keep_turns: 6, store_transcripts: true },
};

const lines = (value: string) => value.split("\n").map((line) => line.trim()).filter(Boolean);

function AgentForm({ agentId, initial, onClose, onSaved }: { agentId: string | null; initial: Config; onClose: () => void; onSaved: () => void }) {
  const [values, setValues] = useState<Config>(initial);
  const [policies, setPolicies] = useState(initial.business_policies.join("\n"));
  const [bases, setBases] = useState(initial.knowledge_bases.join("\n"));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (patch: Partial<Config>) => setValues({ ...values, ...patch });

  function validate(): Record<string, string> {
    const found: Record<string, string> = {};
    const required: [keyof Config, string][] = [
      ["name", "Agent Name"],
      ["role", "Role"],
      ["organisation", "Organisation"],
      ["personality", "Personality"],
      ["system_instructions", "System Instructions"],
    ];
    if (!agentId) {
      required.unshift(["industry", "Industry"]);
      if (!/^[a-z0-9-]{2,40}$/.test(values.slug)) found.slug = "Slug must be 2 to 40 lower-case letters, numbers or hyphens.";
    }
    for (const [key, label] of required) {
      const text = String(values[key] ?? "").trim();
      if (!text) found[key as string] = `${label} is required.`;
      else if (text.length < 2) found[key as string] = `${label} must have at least 2 characters.`;
    }
    if (values.languages.length === 0) found.languages = "Choose at least one language.";
    for (const language of values.languages) {
      const name = LANGUAGES.find((item) => item.code === language)?.label;
      if (!values.greeting[language]?.trim()) found[`greeting-${language}`] = `Greeting in ${name} is required.`;
      if (!values.no_answer[language]?.trim()) found[`no-answer-${language}`] = `No Answer Message in ${name} is required.`;
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
      const body = { ...values, business_policies: lines(policies), knowledge_bases: lines(bases) };
      const result = await api<{ message: string }>(agentId ? `/api/admin/agents/${agentId}` : "/api/admin/agents", {
        method: agentId ? "PUT" : "POST",
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

  const toggleLanguage = (code: Language, on: boolean) =>
    set({ languages: on ? [...values.languages, code] : values.languages.filter((item) => item !== code) });

  return (
    <Modal title={agentId ? `Edit Agent ${initial.name}` : "Add Agent"} onClose={onClose} wide>
      <form onSubmit={submit} noValidate>
        {problem ? <div className="notice error">{problem}</div> : null}
        <div className="grid two">
          {agentId ? null : (
            <>
              <Field label="Slug" required error={errors.slug} hint="Used in links. It cannot change later.">
                {(props) => <input {...props} placeholder="Enter Slug" maxLength={40} value={values.slug} onChange={(event) => set({ slug: event.target.value })} />}
              </Field>
              <Field label="Industry" required error={errors.industry}>
                {(props) => <input {...props} placeholder="Enter Industry" maxLength={60} value={values.industry} onChange={(event) => set({ industry: event.target.value })} />}
              </Field>
            </>
          )}
          <Field label="Agent Name" required error={errors.name}>
            {(props) => <input {...props} placeholder="Enter Agent Name" maxLength={60} value={values.name} onChange={(event) => set({ name: event.target.value })} />}
          </Field>
          <Field label="Role" required error={errors.role}>
            {(props) => <input {...props} placeholder="Enter Role" maxLength={120} value={values.role} onChange={(event) => set({ role: event.target.value })} />}
          </Field>
          <Field label="Organisation" required error={errors.organisation}>
            {(props) => <input {...props} placeholder="Enter Organisation" maxLength={120} value={values.organisation} onChange={(event) => set({ organisation: event.target.value })} />}
          </Field>
          <Field label="Minimum Retrieval Confidence" hint="From 0 to 1. Below this, the agent says it does not know.">
            {(props) => <input {...props} type="number" min={0} max={1} step={0.05} value={values.min_confidence} onChange={(event) => set({ min_confidence: Number(event.target.value) })} />}
          </Field>
        </div>
        <Field label="Personality" required error={errors.personality}>
          {(props) => <textarea {...props} placeholder="Enter Personality" maxLength={400} value={values.personality} onChange={(event) => set({ personality: event.target.value })} />}
        </Field>
        <Field label="System Instructions" required error={errors.system_instructions}>
          {(props) => <textarea {...props} placeholder="Enter System Instructions" maxLength={2000} value={values.system_instructions} onChange={(event) => set({ system_instructions: event.target.value })} />}
        </Field>
        <div className="field">
          <span className="label-text">
            Languages<span className="required">*</span>
          </span>
          <div className="controls">
            {LANGUAGES.map((item) => (
              <label key={item.code} className="switch-row">
                <input type="checkbox" checked={values.languages.includes(item.code)} onChange={(event) => toggleLanguage(item.code, event.target.checked)} />
                {item.label}
              </label>
            ))}
          </div>
          {errors.languages ? <p className="field-error">{errors.languages}</p> : null}
        </div>
        {values.languages.map((code) => {
          const name = LANGUAGES.find((item) => item.code === code)?.label;
          return (
            <div className="grid two" key={code}>
              <Field label={`Greeting (${name})`} required error={errors[`greeting-${code}`]}>
                {(props) => <textarea {...props} placeholder={`Enter Greeting in ${name}`} maxLength={400} value={values.greeting[code] ?? ""} onChange={(event) => set({ greeting: { ...values.greeting, [code]: event.target.value } })} />}
              </Field>
              <Field label={`No Answer Message (${name})`} required error={errors[`no-answer-${code}`]}>
                {(props) => <textarea {...props} placeholder={`Enter No Answer Message in ${name}`} maxLength={400} value={values.no_answer[code] ?? ""} onChange={(event) => set({ no_answer: { ...values.no_answer, [code]: event.target.value } })} />}
              </Field>
            </div>
          );
        })}
        <div className="grid two">
          <Field label="Business Policies" hint="One policy on each line.">
            {(props) => <textarea {...props} placeholder="Enter Business Policies" maxLength={4000} value={policies} onChange={(event) => setPolicies(event.target.value)} />}
          </Field>
          <Field label="Knowledge Bases" hint="One knowledge base name on each line.">
            {(props) => <textarea {...props} placeholder="Enter Knowledge Bases" maxLength={1000} value={bases} onChange={(event) => setBases(event.target.value)} />}
          </Field>
        </div>
        <p className="muted">Emergency rules, restricted actions and evaluation tests stay as they are when you save this form.</p>
        <div className="form-actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {agentId ? "Update Agent" : "Add Agent"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

interface TestResult {
  id: string;
  language: string;
  question: string;
  passed: boolean;
  reply: string;
  failures: string[];
}

function TestResults({ agent, onClose }: { agent: AgentRow; onClose: () => void }) {
  const [result, setResult] = useState<{ passed: number; total: number; results: TestResult[] } | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setProblem("");
    try {
      setResult(await api(`/api/admin/agents/${agent.id}/evaluate`, { method: "POST" }));
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Test Agent ${agent.name}`} onClose={onClose} wide>
      <p className="muted">This asks the agent its saved test questions. Answers come from the live language model, so it can take a minute.</p>
      {problem ? <div className="notice error">{problem}</div> : null}
      {result ? (
        <>
          <p>
            <strong>
              {result.passed} of {result.total} tests passed
            </strong>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Question</th>
                  <th scope="col">Language</th>
                  <th scope="col">Result</th>
                  <th scope="col">Answer</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((item) => (
                  <tr key={item.id}>
                    <td>{item.question}</td>
                    <td>{item.language.toUpperCase()}</td>
                    <td>
                      <span className={`badge ${item.passed ? "good" : "bad"}`}>{item.passed ? "Passed" : "Failed"}</span>
                    </td>
                    <td>
                      {item.reply || "-"}
                      {item.failures.length ? <p className="field-error">{item.failures.join(" ")}</p> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      <div className="form-actions">
        <button type="button" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="primary" disabled={busy} onClick={run}>
          {busy ? "Running Tests" : "Run Tests"}
        </button>
      </div>
    </Modal>
  );
}

export function Agents() {
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState<{ id: string | null; config: Config } | null>(null);
  const [removing, setRemoving] = useState<AgentRow | null>(null);
  const [testing, setTesting] = useState<AgentRow | null>(null);
  const { user } = useSession();
  const toast = useToast();
  const load = useCallback((query: string) => api<Paged<AgentRow>>(`/api/admin/agents?${query}`), []);
  const reload = () => setRefresh((value) => value + 1);
  const canEdit = user?.role !== "viewer";
  const canPublish = user?.role === "admin" || user?.role === "owner";

  async function edit(row: AgentRow) {
    try {
      const result = await api<{ config: Config }>(`/api/admin/agents/${row.id}`);
      setEditing({ id: row.id, config: result.config });
    } catch (error) {
      toast((error as Error).message, "error");
    }
  }

  async function publish(row: AgentRow) {
    try {
      const result = await api<{ message: string }>(`/api/admin/agents/${row.id}/publish?published=${!row.published}`, { method: "POST" });
      toast(result.message);
      reload();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  }

  const columns: Column<AgentRow>[] = [
    { header: "Industry", cell: (row) => row.industry },
    { header: "Agent Name", cell: (row) => row.name },
    { header: "Organisation", cell: (row) => row.organisation },
    { header: "Languages", cell: (row) => row.languages.join(", ").toUpperCase() },
    { header: "Status", cell: (row) => <span className={`badge ${row.published ? "good" : ""}`}>{row.published ? "Published" : "Draft"}</span> },
    { header: "Updated", cell: (row) => formatDate(row.updated_at) },
    {
      header: "Actions",
      cell: (row) => (
        <div className="row-actions">
          {canEdit ? (
            <button type="button" className="icon" title={`Edit ${row.name}`} onClick={() => edit(row)}>
              Edit
            </button>
          ) : null}
          {canEdit ? (
            <button type="button" className="icon" title={`Test ${row.name}`} onClick={() => setTesting(row)}>
              Test
            </button>
          ) : null}
          {canPublish ? (
            <button type="button" className="icon" title={row.published ? `Unpublish ${row.name}` : `Publish ${row.name}`} onClick={() => publish(row)}>
              {row.published ? "Unpublish" : "Publish"}
            </button>
          ) : null}
          {canPublish ? (
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
        <h1>Agents</h1>
        {canEdit ? (
          <button type="button" className="primary" onClick={() => setEditing({ id: null, config: BLANK })}>
            Add Agent
          </button>
        ) : null}
      </div>
      <DataTable columns={columns} load={load} searchPlaceholder="Search Agent Name or Industry" refreshKey={refresh} />
      {editing ? (
        <AgentForm
          key={editing.id ?? "new"}
          agentId={editing.id}
          initial={editing.config}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      ) : null}
      {testing ? <TestResults agent={testing} onClose={() => setTesting(null)} /> : null}
      {removing ? (
        <ConfirmDelete
          title="Delete Agent"
          message={`Are you sure you want to delete Agent ${removing.name} for ${removing.industry}?`}
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              const result = await api<{ message: string }>(`/api/admin/agents/${removing.id}`, { method: "DELETE" });
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
