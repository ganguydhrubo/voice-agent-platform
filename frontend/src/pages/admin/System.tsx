import { useEffect, useState } from "react";
import { api } from "../../api";
import { Field, useToast } from "../../components/ui";

type Values = Record<string, unknown>;

interface SystemData {
  hardware: Values;
  plan: Values;
  live: Values;
  llm_healthy: boolean;
  model_error: string;
  ram_used_percent: number;
  cpu_percent: number;
}

function label(key: string): string {
  const words = key.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function Rows({ values }: { values: Values }) {
  return (
    <ul className="side-list">
      {Object.entries(values).map(([key, value]) => (
        <li key={key}>
          <span>{label(key)}:</span> <span>{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
        </li>
      ))}
    </ul>
  );
}

export function System() {
  const [data, setData] = useState<SystemData | null>(null);
  const [days, setDays] = useState("");
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [problem, setProblem] = useState("");
  const toast = useToast();

  useEffect(() => {
    api<SystemData>("/api/admin/system")
      .then(setData)
      .catch((issue: Error) => setProblem(issue.message));
    api<{ transcript_retention_days: number }>("/api/admin/settings")
      .then((result) => {
        setDays(String(result.transcript_retention_days));
        setSaved(String(result.transcript_retention_days));
      })
      .catch((issue: Error) => setProblem(issue.message));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!/^\d{1,4}$/.test(days.trim()) || Number(days) > 3650) {
      setError("Transcript Retention must be a number from 0 to 3,650 days.");
      return;
    }
    setError("");
    try {
      const result = await api<{ message: string }>("/api/admin/settings", {
        method: "PUT",
        json: { transcript_retention_days: Number(days) },
      });
      setSaved(days);
      toast(result.message);
    } catch (issue) {
      setError((issue as Error).message);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>System</h1>
      </div>
      {problem ? <div className="notice error">{problem}</div> : null}
      {data?.model_error ? <div className="notice warning">{data.model_error}</div> : null}
      <div className="grid two">
        <section className="card">
          <h2>Retention</h2>
          <form onSubmit={save} noValidate>
            <Field label="Transcript Retention (days)" required error={error} hint="0 keeps no transcripts. Audio is never stored.">
              {(props) => <input {...props} inputMode="numeric" maxLength={4} placeholder="Enter Transcript Retention" value={days} onChange={(event) => setDays(event.target.value)} />}
            </Field>
            <div className="form-actions">
              <button type="button" onClick={() => { setDays(saved); setError(""); }}>
                Cancel
              </button>
              <button type="submit" className="primary">
                Update Settings
              </button>
            </div>
          </form>
        </section>
        {data ? (
          <>
            <section className="card">
              <h2>Health</h2>
              <ul className="side-list">
                <li>
                  <span>Language model:</span> <span>{data.llm_healthy ? "Running" : "Not running"}</span>
                </li>
                <li>
                  <span>Memory used:</span> <span>{data.ram_used_percent}%</span>
                </li>
                <li>
                  <span>Processor used:</span> <span>{data.cpu_percent}%</span>
                </li>
              </ul>
              <Rows values={data.live} />
            </section>
            <section className="card">
              <h2>Hardware</h2>
              <Rows values={data.hardware} />
            </section>
            <section className="card">
              <h2>Chosen plan</h2>
              <Rows values={data.plan} />
            </section>
          </>
        ) : null}
      </div>
    </>
  );
}
