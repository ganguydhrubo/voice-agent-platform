import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { AgentCard } from "../api";
import { ConfirmDelete, useToast } from "../components/ui";
import { Waveform } from "../components/Waveform";
import { VoiceClient } from "../voice/client";
import type { ConversationState, MicStatus, TranscriptLine } from "../voice/client";

interface Stored {
  token: string;
  agent: AgentCard;
  language: string;
  voice: string | null;
  mode: "voice" | "text";
  keepHistory: boolean;
}

const STATE_LABELS: Record<ConversationState, string> = {
  idle: "Ready",
  connecting: "Connecting",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  reconnecting: "Reconnecting",
  ended: "Conversation ended",
  error: "Connection problem",
};

const MIC_LABELS: Record<MicStatus, string> = {
  unknown: "Not started",
  requesting: "Waiting for permission",
  granted: "On",
  denied: "Blocked",
  missing: "Not found",
  unsupported: "Not available",
  off: "Muted",
};

function upsert(lines: TranscriptLine[], line: TranscriptLine): TranscriptLine[] {
  const index = lines.findIndex((item) => item.id === line.id);
  if (index < 0) return [...lines, line];
  const copy = [...lines];
  copy[index] = line;
  return copy;
}

export function Talk() {
  const { id = "" } = useParams();
  const stored = useMemo<Stored | null>(() => {
    const raw = sessionStorage.getItem(`conversation-${id}`);
    return raw ? (JSON.parse(raw) as Stored) : null;
  }, [id]);
  const toast = useToast();
  const client = useRef<VoiceClient | null>(null);
  const transcriptEnd = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<ConversationState>("idle");
  const [mic, setMic] = useState<MicStatus>(stored?.mode === "text" ? "off" : "unknown");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [partial, setPartial] = useState("");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [language, setLanguage] = useState(stored?.language ?? "en");
  const [voice, setVoice] = useState(stored?.voice ?? "");
  const [muted, setMuted] = useState(false);
  const [spoken, setSpoken] = useState(stored?.mode !== "text");
  const [timings, setTimings] = useState<Record<string, number | string | boolean> | null>(null);
  const [asking, setAsking] = useState(false);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    if (!stored) return undefined;
    const voiceClient = new VoiceClient({
      onState: setState,
      onMic: setMic,
      onPartial: setPartial,
      onLine: (line) => setLines((items) => upsert(items, line)),
      onInterrupted: () => setPartial(""),
      onError: setError,
      onNotice: (code) => {
        if (code === "approved_text") setNotice("The language model is busy, so this answer was read from the approved documents.");
      },
      onEscalation: (severity) =>
        setNotice(severity === "emergency" ? "This has been marked as urgent for our team." : "A member of our team has been asked to follow up."),
      onTimings: setTimings,
      onLanguage: (next, nextVoice) => {
        setLanguage(next);
        setVoice(nextVoice ?? "");
      },
    });
    client.current = voiceClient;
    voiceClient.start({ id, token: stored.token, mode: stored.mode }).catch((problem: Error) => setError(problem.message));
    return () => voiceClient.release();
  }, [id, stored]);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView?.({ block: "nearest" });
  }, [lines, partial]);

  const levelNode = useCallback(() => {
    const voiceClient = client.current;
    if (!voiceClient) return null;
    return state === "speaking" ? voiceClient.speakerLevelNode : voiceClient.microphoneLevelNode;
  }, [state]);

  if (!stored) {
    return (
      <div className="card">
        <h1>This conversation is not available</h1>
        <p>It was started in another tab or has ended.</p>
        <Link className="button primary" to="/">
          Start Conversation
        </Link>
      </div>
    );
  }

  const live = !["ended", "error"].includes(state);
  const voices = stored.agent.languages.find((item) => item.code === language)?.voices ?? [];

  function send(event: React.FormEvent) {
    event.preventDefault();
    const text = typed.trim();
    if (!text) return;
    client.current?.sendText(text);
    setTyped("");
  }

  async function deleteConversation() {
    try {
      await api(`/api/public/conversations/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${stored?.token}` } });
      sessionStorage.removeItem(`conversation-${id}`);
      setDeleted(true);
      setLines([]);
      toast("Conversation deleted successfully.");
    } catch (problem) {
      toast((problem as Error).message, "error");
    }
    setAsking(false);
  }

  return (
    <div className="talk">
      <section className="card talk-stage" aria-label="Conversation">
        <div className="talk-head">
          <div>
            <h1 style={{ fontSize: "1.3rem" }}>
              {stored.agent.name}, {stored.agent.organisation}
            </h1>
            <span className="muted">{stored.agent.industry}. AI assistant, not a person.</span>
          </div>
          <span className="status-pill" data-state={state} role="status" data-testid="state">
            {STATE_LABELS[state]}
          </span>
        </div>

        <Waveform getNode={levelNode} active={state === "listening" || state === "speaking"} />

        {error ? <div className="notice error">{error}</div> : null}
        {notice ? <div className="notice warning">{notice}</div> : null}

        <div className="transcript" aria-live="polite" data-testid="transcript">
          {lines.map((line) => (
            <div key={line.id} className={`bubble ${line.role === "user" ? "user" : "agent"}`} data-role={line.role}>
              {line.text}
              {line.interrupted ? <span className="meta">Interrupted</span> : null}
              {line.sources?.length ? (
                <span className="meta">
                  Source: {line.sources[0].title}
                  {line.sources[0].section ? `, ${line.sources[0].section}` : ""}
                </span>
              ) : null}
            </div>
          ))}
          {partial ? (
            <div className="bubble user partial" data-testid="partial">
              {partial}
            </div>
          ) : null}
          <div ref={transcriptEnd} />
        </div>

        <form className="text-entry" onSubmit={send}>
          <input
            aria-label="Type your question"
            placeholder="Type your question"
            value={typed}
            maxLength={500}
            disabled={!live || state === "connecting" || state === "reconnecting"}
            onChange={(event) => setTyped(event.target.value)}
          />
          <button type="submit" disabled={!live || !typed.trim()}>
            Send
          </button>
        </form>

        <div className="controls">
          <button type="button" disabled={state !== "speaking" && state !== "thinking"} onClick={() => client.current?.interrupt()}>
            Interrupt
          </button>
          {spoken ? (
            <button
              type="button"
              disabled={!live || mic === "denied" || mic === "missing" || mic === "unsupported"}
              onClick={() => {
                client.current?.setMuted(!muted);
                setMuted(!muted);
              }}
            >
              {muted ? "Unmute Microphone" : "Mute Microphone"}
            </button>
          ) : null}
          <button
            type="button"
            disabled={!live}
            onClick={() => {
              client.current?.setMode(spoken ? "text" : "voice").catch((problem: Error) => setError(problem.message));
              setSpoken(!spoken);
            }}
          >
            {spoken ? "Switch to Text Mode" : "Switch to Voice Mode"}
          </button>
          <button type="button" className="danger" disabled={!live} onClick={() => client.current?.end()}>
            End Conversation
          </button>
          {!live ? (
            <Link className="button primary" to="/">
              New Conversation
            </Link>
          ) : null}
        </div>
      </section>

      <aside className="grid" style={{ alignContent: "start" }}>
        <div className="card">
          <h2>Settings</h2>
          <div className="field">
            <label htmlFor="talk-language">Language</label>
            <select
              id="talk-language"
              value={language}
              disabled={!live}
              onChange={(event) => {
                setLanguage(event.target.value);
                client.current?.setLanguage(event.target.value);
              }}
            >
              {stored.agent.languages.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="talk-voice">Voice</label>
            <select
              id="talk-voice"
              value={voice}
              disabled={!live}
              onChange={(event) => {
                setVoice(event.target.value);
                client.current?.setVoice(event.target.value);
              }}
            >
              {voices.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <ul className="side-list">
            <li>
              <span>Microphone:</span> <span data-testid="mic">{MIC_LABELS[mic]}</span>
            </li>
            <li>
              <span>Transcript kept:</span> <span>{stored.keepHistory ? "Yes" : "No"}</span>
            </li>
            <li>
              <span>Audio stored:</span> <span>No</span>
            </li>
          </ul>
        </div>

        {timings ? (
          <details className="card" data-testid="timings">
            <summary>Timing of the last reply</summary>
            <ul className="side-list">
              {Object.entries(timings)
                .filter(([key]) => key.endsWith("_ms"))
                .map(([key, value]) => (
                  <li key={key}>
                    <span>{key.replace("_ms", "").replaceAll("_", " ")}:</span> <span>{Math.round(Number(value))} ms</span>
                  </li>
                ))}
            </ul>
          </details>
        ) : null}

        {!live && stored.keepHistory && !deleted ? (
          <div className="card">
            <h2>Your data</h2>
            <p className="muted">You can delete this transcript now.</p>
            <button type="button" className="danger" onClick={() => setAsking(true)}>
              Delete Transcript
            </button>
          </div>
        ) : null}
      </aside>

      {asking ? (
        <ConfirmDelete
          title="Delete Transcript"
          message="Are you sure you want to delete the transcript of this conversation? This cannot be undone."
          onConfirm={deleteConversation}
          onClose={() => setAsking(false)}
        />
      ) : null}
    </div>
  );
}
