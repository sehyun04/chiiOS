// chiiOS 홈 화면. 5초마다 /api/state 를 받아 칸을 다시 그린다.
const $ = (s) => document.querySelector(s);
const DAYS = ["일", "월", "화", "수", "목", "금", "토"];
const ICON = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><polygon points="6 3 20 12 6 21 6 3"></polygon></svg>',
  moon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>',
  bake: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"></path><path d="M21 3v5h-5"></path></svg>',
  log: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path><path d="M16 13H8"></path><path d="M16 17H8"></path></svg>',
  warn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>',
  x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>',
};

let state = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const gib = (b) => (b / 2 ** 30).toFixed(1);
// docker 는 이미지 크기를 10진 MB 로 보여 준다. 터미널에서 본 숫자와 같아야 헷갈리지 않는다.
const imageSize = (b) => (b == null ? "-" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (t) => { const d = new Date(t * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

function span(sec) {
  const m = Math.floor(Math.max(0, sec) / 60);
  if (m < 1) return "방금";
  if (m < 60) return `${m}분`;
  if (m < 1440) return `${Math.floor(m / 60)}시간`;
  return `${Math.floor(m / 1440)}일`;
}

// 이름 끝 글자에 받침이 있으면 앞말(이), 없으면 뒷말(가)
function josa(word, withBatchim, without) {
  const c = word.charCodeAt(word.length - 1);
  if (c < 0xac00 || c > 0xd7a3) return word + without;
  return word + ((c - 0xac00) % 28 ? withBatchim : without);
}

function botStatus(b) {
  if (b.state === "running") return { cls: "work", label: "일하는 중" };
  if (b.state === "restarting") return { cls: "down", label: "다시 일어나는 중" };
  if (b.state === "created") return { cls: "rest", label: "아직 안 깨움" };
  // 0 은 스스로 끝남, 137·143 은 재우기(docker stop)가 보낸 신호로 끝난 것이다.
  if ([0, 137, 143].includes(b.exitCode)) return { cls: "rest", label: "쉬는 중" };
  return { cls: "down", label: "쓰러짐" };
}

async function post(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "X-Chii": "1", "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return { status: r.status, data: await r.json().catch(() => ({})) };
}

function renderBots(bots, services) {
  const box = $("#bots");
  $("#bot-count").textContent = bots ? `${bots.length}개` : "";
  if (bots === null) {
    box.innerHTML = '<p class="empty">Docker 에 닿지 않는다. 터미널에서 <span class="mono">systemctl status docker</span> 로 본다.</p>';
    return;
  }
  const now = Date.now() / 1000;
  const items = bots.map((b) => {
    const st = botStatus(b);
    const running = b.state === "running";
    const since = running ? ["일한 지", span(now - (b.startedAt || now))] : ["쉰 지", b.finishedAt ? span(now - b.finishedAt) : "-"];
    const main = running
      ? `<button class="glass primary" data-act="stop" data-p="${esc(b.project)}">${ICON.moon}재우기</button>`
      : `<button class="glass primary" data-act="start" data-p="${esc(b.project)}">${ICON.play}깨우기</button>`;
    const bake = b.canBake
      ? `<button class="glass" data-act="bake" data-p="${esc(b.project)}" ${b.baking ? "disabled" : ""}>${ICON.bake}${b.baking ? "굽는 중" : "다시 굽기"}</button>`
      : "";
    let note = "";
    if (b.guard && !running) note = `<div class="note">${ICON.warn}<span>${esc(b.guard)}</span></div>`;
    else if (b.stale) note = `<div class="note">${ICON.bake}<span>새로 구운 판이 있다. 재우고 다시 깨우면 바뀐다.</span></div>`;
    return `<article class="bot">
      <div class="row">
        <div><div class="name">${esc(b.name)}</div><div class="mono dim">${esc(b.project)} · Docker</div></div>
        <span class="sp"></span>
        <span class="pill ${st.cls}"><i></i>${st.label}</span>
      </div>
      <div class="stats">
        <div><span>이미지</span><b>${imageSize(b.imageSize)}</b></div>
        <div title="${esc(b.subject)}"><span>커밋</span><b>${esc(b.commit || "-")}</b></div>
        <div><span>${since[0]}</span><b>${since[1]}</b></div>
      </div>
      <div class="btns">${main}${bake}<button class="glass" data-act="logs" data-p="${esc(b.project)}">${ICON.log}기록</button></div>
      ${note}
    </article>`;
  });
  const chip = (on, label) => `<span class="chip ${on ? "" : "off"}"><i></i>${label}</span>`;
  const empty = bots.length ? "" : '<p class="empty">아직 올린 봇이 없다. <span class="mono">bots/</span> 의 스크립트로 굽고 깨운다.</p>';
  box.innerHTML = empty + items.join("") +
    `<div class="chips" style="margin-top:14px">${chip(services.docker, "Docker")}${chip(services.term, "브라우저 터미널")}</div>`;
}

function renderTodos(todos) {
  const done = todos.filter((t) => t.done).length;
  $("#todo-count").textContent = `${done} / ${todos.length}`;
  $("#todo-fill").style.width = todos.length ? `${(done / todos.length) * 100}%` : "0";
  $("#todos").innerHTML = todos.map((t) => `<li class="${t.done ? "done" : ""}">
      <button class="todo-check" data-id="${esc(t.id)}" aria-pressed="${t.done}" aria-label="${t.done ? "안 한 걸로" : "끝낸 걸로"}">${ICON.check}</button>
      <span>${esc(t.text)}</span>
      <button class="todo-del" data-del="${esc(t.id)}" aria-label="지우기">${ICON.x}</button>
    </li>`).join("");
}

let lastEventCount = -1;
function renderEvents(events) {
  const box = $("#events");
  // 새 기록이 생겼을 때만 맨 아래(최신)로 내린다. 위로 올려 읽는 중에는 끌어내리지 않는다.
  const grew = events.length !== lastEventCount;
  lastEventCount = events.length;
  box.innerHTML = events.length
    ? events.map((e) => `<li class="${esc(e.kind)}"><time>${hhmm(e.t)}</time><i></i><span>${esc(e.text)}</span></li>`).join("")
    : '<li class="empty">오늘은 아직 아무 일도 없다.</li>';
  if (grew) box.scrollTop = box.scrollHeight;
}

function renderBar(s) {
  const sys = s.sys;
  $("#who").textContent = `${sys.user}@${sys.host}:~`;
  $("#up").textContent = `${sys.os} · ${span(sys.uptime)}째`;
  $("#mem").textContent = `${gib(sys.memUsed)} / ${gib(sys.memTotal)} GB`;
  $("#mem-fill").style.width = `${(sys.memUsed / sys.memTotal) * 100}%`;
  $("#disk").textContent = `디스크 ${gib(sys.diskUsed)} GB`;

  const down = (s.bots || []).find((b) => botStatus(b).cls === "down");
  const left = s.todos.filter((t) => !t.done).length;
  let say;
  if (down) say = `대장, ${josa(down.name, "이", "가")} 쓰러졌어`;
  else if (left) say = `대장, 할 일 ${left}개 남았어~`;
  else if (s.todos.length) say = "대장, 오늘 할 일 다 했어!";
  else say = "대장, 오늘은 뭐 할 거야?";
  $("#say").textContent = say;
}

function tick() {
  const d = new Date();
  $("#clock").textContent = `${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${DAYS[d.getDay()]} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  $("#today").textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`;
}

async function refresh() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    state = await r.json();
  } catch {
    $("#say").textContent = "대장, 집이랑 연락이 끊겼어";
    return;
  }
  const frame = $("#ttyd");
  if (!frame.src) frame.src = `http://${location.hostname}:${state.termPort}/`;
  renderBots(state.bots, state.services);
  renderTodos(state.todos);
  renderEvents(state.events);
  renderBar(state);
}

// 대화 상자: 제목·본문·단추를 받아 띄운다.
function dialog(title, bodyHtml, buttons = []) {
  const dlg = $("#dlg");
  $("#dlg-title").textContent = title;
  $("#dlg-body").innerHTML = bodyHtml;
  const box = $("#dlg-btns");
  box.innerHTML = "";
  for (const b of buttons) {
    const el = document.createElement("button");
    el.className = `glass ${b.primary ? "primary" : ""}`;
    el.textContent = b.label;
    el.onclick = async () => { dlg.close(); if (b.run) await b.run(); };
    box.appendChild(el);
  }
  dlg.showModal();
  return dlg;
}
$("#dlg-close").onclick = () => $("#dlg").close();

async function act(kind, project) {
  const bot = (state.bots || []).find((b) => b.project === project);
  const name = bot ? bot.name : project;
  if (kind === "logs") {
    const r = await fetch(`/api/bots/${encodeURIComponent(project)}/logs?tail=300`);
    const data = await r.json();
    const dlg = dialog(`${name} 기록`, `<pre>${esc(data.text || data.error || "기록이 없다")}</pre>`);
    const pre = dlg.querySelector("pre");
    if (pre) pre.scrollTop = pre.scrollHeight;
    return;
  }
  const r = await post(`/api/bots/${encodeURIComponent(project)}/${kind}`);
  if (r.status === 409 && r.data.guard) {
    dialog(`${name} 깨우기`, `<p>${esc(r.data.guard)}</p>`, [
      { label: "그만두기" },
      { label: "재웠어, 깨우기", primary: true, run: async () => { await post(`/api/bots/${encodeURIComponent(project)}/start`, { confirm: true }); refresh(); } },
    ]);
    return;
  }
  if (r.status >= 400) dialog(`${name}`, `<p>${esc(r.data.error || "잘 안 됐다. 기록을 본다.")}</p>`);
  refresh();
}

$("#bots").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-act]");
  if (b && !b.disabled) act(b.dataset.act, b.dataset.p);
});

$("#todos").addEventListener("click", async (e) => {
  const check = e.target.closest(".todo-check");
  const del = e.target.closest(".todo-del");
  if (check) await post(`/api/todos/${check.dataset.id}/toggle`);
  else if (del) await post(`/api/todos/${del.dataset.del}/delete`);
  else return;
  refresh();
});

$("#todo-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#todo-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  await post("/api/todos", { text });
  refresh();
});

// 보고 있는 칸 표시. 터미널 안을 누르면 포커스가 iframe 으로 넘어가 창이 blur 된다.
const panes = [...document.querySelectorAll(".pane")];
function setOn(n) { panes.forEach((p) => p.classList.toggle("on", p.dataset.n === String(n))); }
panes.forEach((p) => p.addEventListener("mousedown", () => setOn(p.dataset.n)));
window.addEventListener("blur", () => setTimeout(() => { if (document.activeElement === $("#ttyd")) setOn(1); }, 0));
// Alt+숫자로 칸 옮기기. 터미널 안에 있을 땐 키가 셸로 가므로, 터미널 밖에서만 먹는다.
document.addEventListener("keydown", (e) => {
  if (!e.altKey || !/^Digit[1-4]$/.test(e.code)) return;
  e.preventDefault();
  const n = e.code.slice(5);
  setOn(n);
  const pane = panes.find((p) => p.dataset.n === n);
  if (n === "1") $("#ttyd").focus();
  else if (n === "3") $("#todo-input").focus();
  else pane.querySelector("button")?.focus();
});

tick();
setInterval(tick, 15000);
refresh();
setInterval(refresh, 5000);
