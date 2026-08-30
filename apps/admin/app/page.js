"use client";

import { useEffect, useState } from "react";

function csrf() {
  const m = document.cookie.match(/(?:^|; )nexus_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function api(path, opts = {}) {
  const headers = { "X-CSRF-Token": csrf(), "X-Nexus-Site": "admin", ...(opts.headers || {}) };
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const res = await fetch(`/api${path}`, { credentials: "include", ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  return data;
}

const STEPS = ["queued", "parsing", "chunking", "embedding", "ready", "failed"];

export default function AdminPage() {
  const [me, setMe] = useState(null);
  const [email, setEmail] = useState("admin@nexus.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState("docs");
  const [docs, setDocs] = useState([]);
  const [internals, setInternals] = useState([]);
  const [externals, setExternals] = useState([]);
  const [newEmail, setNewEmail] = useState("");
  const [newPass, setNewPass] = useState("");

  async function loadMe() {
    try {
      const d = await api("/auth/me");
      if (d.user.role !== "admin") throw new Error("Admin only");
      setMe(d.user);
    } catch {
      setMe(null);
    }
  }

  async function refresh() {
    const [d, i, e] = await Promise.all([
      api("/admin/documents"),
      api("/admin/users/internal"),
      api("/admin/users/external"),
    ]);
    setDocs(d);
    setInternals(i);
    setExternals(e);
  }

  useEffect(() => {
    loadMe();
  }, []);

  useEffect(() => {
    if (!me) return;
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [me]);

  async function login(e) {
    e.preventDefault();
    setError("");
    try {
      await api("/auth/admin/login", { method: "POST", json: { email, password } });
      await loadMe();
    } catch (err) {
      setError(err.message);
    }
  }

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    const vis = document.getElementById("vis").value;
    if (vis) fd.append("visibility", vis);
    const res = await fetch("/api/admin/documents", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": csrf(), "X-Nexus-Site": "admin" },
      body: fd,
    });
    if (!res.ok) setError("Upload failed");
    e.target.value = "";
    await refresh();
  }

  async function removeDoc(id) {
    if (!confirm("Remove this document from the knowledge base?")) return;
    await api(`/admin/documents/${id}`, { method: "DELETE" });
    await refresh();
  }

  async function createUser(e) {
    e.preventDefault();
    await api("/admin/users/internal", { method: "POST", json: { email: newEmail, password: newPass } });
    setNewEmail("");
    setNewPass("");
    await refresh();
  }

  if (!me) {
    return (
      <main style={{ maxWidth: 380, margin: "18vh auto", padding: 24 }}>
        <h1 style={{ fontWeight: 560, letterSpacing: "0.08em" }}>NEXUS ADMIN</h1>
        <p style={{ color: "var(--muted)" }}>Minimal control plane for users and ingestion.</p>
        <form onSubmit={login} style={{ display: "grid", gap: 10 }}>
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" style={inp} />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" style={inp} />
          <button style={btn}>Sign in</button>
          {error && <p style={{ color: "var(--bad)" }}>{error}</p>}
        </form>
      </main>
    );
  }

  return (
    <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ display: "flex", gap: 16, alignItems: "baseline", marginBottom: 22 }}>
        <h1 style={{ margin: 0, fontSize: 22, letterSpacing: "0.12em" }}>NEXUS ADMIN</h1>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>{me.email}</span>
        {me.must_change_password && <span style={{ color: "var(--warn)", fontSize: 13 }}>Change the bootstrap password.</span>}
      </header>
      <nav style={{ display: "flex", gap: 8, marginBottom: 18 }}>
        {["docs", "internal", "external"].map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{ ...btn, background: tab === t ? "#1f6feb" : "#21262d" }}>
            {t === "docs" ? "Documents" : t === "internal" ? "Internal users" : "External visitors"}
          </button>
        ))}
      </nav>

      {tab === "docs" && (
        <section>
          <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "center" }}>
            <select id="vis" defaultValue="" style={inp}>
              <option value="">Auto-classify</option>
              <option value="generic">generic</option>
              <option value="internal">internal</option>
              <option value="restricted_pii">restricted_pii</option>
            </select>
            <label style={{ ...btn, display: "inline-block" }}>
              Upload
              <input type="file" hidden onChange={upload} />
            </label>
          </div>
          <table style={table}>
            <thead>
              <tr>
                <th>File</th>
                <th>Visibility</th>
                <th>Status</th>
                <th>Chunks</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>{d.filename}</td>
                  <td>{d.visibility}{d.visibility_override ? " *" : ""}</td>
                  <td>
                    <div style={{ fontSize: 12, color: d.status === "failed" ? "var(--bad)" : "var(--muted)" }}>
                      {d.status} · {d.progress_step} {d.progress_pct}%
                    </div>
                    <div style={bar}>
                      <div
                        style={{
                          width: `${d.progress_pct}%`,
                          height: 6,
                          background: d.status === "failed" ? "var(--bad)" : d.status === "ready" ? "var(--ok)" : "var(--accent)",
                          borderRadius: 99,
                        }}
                      />
                    </div>
                    {d.error && <div style={{ color: "var(--bad)", fontSize: 12 }}>{d.error}</div>}
                  </td>
                  <td>{d.chunk_count}</td>
                  <td>
                    <button style={{ ...btn, background: "#3d1f1f" }} onClick={() => removeDoc(d.id)}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "internal" && (
        <section>
          <form onSubmit={createUser} style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <input style={inp} placeholder="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} required />
            <input style={inp} placeholder="temp password (12+ chars)" value={newPass} onChange={(e) => setNewPass(e.target.value)} required minLength={12} />
            <button style={btn}>Create</button>
          </form>
          <table style={table}>
            <thead>
              <tr>
                <th>Email</th>
                <th>Active</th>
                <th>Queries</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {internals.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.is_active ? "yes" : "no"}</td>
                  <td>{u.query_count}</td>
                  <td>
                    <button
                      style={btn}
                      onClick={async () => {
                        await api(`/admin/users/${u.id}/${u.is_active ? "disable" : "enable"}`, { method: "POST" });
                        await refresh();
                      }}
                    >
                      {u.is_active ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "external" && (
        <table style={table}>
          <thead>
            <tr>
              <th>Email</th>
              <th>Last seen</th>
              <th>Queries</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {externals.map((u) => (
              <tr key={u.id}>
                <td>{u.email}</td>
                <td>{u.last_seen_at ? new Date(u.last_seen_at).toLocaleString() : "—"}</td>
                <td>{u.query_count}</td>
                <td>{u.is_active ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}

const inp = {
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid var(--line)",
  background: varPanel(),
  color: "var(--text)",
};
function varPanel() {
  return "#0e1116";
}
const btn = {
  padding: "10px 14px",
  borderRadius: 8,
  border: "none",
  background: "#1f6feb",
  color: "white",
  cursor: "pointer",
};
const table = { width: "100%", borderCollapse: "collapse" };
const bar = { background: "#21262d", borderRadius: 99, overflow: "hidden", marginTop: 6 };
