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

const TABS = [
  { key: "docs", label: "Documents" },
  { key: "internal", label: "Internal users" },
  { key: "external", label: "External visitors" },
];

const STATUS_LABEL = {
  queued: "Queued",
  parsing: "Parsing",
  chunking: "Chunking",
  embedding: "Embedding",
  ready: "Ready",
  failed: "Failed",
};

export default function AdminPage() {
  const [me, setMe] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [email, setEmail] = useState("admin@nexus.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [tab, setTab] = useState("docs");
  const [docs, setDocs] = useState([]);
  const [internals, setInternals] = useState([]);
  const [externals, setExternals] = useState([]);
  const [newEmail, setNewEmail] = useState("");
  const [newPass, setNewPass] = useState("");
  const [uploading, setUploading] = useState(false);
  const [creatingUser, setCreatingUser] = useState(false);
  const [togglingId, setTogglingId] = useState(null);
  const [removingId, setRemovingId] = useState(null);

  async function loadMe() {
    try {
      const d = await api("/auth/me");
      if (d.user.role !== "admin") throw new Error("Admin only");
      setMe(d.user);
    } catch {
      setMe(null);
    } finally {
      setCheckingAuth(false);
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
    setSigningIn(true);
    try {
      await api("/auth/admin/login", { method: "POST", json: { email, password } });
      await loadMe();
    } catch (err) {
      setError(err.message);
    } finally {
      setSigningIn(false);
    }
  }

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    const vis = document.getElementById("vis").value;
    if (vis) fd.append("visibility", vis);
    try {
      const res = await fetch("/api/admin/documents", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": csrf(), "X-Nexus-Site": "admin" },
        body: fd,
      });
      if (!res.ok) setError("Upload failed");
      await refresh();
    } finally {
      e.target.value = "";
      setUploading(false);
    }
  }

  async function removeDoc(id) {
    if (!confirm("Remove this document from the knowledge base?")) return;
    setRemovingId(id);
    try {
      await api(`/admin/documents/${id}`, { method: "DELETE" });
      await refresh();
    } finally {
      setRemovingId(null);
    }
  }

  async function createUser(e) {
    e.preventDefault();
    setCreatingUser(true);
    try {
      await api("/admin/users/internal", { method: "POST", json: { email: newEmail, password: newPass } });
      setNewEmail("");
      setNewPass("");
      await refresh();
    } finally {
      setCreatingUser(false);
    }
  }

  async function toggleUser(u) {
    setTogglingId(u.id);
    try {
      await api(`/admin/users/${u.id}/${u.is_active ? "disable" : "enable"}`, { method: "POST" });
      await refresh();
    } finally {
      setTogglingId(null);
    }
  }

  if (checkingAuth) {
    return (
      <div className="nx-checking">
        <div className="nx-spinner" />
        <span>Checking your session…</span>
      </div>
    );
  }

  if (!me) {
    return (
      <main className="nx-auth-wrap">
        <div className="nx-auth-card">
          <div className="nx-brand">
            <span className="nx-brand-mark">N</span>
            <div>
              <h1 className="nx-brand-text">Nexus</h1>
              <p className="nx-brand-sub">Administration console for knowledge base ingestion and access control.</p>
            </div>
          </div>
          <form onSubmit={login} className="nx-form">
            <label className="nx-field">
              <span>Email</span>
              <input
                className="nx-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@organization.com"
                autoComplete="username"
              />
            </label>
            <label className="nx-field">
              <span>Password</span>
              <input
                className="nx-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </label>
            <button className="nx-btn nx-btn-primary" disabled={signingIn}>
              {signingIn ? "Signing in…" : "Sign in"}
            </button>
            {error && <p className="nx-error">{error}</p>}
          </form>
        </div>
      </main>
    );
  }

  return (
    <div className="nx-app">
      <div className="nx-header-rule" />
      <header className="nx-header">
        <div className="nx-header-inner">
          <div className="nx-header-brand">
            <span className="nx-brand-mark small">N</span>
            <h1>
              Nexus<span>Administration</span>
            </h1>
          </div>
          <div className="nx-header-meta">
            {me.must_change_password && <span className="nx-badge-warn">Change the bootstrap password</span>}
            <span className="nx-user-email">{me.email}</span>
          </div>
        </div>
        <nav className="nx-nav">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`nx-nav-btn${tab === t.key ? " active" : ""}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="nx-main">
        {tab === "docs" && (
          <section>
            <div className="nx-section-head">
              <div>
                <h2>Documents</h2>
                <p>Files ingested into the knowledge base and their processing status.</p>
              </div>
            </div>
            <div className="nx-card">
              <div className="nx-toolbar">
                <select id="vis" defaultValue="" className="nx-input nx-select">
                  <option value="">Auto-classify</option>
                  <option value="generic">Generic</option>
                  <option value="internal">Internal</option>
                  <option value="restricted_pii">Restricted (PII)</option>
                </select>
                <label className="nx-upload-label">
                  {uploading ? "Uploading…" : "Upload document"}
                  <input type="file" hidden onChange={upload} disabled={uploading} />
                </label>
              </div>

              {docs.length === 0 ? (
                <div className="nx-empty">
                  <div className="nx-empty-mark">N</div>
                  <p>No documents yet. Upload a file to start building the knowledge base.</p>
                </div>
              ) : (
                <div className="nx-table-scroll">
                  <table className="nx-table">
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
                          <td className="nx-col-file">{d.filename}</td>
                          <td>
                            <span className={`nx-pill nx-pill-${d.visibility}`}>
                              {d.visibility}
                              {d.visibility_override && <span className="nx-pill-star">*</span>}
                            </span>
                          </td>
                          <td>
                            <div className={`nx-status-line${d.status === "failed" ? " is-failed" : ""}`}>
                              <span className={`nx-status-dot is-${d.status === "ready" || d.status === "failed" ? d.status : "active"}`} />
                              <span>
                                {STATUS_LABEL[d.status] || d.status} · {d.progress_step} {d.progress_pct}%
                              </span>
                            </div>
                            <div className="nx-progress">
                              <div
                                className={`nx-progress-bar${d.status === "ready" ? " is-ready" : ""}${d.status === "failed" ? " is-failed" : ""}`}
                                style={{ width: `${d.progress_pct}%` }}
                              />
                            </div>
                            {d.error && <div className="nx-doc-error">{d.error}</div>}
                          </td>
                          <td className="nx-num">{d.chunk_count}</td>
                          <td>
                            <button
                              className="nx-btn nx-btn-danger nx-btn-sm"
                              onClick={() => removeDoc(d.id)}
                              disabled={removingId === d.id}
                            >
                              {removingId === d.id ? "Removing…" : "Remove"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}

        {tab === "internal" && (
          <section>
            <div className="nx-section-head">
              <div>
                <h2>Internal users</h2>
                <p>Staff accounts with access to the full knowledge base.</p>
              </div>
            </div>
            <div className="nx-card">
              <form onSubmit={createUser} className="nx-form-inline">
                <input
                  className="nx-input"
                  placeholder="Email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  required
                />
                <input
                  className="nx-input"
                  placeholder="Temporary password (12+ characters)"
                  value={newPass}
                  onChange={(e) => setNewPass(e.target.value)}
                  required
                  minLength={12}
                />
                <button className="nx-btn nx-btn-primary" disabled={creatingUser}>
                  {creatingUser ? "Creating…" : "Create"}
                </button>
              </form>

              {internals.length === 0 ? (
                <div className="nx-empty">
                  <div className="nx-empty-mark">N</div>
                  <p>No internal users yet.</p>
                </div>
              ) : (
                <div className="nx-table-scroll">
                  <table className="nx-table">
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
                          <td className="nx-col-file">{u.email}</td>
                          <td>
                            <span className={`nx-yn ${u.is_active ? "is-yes" : "is-no"}`}>
                              {u.is_active ? "Yes" : "No"}
                            </span>
                          </td>
                          <td className="nx-num">{u.query_count}</td>
                          <td>
                            <button
                              className="nx-btn nx-btn-ghost nx-btn-sm"
                              onClick={() => toggleUser(u)}
                              disabled={togglingId === u.id}
                            >
                              {togglingId === u.id ? "Working…" : u.is_active ? "Disable" : "Enable"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}

        {tab === "external" && (
          <section>
            <div className="nx-section-head">
              <div>
                <h2>External visitors</h2>
                <p>Visitor accounts with scoped access to public-facing content.</p>
              </div>
            </div>
            <div className="nx-card">
              {externals.length === 0 ? (
                <div className="nx-empty">
                  <div className="nx-empty-mark">N</div>
                  <p>No external visitors yet.</p>
                </div>
              ) : (
                <div className="nx-table-scroll">
                  <table className="nx-table">
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
                          <td className="nx-col-file">{u.email}</td>
                          <td className="nx-num">{u.last_seen_at ? new Date(u.last_seen_at).toLocaleString() : "—"}</td>
                          <td className="nx-num">{u.query_count}</td>
                          <td>
                            <span className={`nx-yn ${u.is_active ? "is-yes" : "is-no"}`}>
                              {u.is_active ? "Yes" : "No"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}