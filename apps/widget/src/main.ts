/**
 * Unisona embeddable widget: chat + voice in a Shadow DOM bubble.
 *
 * <script src="https://api.example.com/widget/widget.js" data-agent="pk_..." data-api="https://api.example.com" async></script>
 * Optional: window.UnisonaSettings = { userId, userHash, name, email, phone, variables } for verified identity & memory.
 */
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

type Cfg = { name: string; business: string; greeting: string; widget: any; voice_enabled: boolean; chat_enabled: boolean };
type Msg = { role: string; text: string; options?: string[]; citations?: any[] };

const script = (document.currentScript as HTMLScriptElement) || document.querySelector("script[data-agent]");
const KEY = script?.dataset.agent || "";
const API = (script?.dataset.api || new URL(script?.src || location.href).origin).replace(/\/$/, "");
const settings: any = (window as any).UnisonaSettings || {};

function sid(): string {
  const k = `unisona_s_${KEY}`;
  let v = localStorage.getItem(k);
  if (!v) {
    v = Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(k, v);
  }
  return v;
}

function esc(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
}

function md(s: string) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|\n)[-•] (.+)/g, "$1• $2")
    .replace(/\n/g, "<br>");
}

const CSS = (c: string, side: string) => `
:host{all:initial}
*{box-sizing:border-box;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.launcher{position:fixed;${side}:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;z-index:2147483646;
 background:radial-gradient(circle at 30% 25%,#fff8,transparent 50%),conic-gradient(from 200deg,${c},#38bdf8,#f0abfc,${c});
 box-shadow:0 12px 30px -8px ${c}aa;transition:transform .2s}
.launcher:hover{transform:scale(1.06)}
.launcher svg{width:26px;height:26px;color:#fff}
.panel{position:fixed;${side}:20px;bottom:92px;width:380px;max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 120px);
 background:#fff;border-radius:20px;box-shadow:0 24px 70px -12px #0005;display:none;flex-direction:column;overflow:hidden;z-index:2147483647;border:1px solid #0001}
.panel.open{display:flex;animation:pop .22s ease}
@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
.head{background:${c};color:#fff;padding:16px;display:flex;align-items:center;gap:10px}
.av{width:36px;height:36px;border-radius:50%;background:#fff3;display:grid;place-items:center;font-weight:600}
.head b{display:block;font-size:15px}.head small{opacity:.85;font-size:12px}
.head button{margin-left:auto;background:#fff2;border:0;color:#fff;border-radius:999px;padding:7px 12px;font-size:12px;cursor:pointer;display:flex;gap:6px;align-items:center}
.body{flex:1;overflow-y:auto;padding:14px;background:#f7f7fb;display:flex;flex-direction:column;gap:8px}
.m{max-width:85%;padding:9px 13px;border-radius:16px;font-size:14px;line-height:1.45;word-wrap:break-word}
.m.a{background:#fff;border:1px solid #0001;align-self:flex-start;border-bottom-left-radius:4px;color:#111}
.m.u{background:${c};color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
.m.h{background:#e0f2fe;align-self:flex-start;color:#0c4a6e}
.m a{color:${c}}
.sys{align-self:center;font-size:11px;color:#777}
.opts,.cites{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start}
.opt{border:1px solid ${c}55;color:${c};background:#fff;border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer}
.cite{font-size:11px;color:#666;border:1px solid #0001;background:#fff;border-radius:6px;padding:2px 7px;text-decoration:none}
.dots span{display:inline-block;width:6px;height:6px;margin:0 2px;border-radius:50%;background:#aaa;animation:b 1s infinite}
.dots span:nth-child(2){animation-delay:.15s}.dots span:nth-child(3){animation-delay:.3s}
@keyframes b{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
form{display:flex;gap:8px;padding:12px;border-top:1px solid #0001;background:#fff}
input{flex:1;border:1px solid #0002;border-radius:12px;padding:10px 12px;font-size:14px;outline:none}
input:focus{border-color:${c}}
.send{background:${c};border:0;color:#fff;border-radius:12px;width:42px;cursor:pointer}
.call{display:none;flex-direction:column;align-items:center;gap:10px;padding:22px;background:linear-gradient(#f4f2ff,#fff);border-bottom:1px solid #0001}
.call.on{display:flex}
.orb{width:110px;height:110px;border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff9,transparent 45%),conic-gradient(from 0deg,${c},#38bdf8,#f0abfc,${c});transition:transform .1s;box-shadow:0 20px 50px -15px ${c}}
.call p{margin:0;font-size:13px;color:#555;text-transform:capitalize}
.end{background:#ef4444;color:#fff;border:0;border-radius:999px;padding:8px 16px;font-size:13px;cursor:pointer}
.foot{text-align:center;font-size:10px;color:#999;padding:0 0 8px;background:#fff}
`;

const ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
const ICON_MIC = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 19v3"/></svg>';

async function boot() {
  if (!KEY) return console.warn("[unisona] missing data-agent");
  const r = await fetch(`${API}/public/agents/${KEY}`);
  if (!r.ok) return console.warn("[unisona] agent unavailable");
  const cfg: Cfg = await r.json();
  const color = cfg.widget?.color || "#6D5EF8";
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${CSS(color, cfg.widget?.position === "left" ? "left" : "right")}</style>
  <button class="launcher" aria-label="Open chat">${ICON_CHAT}</button>
  <div class="panel" role="dialog">
    <div class="head"><div class="av">${esc((cfg.name || "A")[0])}</div><div><b>${esc(cfg.widget?.title || cfg.business || "Chat")}</b><small>${esc(cfg.widget?.subtitle || "")}</small></div>
    ${cfg.voice_enabled ? `<button class="talk">${ICON_MIC} Talk</button>` : ""}</div>
    <div class="call"><div class="orb"></div><p class="cs">connecting</p><button class="end">End call</button></div>
    <div class="body"></div>
    <form><input placeholder="Type your message…" aria-label="Message"><button class="send" aria-label="Send">➤</button></form>
    <div class="foot">Powered by Unisona</div>
  </div>`;
  const $ = (s: string) => root.querySelector(s) as HTMLElement;
  const panel = $(".panel"), body = $(".body"), input = root.querySelector("input") as HTMLInputElement;
  const msgs: Msg[] = [{ role: "a", text: cfg.greeting }];
  let conv = localStorage.getItem(`unisona_c_${KEY}`);
  let busy = false;
  let es: EventSource | null = null;

  const render = () => {
    body.innerHTML = msgs.map((m) => {
      if (m.role === "sys") return `<div class="sys">${esc(m.text)}</div>`;
      let h = `<div class="m ${m.role}">${m.text ? md(m.text) : '<span class="dots"><span></span><span></span><span></span></span>'}</div>`;
      if (m.citations?.length) h += `<div class="cites">${m.citations.map((c) => `<a class="cite" ${c.url ? `href="${esc(c.url)}" target="_blank"` : ""} title="${esc(c.snippet || "")}">📄 ${esc(c.title)}</a>`).join("")}</div>`;
      if (m.options?.length) h += `<div class="opts">${m.options.map((o) => `<button class="opt">${esc(o)}</button>`).join("")}</div>`;
      return h;
    }).join("") + (msgs.length === 1 && cfg.widget?.starters?.length ? `<div class="opts">${cfg.widget.starters.map((o: string) => `<button class="opt">${esc(o)}</button>`).join("")}</div>` : "");
    body.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => send((b as HTMLElement).innerText)));
    body.scrollTop = body.scrollHeight;
  };

  const listen = () => {
    if (!conv || es) return;
    es = new EventSource(`${API}/public/conversations/${conv}/events?session_id=${sid()}`);
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "human.message") { msgs.push({ role: "h", text: ev.text }); render(); }
      if (ev.type === "agent.joined") { msgs.push({ role: "sys", text: ev.text }); render(); }
    };
  };

  async function send(text: string) {
    text = text.trim();
    if (!text || busy) return;
    busy = true;
    msgs.push({ role: "u", text }, { role: "a", text: "" });
    render();
    const last = msgs[msgs.length - 1];
    try {
      const res = await fetch(`${API}/public/chat/${KEY}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, session_id: sid(), conversation_id: conv, channel: "widget", name: settings.name, email: settings.email, phone: settings.phone,
          user_id: settings.userId, user_hash: settings.userHash, variables: settings.variables }),
      });
      if (!res.ok || !res.body) throw new Error("Something went wrong");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, i).replace(/^data: /, "");
          buf = buf.slice(i + 2);
          try {
            const ev = JSON.parse(line);
            if (ev.type === "meta") { conv = ev.conversation_id; localStorage.setItem(`unisona_c_${KEY}`, conv!); listen(); }
            if (ev.type === "token") { last.text += ev.text; render(); }
            if (ev.type === "reset") last.text = "";
            if (ev.type === "final") {
              if (ev.reply.awaiting_human) msgs.pop();
              else { last.text = ev.reply.text; last.options = ev.reply.options; last.citations = ev.reply.citations; }
              render();
            }
          } catch { /* partial */ }
        }
      }
    } catch (e: any) {
      last.text = "Sorry, I couldn't connect. Please try again.";
      render();
    } finally {
      busy = false;
    }
  }

  // Voice
  let client: PipecatClient | null = null;
  const callBox = $(".call"), orb = $(".orb"), cs = $(".cs");
  const audio = new Audio();
  audio.autoplay = true;
  const endCall = async () => { try { await client?.disconnect(); } catch {} client = null; callBox.classList.remove("on"); };
  root.querySelector(".talk")?.addEventListener("click", async () => {
    if (client) return endCall();
    callBox.classList.add("on");
    cs.textContent = "connecting";
    client = new PipecatClient({
      transport: new SmallWebRTCTransport({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] }),
      enableMic: true, enableCam: false,
      callbacks: {
        onTrackStarted: (t, p) => { if (t.kind === "audio" && !p?.local) { audio.srcObject = new MediaStream([t]); audio.play().catch(() => {}); } },
        onBotStartedSpeaking: () => (cs.textContent = "speaking"),
        onUserStartedSpeaking: () => (cs.textContent = "listening"),
        onUserStoppedSpeaking: () => (cs.textContent = "thinking"),
        onRemoteAudioLevel: (l) => (orb.style.transform = `scale(${1 + Math.min(l, 1) * 0.25})`),
        onLocalAudioLevel: (l) => (orb.style.transform = `scale(${1 + Math.min(l, 1) * 0.15})`),
        onDisconnected: () => endCall(),
      },
    });
    try {
      await client.connect({ webrtcRequestParams: { endpoint: `${API}/public/voice/${KEY}/offer`, requestData: { session_id: sid(), name: settings.name } } } as any);
      cs.textContent = "listening";
    } catch (e: any) {
      cs.textContent = e?.message?.includes("ermission") ? "microphone blocked" : "could not connect";
      setTimeout(endCall, 2500);
    }
  });
  $(".end").addEventListener("click", endCall);

  $(".launcher").addEventListener("click", () => { panel.classList.toggle("open"); if (panel.classList.contains("open")) input.focus(); });
  root.querySelector("form")!.addEventListener("submit", (e) => { e.preventDefault(); const t = input.value; input.value = ""; send(t); });
  if (conv) {
    fetch(`${API}/public/conversations/${conv}/messages?session_id=${sid()}`).then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d?.items?.length && d.status !== "closed") {
        msgs.splice(0, msgs.length, ...d.items.map((m: any) => ({ role: m.role === "user" ? "u" : m.role === "human" ? "h" : "a", text: m.content, options: m.ir?.options, citations: m.ir?.citations })));
        listen();
      } else conv = null;
      render();
    });
  }
  render();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
