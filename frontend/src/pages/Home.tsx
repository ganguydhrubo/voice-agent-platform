import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { AgentCard } from "../api";
import { Field, SearchInput } from "../components/ui";

export function Home() {
  const [agents, setAgents] = useState<AgentCard[]>([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string>("healthcare");
  const [language, setLanguage] = useState("en");
  const [voice, setVoice] = useState("");
  const [keepHistory, setKeepHistory] = useState(true);
  const [mode, setMode] = useState<"voice" | "text">("voice");
  const [search, setSearch] = useState("");
  const [starting, setStarting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api<{ agents: AgentCard[] }>("/api/public/agents")
      .then((result) => setAgents(result.agents))
      .catch((problem: Error) => setError(problem.message));
  }, []);

  const agent = agents.find((item) => item.slug === selected);
  const languages = agent?.languages ?? [];
  const voices = languages.find((item) => item.code === language)?.voices ?? [];
  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return agents.filter((item) => !term || `${item.industry} ${item.organisation}`.toLowerCase().includes(term));
  }, [agents, search]);

  useEffect(() => {
    setVoice(voices[0]?.id ?? "");
    // Only a change of language or agent resets the voice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, selected, agents]);

  async function start() {
    if (!agent) return;
    setStarting(true);
    setError("");
    try {
      const conversation = await api<{ id: string; token: string; voice: string | null }>("/api/public/conversations", {
        method: "POST",
        json: { agent: agent.slug, language, voice, mode, keep_history: keepHistory },
      });
      sessionStorage.setItem(
        `conversation-${conversation.id}`,
        JSON.stringify({ token: conversation.token, agent, language, voice: conversation.voice, mode, keepHistory }),
      );
      navigate(`/talk/${conversation.id}`);
    } catch (problem) {
      setError((problem as Error).message);
      setStarting(false);
    }
  }

  return (
    <>
      <section className="hero">
        <h1>Talk to an AI agent in your browser</h1>
        <p>
          Choose an industry, press Start Conversation and speak naturally. No phone number is needed, and the speech,
          language model and knowledge all run on this server.
        </p>
      </section>
      {error ? <div className="notice error">{error}</div> : null}
      <div className="table-tools">
        <SearchInput value={search} onChange={setSearch} placeholder="Search Industry" />
      </div>
      <div className="industry-grid" role="group" aria-label="Choose an industry">
        {visible.map((item) => (
          <button
            key={item.slug}
            type="button"
            className="industry-card"
            aria-pressed={item.slug === selected}
            onClick={() => setSelected(item.slug)}
          >
            <strong>{item.industry}</strong>
            <span>
              {item.name}, {item.organisation}
            </span>
          </button>
        ))}
        {agents.length > 0 && visible.length === 0 ? <p className="muted">No records found</p> : null}
      </div>

      <section className="card start-panel" aria-label="Conversation settings">
        <Field label="Language">
          {(props) => (
            <select {...props} value={language} onChange={(event) => setLanguage(event.target.value)}>
              {languages.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Voice">
          {(props) => (
            <select {...props} value={voice} onChange={(event) => setVoice(event.target.value)}>
              {voices.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="How to talk">
          {(props) => (
            <select {...props} value={mode} onChange={(event) => setMode(event.target.value as "voice" | "text")}>
              <option value="voice">Speak with microphone</option>
              <option value="text">Type only</option>
            </select>
          )}
        </Field>
        <div>
          <label className="switch-row">
            <input type="checkbox" checked={keepHistory} onChange={(event) => setKeepHistory(event.target.checked)} />
            Keep a transcript of this conversation
          </label>
          <p className="field-hint">Audio is never stored.</p>
        </div>
        <button type="button" className="primary" disabled={!agent || starting} onClick={start}>
          Start Conversation
        </button>
      </section>
    </>
  );
}
