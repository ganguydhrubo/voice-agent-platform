import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { User } from "../api";
import { useSession } from "../App";
import { Field, PasswordInput, useToast } from "../components/ui";

const REMEMBER_KEY = "remembered-email";
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{10,128}$/;
const PASSWORD_RULE = "Password must be 10 to 128 characters with at least one letter and one number.";

function readRemembered(): string {
  try {
    return localStorage.getItem(REMEMBER_KEY) ?? "";
  } catch {
    return "";
  }
}

function storeRemembered(email: string | null): void {
  try {
    if (email) localStorage.setItem(REMEMBER_KEY, email);
    else localStorage.removeItem(REMEMBER_KEY);
  } catch {
    // Remember Me only pre-fills a field, so a blocked store changes nothing else.
  }
}

export function LogIn() {
  const remembered = readRemembered();
  const [email, setEmail] = useState(remembered);
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(Boolean(remembered));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const { refresh, user } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const target = (location.state as { from?: string } | null)?.from ?? "/admin";

  useEffect(() => {
    if (user) navigate(target, { replace: true });
  }, [user, navigate, target]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!email.trim()) found.email = "Email ID is required.";
    else if (!EMAIL_PATTERN.test(email.trim())) found.email = "Enter a valid Email ID.";
    if (!password) found.password = "Password is required.";
    setErrors(found);
    setProblem("");
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await api<{ user: User }>("/api/auth/login", { method: "POST", json: { email: email.trim(), password, remember } });
      storeRemembered(remember ? email.trim() : null);
      await refresh();
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card auth-card" onSubmit={submit} noValidate>
      <h1>Log In</h1>
      {problem ? <div className="notice error">{problem}</div> : null}
      <Field label="Email ID" required error={errors.email}>
        {(props) => (
          <input {...props} type="email" placeholder="Enter Email ID" autoComplete="username" maxLength={120} value={email} onChange={(event) => setEmail(event.target.value)} />
        )}
      </Field>
      <Field label="Password" required error={errors.password}>
        {(props) => (
          <PasswordInput {...props} placeholder="Enter Password" autoComplete="current-password" maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />
        )}
      </Field>
      <div className="auth-links">
        <label className="switch-row">
          <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
          Remember Me
        </label>
        <Link to="/forgot-password">Forgot Password</Link>
      </div>
      <div className="form-actions">
        <Link className="button" to="/">
          Cancel
        </Link>
        <button type="submit" className="primary" disabled={busy}>
          Log In
        </button>
      </div>
    </form>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim()) return setError("Email ID is required.");
    if (!EMAIL_PATTERN.test(email.trim())) return setError("Enter a valid Email ID.");
    setError("");
    setBusy(true);
    try {
      const result = await api<{ message: string }>("/api/auth/forgot-password", { method: "POST", json: { email: email.trim() } });
      setDone(result.message);
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
    return undefined;
  }

  return (
    <form className="card auth-card" onSubmit={submit} noValidate>
      <h1>Forgot Password</h1>
      {done ? <div className="notice">{done}</div> : <p className="muted">This install has no mail service, so your administrator gives you the reset link from the server.</p>}
      <Field label="Email ID" required error={error}>
        {(props) => <input {...props} type="email" placeholder="Enter Email ID" maxLength={120} value={email} onChange={(event) => setEmail(event.target.value)} />}
      </Field>
      <div className="form-actions">
        <Link className="button" to="/login">
          Cancel
        </Link>
        <button type="submit" className="primary" disabled={busy}>
          Send Reset Link
        </button>
      </div>
    </form>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const toast = useToast();
  const navigate = useNavigate();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!password) found.password = "New Password is required.";
    else if (!PASSWORD_PATTERN.test(password)) found.password = PASSWORD_RULE;
    if (!confirm) found.confirm = "Confirm Password is required.";
    else if (confirm !== password) found.confirm = "Confirm Password must match New Password.";
    setErrors(found);
    setProblem("");
    if (Object.keys(found).length) return;
    try {
      const result = await api<{ message: string }>("/api/auth/reset-password", {
        method: "POST",
        json: { token: params.get("token") ?? "", new_password: password },
      });
      toast(result.message);
      navigate("/login");
    } catch (error) {
      setProblem((error as Error).message);
    }
  }

  return (
    <form className="card auth-card" onSubmit={submit} noValidate>
      <h1>Reset Password</h1>
      {problem ? <div className="notice error">{problem}</div> : null}
      <Field label="New Password" required error={errors.password}>
        {(props) => <PasswordInput {...props} placeholder="Enter New Password" maxLength={128} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />}
      </Field>
      <Field label="Confirm Password" required error={errors.confirm}>
        {(props) => <PasswordInput {...props} placeholder="Enter Confirm Password" maxLength={128} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} />}
      </Field>
      <div className="form-actions">
        <Link className="button" to="/login">
          Cancel
        </Link>
        <button type="submit" className="primary">
          Reset Password
        </button>
      </div>
    </form>
  );
}

export function ChangePassword() {
  const empty = { current: "", next: "", confirm: "" };
  const [values, setValues] = useState(empty);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toast = useToast();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!values.current) found.current = "Current Password is required.";
    if (!values.next) found.next = "New Password is required.";
    else if (!PASSWORD_PATTERN.test(values.next)) found.next = PASSWORD_RULE;
    else if (values.next === values.current) found.next = "New Password must be different from Current Password.";
    if (!values.confirm) found.confirm = "Confirm Password is required.";
    else if (values.confirm !== values.next) found.confirm = "Confirm Password must match New Password.";
    setErrors(found);
    if (Object.keys(found).length) return;
    try {
      const result = await api<{ message: string }>("/api/auth/change-password", {
        method: "POST",
        json: { current_password: values.current, new_password: values.next },
      });
      toast(result.message);
      setValues(empty);
    } catch (error) {
      setErrors({ current: (error as Error).message });
    }
  }

  const set = (key: keyof typeof empty) => (event: React.ChangeEvent<HTMLInputElement>) => setValues({ ...values, [key]: event.target.value });

  return (
    <form className="card" style={{ maxWidth: 460 }} onSubmit={submit} noValidate>
      <h1>Change Password</h1>
      <Field label="Current Password" required error={errors.current}>
        {(props) => <PasswordInput {...props} placeholder="Enter Current Password" maxLength={128} autoComplete="current-password" value={values.current} onChange={set("current")} />}
      </Field>
      <Field label="New Password" required error={errors.next}>
        {(props) => <PasswordInput {...props} placeholder="Enter New Password" maxLength={128} autoComplete="new-password" value={values.next} onChange={set("next")} />}
      </Field>
      <Field label="Confirm Password" required error={errors.confirm}>
        {(props) => <PasswordInput {...props} placeholder="Enter Confirm Password" maxLength={128} autoComplete="new-password" value={values.confirm} onChange={set("confirm")} />}
      </Field>
      <div className="form-actions">
        <button type="button" onClick={() => { setValues(empty); setErrors({}); }}>
          Cancel
        </button>
        <button type="submit" className="primary">
          Change Password
        </button>
      </div>
    </form>
  );
}
