import { useCallback, useEffect, useState } from "react";
import { api, formatDateTime } from "../../api";
import type { Paged } from "../../api";
import { useSession } from "../../App";
import { ConfirmDelete, DataTable, Modal, useToast } from "../../components/ui";
import type { Column } from "../../components/ui";

interface ConversationRow {
  id: string;
  agent: string;
  industry: string;
  language: string;
  mode: string;
  keep_history: number;
  messages: number;
  started_at: string;
  ended_at: string | null;
}

interface Message {
  role: string;
  text: string;
  interrupted: boolean;
  created_at: string;
}

export function Conversations() {
  const [refresh, setRefresh] = useState(0);
  const [viewing, setViewing] = useState<ConversationRow | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [removing, setRemoving] = useState<ConversationRow | null>(null);
  const { user } = useSession();
  const toast = useToast();
  const load = useCallback((query: string) => api<Paged<ConversationRow>>(`/api/admin/conversations?${query}`), []);

  async function open(row: ConversationRow) {
    try {
      const result = await api<{ messages: Message[] }>(`/api/admin/conversations/${row.id}`);
      setMessages(result.messages);
      setViewing(row);
    } catch (error) {
      toast((error as Error).message, "error");
    }
  }

  const canDelete = user?.role === "admin" || user?.role === "owner";
  const columns: Column<ConversationRow>[] = [
    { header: "Agent", cell: (row) => `${row.agent} (${row.industry})` },
    { header: "Language", cell: (row) => row.language.toUpperCase() },
    { header: "Mode", cell: (row) => (row.mode === "voice" ? "Voice" : "Text") },
    { header: "Messages", cell: (row) => row.messages },
    { header: "Started", cell: (row) => formatDateTime(row.started_at) },
    { header: "Ended", cell: (row) => formatDateTime(row.ended_at) },
    {
      header: canDelete ? "Actions" : "Action",
      cell: (row) => (
        <div className="row-actions">
          <button type="button" className="icon" title="View conversation" onClick={() => open(row)}>
            View
          </button>
          {canDelete ? (
            <button type="button" className="icon delete" title="Delete conversation" onClick={() => setRemoving(row)}>
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
        <h1>Conversations</h1>
      </div>
      <DataTable columns={columns} load={load} searchPlaceholder="Search Agent or Industry" refreshKey={refresh} />
      {viewing ? (
        <Modal title={`Conversation with ${viewing.agent}`} onClose={() => setViewing(null)} wide>
          {messages.length === 0 ? <p className="muted">No records found</p> : null}
          <div className="transcript" style={{ maxHeight: "60vh" }}>
            {messages.map((message, index) => (
              <div key={index} className={`bubble ${message.role === "user" ? "user" : "agent"}`}>
                {message.text}
                <span className="meta">
                  {formatDateTime(message.created_at)}
                  {message.interrupted ? ", interrupted" : ""}
                </span>
              </div>
            ))}
          </div>
        </Modal>
      ) : null}
      {removing ? (
        <ConfirmDelete
          title="Delete Conversation"
          message={`Are you sure you want to delete the conversation with ${removing.agent} from ${formatDateTime(removing.started_at)}?`}
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              const result = await api<{ message: string }>(`/api/admin/conversations/${removing.id}`, { method: "DELETE" });
              toast(result.message);
              setRefresh((value) => value + 1);
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

interface EscalationRow {
  id: string;
  agent: string;
  industry: string;
  rule: string;
  severity: string;
  status: string;
  created_at: string;
}

export function Escalations() {
  const [refresh, setRefresh] = useState(0);
  const toast = useToast();
  const load = useCallback((query: string) => api<Paged<EscalationRow>>(`/api/admin/escalations?${query}`), []);

  async function close(row: EscalationRow) {
    try {
      const result = await api<{ message: string }>(`/api/admin/escalations/${row.id}/close`, { method: "POST" });
      toast(result.message);
      setRefresh((value) => value + 1);
    } catch (error) {
      toast((error as Error).message, "error");
    }
  }

  const columns: Column<EscalationRow>[] = [
    { header: "Agent", cell: (row) => `${row.agent} (${row.industry})` },
    { header: "Rule", cell: (row) => row.rule },
    { header: "Severity", cell: (row) => <span className={`badge ${row.severity === "emergency" ? "bad" : ""}`}>{row.severity}</span> },
    { header: "Status", cell: (row) => <span className={`badge ${row.status === "open" ? "bad" : "good"}`}>{row.status}</span> },
    { header: "Created", cell: (row) => formatDateTime(row.created_at) },
    {
      header: "Action",
      cell: (row) =>
        row.status === "open" ? (
          <button type="button" className="icon" title="Close escalation" onClick={() => close(row)}>
            Close
          </button>
        ) : (
          "-"
        ),
    },
  ];

  return (
    <>
      <div className="page-head">
        <h1>Escalations</h1>
      </div>
      <DataTable columns={columns} load={load} searchPlaceholder="Search Agent, Rule or Severity" refreshKey={refresh} />
    </>
  );
}

interface AuditRow {
  id: number;
  actor: string;
  action: string;
  target: string;
  ip: string;
  created_at: string;
}

export function AuditLog() {
  const load = useCallback((query: string) => api<Paged<AuditRow>>(`/api/admin/audit-log?${query}`), []);
  const columns: Column<AuditRow>[] = [
    { header: "Who", cell: (row) => row.actor },
    { header: "Action", cell: (row) => row.action.replaceAll("_", " ") },
    { header: "Target", cell: (row) => row.target || "-" },
    { header: "IP Address", cell: (row) => row.ip || "-" },
    { header: "Date and Time", cell: (row) => formatDateTime(row.created_at) },
  ];
  return (
    <>
      <div className="page-head">
        <h1>Audit Log</h1>
      </div>
      <DataTable columns={columns} load={load} searchPlaceholder="Search Who or Action" />
    </>
  );
}

const STAGE_LABELS: Record<string, string> = {
  speech_ms: "Length of caller's speech",
  stt_final_ms: "Final transcript ready",
  retrieval_ms: "Knowledge search",
  llm_first_token_ms: "First word from language model",
  tts_first_audio_ms: "First speech ready",
  first_audio_sent_ms: "First audio sent",
  first_audible_ms: "First audible reply",
  total_ms: "Whole turn",
};

export function Latency() {
  const [data, setData] = useState<{ turns: number; stages: Record<string, { p50: number; p95: number; p99: number; count: number }> } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<NonNullable<typeof data>>("/api/admin/latency")
      .then(setData)
      .catch((problem: Error) => setError(problem.message));
  }, []);
  const stages = Object.entries(data?.stages ?? {});
  return (
    <>
      <div className="page-head">
        <h1>Latency</h1>
        {data ? <span className="muted">From the last {data.turns.toLocaleString("en-IN")} real turns</span> : null}
      </div>
      {error ? <div className="notice error">{error}</div> : null}
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Stage</th>
              <th scope="col">Median (p50)</th>
              <th scope="col">p95</th>
              <th scope="col">p99</th>
              <th scope="col">Samples</th>
            </tr>
          </thead>
          <tbody>
            {data && stages.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  No records found
                </td>
              </tr>
            ) : null}
            {stages.map(([key, stage]) => (
              <tr key={key}>
                <td>{STAGE_LABELS[key] ?? key}</td>
                <td>{stage.p50.toLocaleString("en-IN")} ms</td>
                <td>{stage.p95.toLocaleString("en-IN")} ms</td>
                <td>{stage.p99.toLocaleString("en-IN")} ms</td>
                <td>{stage.count.toLocaleString("en-IN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
