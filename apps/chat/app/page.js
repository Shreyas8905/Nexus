"use client";

import { useEffect, useRef, useState } from "react";

function getCsrf() {
  const m = document.cookie.match(/(?:^|; )nexus_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}), "X-CSRF-Token": getCsrf() };
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const res = await fetch(`/api${path}`, { ...opts, headers, credentials: "include" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || res.statusText);
  return data;
}

export default function Page() {
  const [me, setMe] = useState(null);
  const [mode, setMode] = useState("external");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const scroller = useRef(null);

  useEffect(() => {
    api("/auth/me")
      .then((d) => setMe(d.user))
      .catch(() => setMe(null));
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function startExternal(e) {
    e.preventDefault();
    setError("");
    try {
      const d = await api("/auth/external", { method: "POST", json: { email } });
      setMe(d.user);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loginInternal(e) {
    e.preventDefault();
    setError("");
    try {
      const d = await api("/auth/login", { method: "POST", json: { email, password } });
      setMe(d.user);
    } catch (err) {
      setError(err.message);
    }
  }

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    let answer = "";
    setMessages((m) => [...m, { role: "assistant", text: "", citations: [] }]);
    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() },
        body: JSON.stringify({ message: text }),
      });
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          const line = part.replace(/^data:\s*/, "");
          if (!line) continue;
          const ev = JSON.parse(line);
          if (ev.type === "token") {
            answer += ev.text;
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { ...copy[copy.length - 1], text: answer };
              return copy;
            });
          }
          if (ev.type === "done") {
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = {
                ...copy[copy.length - 1],
                text: answer,
                citations: ev.citations || [],
                refused: ev.refused,
              };
              return copy;
            });
          }
        }
      }
    } catch (err) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", text: err.message || "Request failed" };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  if (!me) {
    return (
      <main style={wrap}>
        <header style={hero}>
          <div style={mark}>N</div>
          <div>
            <h1 style={h1}>Nexus</h1>
            <p style={sub}>Local knowledge. Intranet only.</p>
          </div>
        </header>
        <div style={card}>
          <div style={tabs}>
            <button style={tabBtn(mode === "external")} onClick={() => setMode("external")}>
              Visitor
            </button>
            <button style={tabBtn(mode === "internal")} onClick={() => setMode("internal")}>
              Internal
            </button>
          </div>
          {mode === "external" ? (
            <form onSubmit={startExternal} style={form}>
              <p style={hint}>Enter your email to start a generic-only session. Individual records are never disclosed.</p>
              <input style={inputEl} type="email" required placeholder="you@example.edu" value={email} onChange={(e) => setEmail(e.target.value)} />
              <button style={primary} type="submit">Begin chat</button>
            </form>
          ) : (
            <form onSubmit={loginInternal} style={form}>
              <p style={hint}>Accounts are created by an administrator.</p>
              <input style={inputEl} type="email" required placeholder="work email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input style={inputEl} type="password" required placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button style={primary} type="submit">Sign in</button>
            </form>
          )}
          {error && <p style={err}>{error}</p>}
        </div>
      </main>
    );
  }

  const internal = me.role === "internal";

  return (
    <main style={chatShell}>
      <header style={topbar}>
        <strong style={{ letterSpacing: "0.18em", color: "var(--gold)" }}>NEXUS</strong>
        <span style={{ color: "var(--muted)", fontSize: 13 }}>
          {internal ? "Internal · citations on" : "Visitor · generic sources only"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)" }}>{me.email}</span>
      </header>
      <div ref={scroller} style={thread}>
        {messages.length === 0 && (
          <div style={empty}>
            <h2 style={{ fontFamily: "var(--font)", fontWeight: 500, margin: "0 0 8px" }}>Ask the knowledge base</h2>
            <p style={{ color: "var(--muted)", margin: 0 }}>
              {internal
                ? "Answers include citations from ingested documents."
                : "You will only receive general information. Personal student or faculty records are blocked."}
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <article key={i} style={bubble(m.role, m.refused)}>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{m.text || (busy && i === messages.length - 1 ? "…" : "")}</div>
            {internal && m.citations?.length > 0 && (
              <div style={cites}>
                {m.citations.map((c, j) => (
                  <span key={j} style={chip}>
                    {c.title}
                    {c.page ? ` · p.${c.page}` : ""}
                    {c.sheet ? ` · ${c.sheet}` : ""}
                  </span>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
      <form onSubmit={send} style={composer}>
        <input
          style={{ ...inputEl, flex: 1 }}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Nexus…"
          disabled={busy}
        />
        <button style={primary} disabled={busy} type="submit">
          Send
        </button>
      </form>
    </main>
  );
}

const wrap = { maxWidth: 520, margin: "12vh auto", padding: 24 };
const hero = { display: "flex", gap: 16, alignItems: "center", marginBottom: 28 };
const mark = {
  width: 52,
  height: 52,
  borderRadius: 14,
  border: "1px solid var(--line)",
  display: "grid",
  placeItems: "center",
  color: "var(--gold)",
  fontFamily: "var(--font)",
  fontSize: 26,
};
const h1 = { margin: 0, fontFamily: "var(--font)", fontWeight: 500, fontSize: 36 };
const sub = { margin: "4px 0 0", color: "var(--muted)" };
const card = {
  background: "var(--bg-elev)",
  border: "1px solid var(--line)",
  borderRadius: 18,
  padding: 22,
};
const tabs = { display: "flex", gap: 8, marginBottom: 16 };
const tabBtn = (on) => ({
  flex: 1,
  padding: "8px 10px",
  borderRadius: 10,
  border: "1px solid var(--line)",
  background: on ? "rgba(212,175,106,0.16)" : "transparent",
  color: on ? "var(--gold-2)" : "var(--muted)",
  cursor: "pointer",
});
const form = { display: "flex", flexDirection: "column", gap: 10 };
const hint = { color: "var(--muted)", fontSize: 14, margin: "0 0 4px" };
const inputEl = {
  padding: "12px 14px",
  borderRadius: 12,
  border: "1px solid var(--line)",
  background: "#0b0f14",
  color: "var(--text)",
  outline: "none",
};
const primary = {
  padding: "12px 16px",
  borderRadius: 12,
  border: "none",
  background: "linear-gradient(180deg, var(--gold-2), var(--gold))",
  color: "#1a1408",
  fontWeight: 600,
  cursor: "pointer",
};
const err = { color: "var(--danger)", fontSize: 13 };
const chatShell = { height: "100vh", display: "flex", flexDirection: "column" };
const topbar = {
  display: "flex",
  gap: 16,
  alignItems: "center",
  padding: "14px 22px",
  borderBottom: "1px solid var(--line)",
};
const thread = { flex: 1, overflow: "auto", padding: "28px 18px 12px", maxWidth: 780, width: "100%", margin: "0 auto" };
const empty = { textAlign: "center", marginTop: "18vh" };
const bubble = (role, refused) => ({
  margin: "0 0 14px",
  padding: "14px 16px",
  borderRadius: role === "user" ? "16px 16px 6px 16px" : "16px 16px 16px 6px",
  marginLeft: role === "user" ? "18%" : 0,
  marginRight: role === "assistant" ? "8%" : 0,
  background: role === "user" ? "rgba(212,175,106,0.12)" : "var(--bg-elev)",
  border: `1px solid ${refused ? "rgba(224,122,110,0.45)" : "var(--line)"}`,
});
const cites = { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 };
const chip = {
  fontSize: 11,
  color: "var(--gold-2)",
  border: "1px solid var(--line)",
  borderRadius: 999,
  padding: "3px 8px",
};
const composer = {
  display: "flex",
  gap: 10,
  padding: 16,
  maxWidth: 780,
  width: "100%",
  margin: "0 auto 12px",
};
