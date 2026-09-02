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

/* ---------------------------------------------------------------- */
/* Minimal markdown renderer (no external dependency).               */
/* Supports: headings, paragraphs, bold/italic, inline code, code    */
/* fences, links, blockquotes, ordered + unordered lists.            */
/* ---------------------------------------------------------------- */

function parseInline(str, keyPrefix) {
  const nodes = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let m;
  let key = 0;
  while ((m = regex.exec(str))) {
    if (m.index > lastIndex) nodes.push(str.slice(lastIndex, m.index));
    const token = m[0];
    if (token.startsWith("`")) {
      nodes.push(
        <code key={`${keyPrefix}${key++}`} style={mdInlineCode}>
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}${key++}`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      nodes.push(<em key={`${keyPrefix}${key++}`}>{token.slice(1, -1)}</em>);
    } else if (token.startsWith("[")) {
      const match = token.match(/\[([^\]]+)\]\(([^)]+)\)/);
      nodes.push(
        <a
          key={`${keyPrefix}${key++}`}
          href={match[2]}
          target="_blank"
          rel="noreferrer"
          style={mdLink}
        >
          {match[1]}
        </a>
      );
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < str.length) nodes.push(str.slice(lastIndex));
  return nodes;
}

function MdHeading({ level, children }) {
  const style = mdHeading(level);
  if (level <= 1) return <h3 style={style}>{children}</h3>;
  if (level === 2) return <h4 style={style}>{children}</h4>;
  if (level === 3) return <h5 style={style}>{children}</h5>;
  return <h6 style={style}>{children}</h6>;
}

function Markdown({ text }) {
  if (!text) return null;
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;
  let key = 0;
  let listBuffer = null;

  function flushList() {
    if (!listBuffer) return;
    const Tag = listBuffer.type === "ol" ? "ol" : "ul";
    blocks.push(
      <Tag key={`list-${key++}`} style={listBuffer.type === "ol" ? mdOl : mdUl}>
        {listBuffer.items.map((it, idx) => (
          <li key={idx} style={mdLi}>
            {parseInline(it, `li${key}-${idx}-`)}
          </li>
        ))}
      </Tag>
    );
    listBuffer = null;
  }

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim().startsWith("```")) {
      flushList();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      blocks.push(
        <pre key={`pre-${key++}`} style={mdPre}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const headerMatch = line.match(/^(#{1,4})\s+(.*)/);
    if (headerMatch) {
      flushList();
      blocks.push(
        <MdHeading key={`h-${key++}`} level={headerMatch[1].length}>
          {parseInline(headerMatch[2], `h${key}-`)}
        </MdHeading>
      );
      i++;
      continue;
    }

    if (line.trim().startsWith(">")) {
      flushList();
      const quoteLines = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote key={`bq-${key++}`} style={mdQuote}>
          {parseInline(quoteLines.join(" "), `bq${key}-`)}
        </blockquote>
      );
      continue;
    }

    const ulMatch = line.match(/^\s*[-*]\s+(.*)/);
    if (ulMatch) {
      if (!listBuffer || listBuffer.type !== "ul") {
        flushList();
        listBuffer = { type: "ul", items: [] };
      }
      listBuffer.items.push(ulMatch[1]);
      i++;
      continue;
    }

    const olMatch = line.match(/^\s*\d+\.\s+(.*)/);
    if (olMatch) {
      if (!listBuffer || listBuffer.type !== "ol") {
        flushList();
        listBuffer = { type: "ol", items: [] };
      }
      listBuffer.items.push(olMatch[1]);
      i++;
      continue;
    }

    if (line.trim() === "") {
      flushList();
      i++;
      continue;
    }

    flushList();
    const paraLines = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].trim().startsWith("```") &&
      !lines[i].match(/^(#{1,4})\s+/) &&
      !lines[i].trim().startsWith(">") &&
      !lines[i].match(/^\s*[-*]\s+/) &&
      !lines[i].match(/^\s*\d+\.\s+/)
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={`p-${key++}`} style={mdP}>
        {parseInline(paraLines.join(" "), `p${key}-`)}
      </p>
    );
  }
  flushList();
  return <>{blocks}</>;
}

/* ---------------------------------------------------------------- */

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
        <p style={footNote}>A private index of institutional documents, papers, and records.</p>
      </main>
    );
  }

  const internal = me.role === "internal";

  return (
    <main style={chatShell}>
      <header style={topbar}>
        <div style={brandRow}>
          <div style={markSmall}>N</div>
          <strong style={brandWord}>Nexus</strong>
        </div>
        <span style={statusPill(internal)}>
          {internal ? "Internal · citations on" : "Visitor · generic sources only"}
        </span>
        <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)" }}>{me.email}</span>
      </header>
      <div ref={scroller} style={thread}>
        {messages.length === 0 && (
          <div style={empty}>
            <h2 style={emptyTitle}>Ask the knowledge base</h2>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: 440, marginInline: "auto" }}>
              {internal
                ? "Answers include citations from ingested documents."
                : "You will only receive general information. Personal student or faculty records are blocked."}
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={row(m.role)}>
            <div style={avatar(m.role, m.refused)}>{m.role === "user" ? "U" : "N"}</div>
            <article style={bubble(m.role, m.refused)}>
              {m.role === "assistant" ? (
                m.text ? (
                  <Markdown text={m.text} />
                ) : busy && i === messages.length - 1 ? (
                  <span style={typing}>
                    <span style={dot(0)} />
                    <span style={dot(1)} />
                    <span style={dot(2)} />
                  </span>
                ) : null
              ) : (
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{m.text}</div>
              )}
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
          </div>
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
        <button style={{ ...primary, opacity: busy || !input.trim() ? 0.55 : 1 }} disabled={busy || !input.trim()} type="submit">
          Send
        </button>
      </form>
    </main>
  );
}

/* ---------------------------- layout / chrome styles ---------------------------- */

const wrap = { maxWidth: 480, margin: "12vh auto 0", padding: 24 };
const hero = { display: "flex", gap: 16, alignItems: "center", marginBottom: 28 };
const mark = {
  width: 52,
  height: 52,
  borderRadius: 12,
  border: "1px solid var(--line-strong)",
  background: "linear-gradient(160deg, var(--cobalt), var(--cobalt-deep))",
  display: "grid",
  placeItems: "center",
  color: "#fff",
  fontFamily: "var(--font-serif)",
  fontSize: 24,
  boxShadow: "0 6px 16px rgba(13, 58, 130, 0.18)",
};
const h1 = { margin: 0, fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: 32, color: "var(--text)" };
const sub = { margin: "4px 0 0", color: "var(--muted)", fontSize: 14 };
const card = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 16,
  padding: 24,
  boxShadow: "0 1px 2px rgba(20, 32, 51, 0.04), 0 12px 32px rgba(20, 32, 51, 0.06)",
};
const tabs = { display: "flex", gap: 6, marginBottom: 18, background: "var(--surface-2)", padding: 4, borderRadius: 10 };
const tabBtn = (on) => ({
  flex: 1,
  padding: "9px 10px",
  borderRadius: 8,
  border: "none",
  background: on ? "var(--surface)" : "transparent",
  color: on ? "var(--cobalt)" : "var(--muted)",
  fontWeight: on ? 600 : 500,
  fontSize: 14,
  boxShadow: on ? "0 1px 3px rgba(20,32,51,0.10)" : "none",
  cursor: "pointer",
  transition: "background 150ms ease, color 150ms ease",
});
const form = { display: "flex", flexDirection: "column", gap: 12 };
const hint = { color: "var(--muted)", fontSize: 13.5, lineHeight: 1.5, margin: "0 0 2px" };
const inputEl = {
  padding: "12px 14px",
  borderRadius: 10,
  border: "1px solid var(--line-strong)",
  background: "var(--surface)",
  color: "var(--text)",
  outline: "none",
  fontSize: 14.5,
  transition: "border-color 150ms ease, box-shadow 150ms ease",
};
const primary = {
  padding: "12px 16px",
  borderRadius: 10,
  border: "none",
  background: "linear-gradient(180deg, var(--cobalt), var(--cobalt-deep))",
  color: "#fff",
  fontWeight: 600,
  fontSize: 14.5,
  cursor: "pointer",
  transition: "opacity 150ms ease, transform 150ms ease",
};
const err = { color: "var(--danger)", fontSize: 13, margin: 0 };
const footNote = { textAlign: "center", color: "var(--muted)", fontSize: 12.5, marginTop: 18 };

const chatShell = { height: "100vh", display: "flex", flexDirection: "column", background: "var(--paper)" };
const topbar = {
  display: "flex",
  gap: 16,
  alignItems: "center",
  padding: "12px 22px",
  borderBottom: "1px solid var(--line)",
  background: "var(--surface)",
};
const brandRow = { display: "flex", alignItems: "center", gap: 10 };
const markSmall = {
  width: 30,
  height: 30,
  borderRadius: 8,
  background: "linear-gradient(160deg, var(--cobalt), var(--cobalt-deep))",
  color: "#fff",
  display: "grid",
  placeItems: "center",
  fontFamily: "var(--font-serif)",
  fontSize: 15,
};
const brandWord = { fontFamily: "var(--font-serif)", fontSize: 17, color: "var(--text)", fontWeight: 600 };
const statusPill = (internal) => ({
  fontSize: 12.5,
  color: internal ? "var(--green)" : "var(--muted)",
  background: internal ? "var(--green-tint)" : "var(--surface-2)",
  border: `1px solid ${internal ? "rgba(20,84,60,0.18)" : "var(--line)"}`,
  borderRadius: 999,
  padding: "4px 10px",
});

const thread = { flex: 1, overflow: "auto", padding: "30px 20px 12px", maxWidth: 820, width: "100%", margin: "0 auto" };
const empty = { textAlign: "center", marginTop: "16vh" };
const emptyTitle = { fontFamily: "var(--font-serif)", fontWeight: 600, fontSize: 22, margin: "0 0 8px", color: "var(--text)" };

const row = (role) => ({
  display: "flex",
  gap: 10,
  flexDirection: role === "user" ? "row-reverse" : "row",
  marginBottom: 16,
});
const avatar = (role, refused) => ({
  flexShrink: 0,
  width: 30,
  height: 30,
  borderRadius: 8,
  display: "grid",
  placeItems: "center",
  fontSize: 12.5,
  fontWeight: 700,
  marginTop: 2,
  color: role === "user" ? "var(--cobalt)" : "#fff",
  background: role === "user" ? "var(--cobalt-tint)" : refused ? "var(--danger)" : "var(--green)",
});
const bubble = (role, refused) => ({
  maxWidth: "78%",
  padding: "13px 16px",
  borderRadius: role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
  background: role === "user" ? "var(--cobalt-tint)" : "var(--surface)",
  border: `1px solid ${refused ? "rgba(168,50,31,0.30)" : role === "user" ? "rgba(0,71,171,0.16)" : "var(--line)"}`,
  fontFamily: "var(--font-serif)",
  fontSize: 15.5,
  color: "var(--text)",
  boxShadow: role === "assistant" ? "0 1px 2px rgba(20,32,51,0.04)" : "none",
});

const typing = { display: "inline-flex", gap: 4, padding: "4px 2px" };
const dot = (idx) => ({
  width: 6,
  height: 6,
  borderRadius: "50%",
  background: "var(--muted)",
  display: "inline-block",
  animation: `nexus-bounce 1.1s ${idx * 0.15}s infinite ease-in-out`,
});

const cites = { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 };
const chip = {
  fontFamily: "var(--font-sans)",
  fontSize: 11.5,
  color: "var(--green)",
  background: "var(--green-tint)",
  border: "1px solid rgba(20,84,60,0.18)",
  borderRadius: 999,
  padding: "3px 9px",
};

const composer = {
  display: "flex",
  gap: 10,
  padding: 16,
  maxWidth: 820,
  width: "100%",
  margin: "0 auto 14px",
};

/* ---------------------------- markdown styles ---------------------------- */

const mdP = { margin: "0 0 10px", lineHeight: 1.65 };
const mdHeading = (level) => ({
  fontFamily: "var(--font-serif)",
  fontWeight: 600,
  color: "var(--text)",
  margin: level <= 1 ? "4px 0 8px" : "10px 0 6px",
  lineHeight: 1.35,
});
const mdUl = { margin: "0 0 10px", paddingLeft: 22 };
const mdOl = { margin: "0 0 10px", paddingLeft: 22 };
const mdLi = { marginBottom: 4, lineHeight: 1.6 };
const mdQuote = {
  margin: "0 0 10px",
  padding: "4px 14px",
  borderLeft: "3px solid var(--cobalt)",
  color: "var(--muted)",
  fontStyle: "italic",
};
const mdPre = {
  margin: "0 0 10px",
  padding: "12px 14px",
  borderRadius: 10,
  background: "var(--surface-2)",
  border: "1px solid var(--line)",
  overflowX: "auto",
  fontFamily: "var(--font-mono)",
  fontSize: 13,
  lineHeight: 1.55,
};
const mdInlineCode = {
  fontFamily: "var(--font-mono)",
  fontSize: "0.88em",
  background: "var(--surface-2)",
  border: "1px solid var(--line)",
  borderRadius: 4,
  padding: "1px 5px",
};
const mdLink = { color: "var(--cobalt)", textDecoration: "underline", textUnderlineOffset: 2 };