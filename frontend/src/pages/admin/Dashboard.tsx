import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatNumber } from "../../api";

interface Overview {
  agents: number;
  published_agents: number;
  knowledge_bases: number;
  documents: number;
  conversations: number;
  open_escalations: number;
  users: number;
  live: { active: number; capacity: number; degraded: boolean };
}

export function Dashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Overview>("/api/admin/overview")
      .then(setData)
      .catch((problem: Error) => setError(problem.message));
  }, []);

  const cards: [string, number, string][] = data
    ? [
        ["Agents", data.agents, "/admin/agents"],
        ["Published Agents", data.published_agents, "/admin/agents"],
        ["Knowledge Bases", data.knowledge_bases, "/admin/knowledge"],
        ["Documents", data.documents, "/admin/knowledge"],
        ["Conversations", data.conversations, "/admin/conversations"],
        ["Open Escalations", data.open_escalations, "/admin/escalations"],
        ["Users", data.users, "/admin/users"],
      ]
    : [];

  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
        {data ? (
          <span className="muted">
            Live conversations: {data.live.active} of {data.live.capacity}
          </span>
        ) : null}
      </div>
      {error ? <div className="notice error">{error}</div> : null}
      {data?.live.degraded ? <div className="notice warning">The server is short of memory or busy, so live partial text is switched off for now.</div> : null}
      <div className="stat-grid">
        {cards.map(([label, value, to]) => (
          <Link key={label} to={to} className="card stat-card">
            <strong>{formatNumber(value)}</strong>
            {label}
          </Link>
        ))}
      </div>
    </>
  );
}
