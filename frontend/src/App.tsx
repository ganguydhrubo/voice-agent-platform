import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, roleRank } from "./api";
import type { User } from "./api";
import { ToastProvider } from "./components/ui";
import { Agents } from "./pages/admin/Agents";
import { AuditLog, Conversations, Escalations, Latency } from "./pages/admin/Records";
import { Dashboard } from "./pages/admin/Dashboard";
import { Knowledge } from "./pages/admin/Knowledge";
import { System } from "./pages/admin/System";
import { Users } from "./pages/admin/Users";
import { ChangePassword, ForgotPassword, LogIn, ResetPassword } from "./pages/Auth";
import { Home } from "./pages/Home";
import { Faqs, Privacy } from "./pages/Info";
import { Talk } from "./pages/Talk";

interface Session {
  user: User | null;
  ready: boolean;
  refresh: () => Promise<void>;
  logOut: () => Promise<void>;
}

const SessionContext = createContext<Session>({ user: null, ready: false, refresh: async () => undefined, logOut: async () => undefined });
export const useSession = () => useContext(SessionContext);

function ScrollToTop() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 320);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  if (!visible) return null;
  return (
    <button type="button" className="scroll-top" aria-label="Scroll to top" title="Scroll to top" onClick={() => window.scrollTo({ top: 0 })}>
      ▲
    </button>
  );
}

function Layout() {
  const { user, logOut } = useSession();
  const location = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [location.pathname]);
  return (
    <>
      <header className="site-header">
        <div className="site-header-inner">
          <Link to="/" className="brand">
            <img src="/favicon.svg" alt="" />
            Voice Agent Platform
          </Link>
          <nav className="site-nav" aria-label="Main">
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/faqs">FAQs</NavLink>
            <NavLink to="/privacy">Privacy Policy</NavLink>
            {user ? <NavLink to="/admin">Admin</NavLink> : <NavLink to="/login">Log In</NavLink>}
            {user ? (
              <button type="button" onClick={logOut}>
                Log Out
              </button>
            ) : null}
          </nav>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="site-footer">
        <div className="site-footer-inner">
          <span>© {new Date().getFullYear()} Voice Agent Platform. All rights reserved.</span>
          <Link to="/privacy">Privacy Policy</Link>
        </div>
      </footer>
      <ScrollToTop />
    </>
  );
}

const ADMIN_LINKS: { to: string; label: string; end?: boolean; min: User["role"] }[] = [
  { to: "/admin", label: "Dashboard", end: true, min: "viewer" },
  { to: "/admin/agents", label: "Agents", min: "viewer" },
  { to: "/admin/knowledge", label: "Knowledge", min: "viewer" },
  { to: "/admin/conversations", label: "Conversations", min: "viewer" },
  { to: "/admin/escalations", label: "Escalations", min: "viewer" },
  { to: "/admin/latency", label: "Latency", min: "viewer" },
  { to: "/admin/users", label: "Users", min: "admin" },
  { to: "/admin/audit-log", label: "Audit Log", min: "admin" },
  { to: "/admin/system", label: "System", min: "admin" },
  { to: "/admin/change-password", label: "Change Password", min: "viewer" },
];

function AdminLayout() {
  const { user, ready } = useSession();
  const location = useLocation();
  if (!ready) return <p className="muted">Loading</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return (
    <div className="admin">
      <nav className="admin-nav card" aria-label="Admin">
        {ADMIN_LINKS.filter((item) => roleRank[user.role] >= roleRank[item.min]).map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div>
        <Outlet />
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="card">
      <h1>Page not found</h1>
      <p>The page you asked for does not exist.</p>
      <Link className="button primary" to="/">
        Go to Home
      </Link>
    </div>
  );
}

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      const result = await api<{ user: User | null }>("/api/auth/me");
      setUser(result.user);
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  const logOut = useCallback(async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    navigate("/");
  }, [navigate]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const session = useMemo(() => ({ user, ready, refresh, logOut }), [user, ready, refresh, logOut]);

  return (
    <SessionContext.Provider value={session}>
      <ToastProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="talk/:id" element={<Talk />} />
            <Route path="faqs" element={<Faqs />} />
            <Route path="privacy" element={<Privacy />} />
            <Route path="login" element={<LogIn />} />
            <Route path="forgot-password" element={<ForgotPassword />} />
            <Route path="reset-password" element={<ResetPassword />} />
            <Route path="admin" element={<AdminLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="agents" element={<Agents />} />
              <Route path="knowledge" element={<Knowledge />} />
              <Route path="conversations" element={<Conversations />} />
              <Route path="escalations" element={<Escalations />} />
              <Route path="latency" element={<Latency />} />
              <Route path="users" element={<Users />} />
              <Route path="audit-log" element={<AuditLog />} />
              <Route path="system" element={<System />} />
              <Route path="change-password" element={<ChangePassword />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </ToastProvider>
    </SessionContext.Provider>
  );
}
