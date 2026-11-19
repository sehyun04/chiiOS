// 1번 칸의 [비서][터미널] 탭과 비서 대화.
// 서버(/api/assistant/chat)가 답을 한 줄짜리 JSON 으로 흘려보내면 받는 대로 그린다.
(() => {
  const $ = (s) => document.querySelector(s);
  const log = $("#chat-log");
  const form = $("#chat-form");
  const input = $("#chat-input");
  const sendBtn = $("#chat-send");
  const pane = $(".pane.main");
  const FACE = "faces/hachiware-work.png";
  const SUGGEST = ["오늘 뭐 있었어?", "남은 할 일 정리해 줘", "니나브 상태 어때?"];
  // 확인 단추는 방금 띄운 것만 누를 수 있다. 오래된 단추로 봇을 깨우면 그 사이 바뀐 사정을 놓친다.
  const CONFIRM_TTL = 10 * 60;
  let info = null;
  let busy = false;

  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const face = (cls) => {
    const img = el("img", cls);
    img.src = FACE;
    img.alt = "";
    return img;
  };
  const post = (path, body) => fetch(path, {
    method: "POST",
    headers: { "X-Chii": "1", "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

  // 탭 ------------------------------------------------------------------

  const tabs = { chat: $("#tab-chat"), term: $("#tab-term") };
  const views = { chat: $("#view-chat"), term: $("#view-term") };
  let tab = "chat";
  try { if (localStorage.getItem("chii-tab") === "term") tab = "term"; } catch {}

  function setTab(name, focus) {
    tab = name;
    for (const k of Object.keys(tabs)) {
      const on = k === name;
      tabs[k].classList.toggle("on", on);
      tabs[k].setAttribute("aria-selected", String(on));
      tabs[k].tabIndex = on ? 0 : -1;
      views[k].hidden = !on;
    }
    pane.dataset.tab = name;
    try { localStorage.setItem("chii-tab", name); } catch {}
    if (name === "term") {
      window.chiiTerm.show();
      if (focus) window.chiiTerm.focus();
    } else {
      markSeen();
      if (focus) focusChat();
    }
  }
  function focusChat() {
    const key = $("#key-input");
    if (key) key.focus();
    else if (!input.disabled) input.focus();
  }
  tabs.chat.addEventListener("click", () => setTab("chat", true));
  tabs.term.addEventListener("click", () => setTab("term", true));
  $(".tabs").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    setTab(tab === "chat" ? "term" : "chat", false);
    tabs[tab].focus();
  });

  // 그리기 --------------------------------------------------------------

  const nearBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  const toBottom = () => { log.scrollTop = log.scrollHeight; };

  function botRow() {
    // .bot 은 봇 칸이 쓰는 이름이라 비서 쪽은 .ai 로 둔다.
    const li = el("li", "msg ai");
    const bubble = el("div", "bubble");
    const txt = el("p", "txt");
    bubble.append(txt);
    li.append(face("av"), bubble);
    log.append(li);
    return { li, bubble, txt };
  }

  function meRow(text) {
    const li = el("li", "msg me");
    const bubble = el("div", "bubble");
    bubble.append(el("p", "txt", text));
    li.append(bubble);
    log.append(li);
  }

  function chip(row, text, bad) {
    let box = row.bubble.querySelector(".did");
    if (!box) {
      box = el("div", "did");
      row.bubble.append(box);
    }
    const c = el("span", `chip${bad ? " off" : ""}`);
    c.append(el("i"), document.createTextNode(text));
    box.append(c);
  }

  function errLine(row, text) {
    row.bubble.append(el("p", "err", text));
  }

  function confirmBox(row, c, live) {
    const box = el("div", "ask");
    box.append(el("p", "", c.guard));
    if (!live) {
      box.append(el("span", "dim", "지난 확인 단추라 지금은 못 눌러. 다시 말해 주면 새로 띄울게."));
      row.bubble.append(box);
      return;
    }
    const btns = el("div", "btns");
    const no = el("button", "glass", "그만두기");
    const yes = el("button", "glass primary", `재웠어, ${c.name} 깨우기`);
    no.type = yes.type = "button";
    no.onclick = () => btns.replaceWith(el("span", "dim", "그만뒀어"));
    yes.onclick = async () => {
      yes.disabled = no.disabled = true;
      let ok = false;
      try { ok = (await post(`/api/bots/${encodeURIComponent(c.project)}/start`, { confirm: true })).ok; } catch {}
      btns.replaceWith(el("span", ok ? "dim" : "err", ok ? `${c.name} 깨웠어` : "깨우지 못했어. 봇 칸의 기록을 봐 줘."));
      window.chiiRefresh?.();
    };
    btns.append(no, yes);
    box.append(btns);
    row.bubble.append(box);
  }

  function hello(title, sub) {
    const li = el("li", "hello");
    li.append(face(""), el("b", "", title));
    if (sub) li.append(el("span", "dim", sub));
    log.append(li);
    return li;
  }

  function greet() {
    const li = hello("대장, 뭐 도와줄까?", "오늘 정리, 할 일 챙기기, 봇 돌보기를 할 줄 알아");
    const box = el("div", "suggest");
    for (const s of SUGGEST) {
      const b = el("button", "glass", s);
      b.type = "button";
      b.onclick = () => send(s);
      box.append(b);
    }
    li.append(box);
  }

  function keyForm(message) {
    const li = hello("하치와레 열쇠가 아직 없어",
      "Claude Console 에서 만든 하치와레 전용 API 키를 넣어 줘. 하치와레 봇 안(/var/lib/chiios/assistant)에만 저장되고 화면에는 다시 나오지 않아.");
    li.classList.add("key");
    const f = el("form", "key-form");
    const k = el("input");
    k.id = "key-input";
    k.type = "password";
    k.placeholder = "sk-ant-...";
    k.autocomplete = "off";
    k.spellcheck = false;
    k.setAttribute("aria-label", "하치와레 API 키");
    const b = el("button", "glass primary", "넣기");
    b.type = "submit";
    f.append(k, b);
    const err = el("p", "err", message || "");
    err.hidden = !message;
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const key = k.value.trim();
      if (!key) return;
      b.disabled = true;
      b.textContent = "맞춰 보는 중";
      let data = {};
      let ok = false;
      try {
        const r = await post("/api/assistant/key", { key });
        ok = r.ok;
        data = await r.json().catch(() => ({}));
      } catch {}
      k.value = "";
      if (ok) {
        await load();
        focusChat();
        return;
      }
      b.disabled = false;
      b.textContent = "넣기";
      err.textContent = data.error || "집이랑 연락이 끊겼어.";
      err.hidden = false;
      k.focus();
    });
    li.append(f, err, el("span", "dim small", "니나브와 잔액을 같이 쓰니까, 월 한도를 걸어 둔 작업 공간에서 만든 키가 좋아."));
  }

  // 비서는 따로 도는 봇이라 재워 둘 수 있다. 그때는 여기서 바로 깨운다(봇 칸 깨우기와 같은 길).
  function sleeping() {
    const li = hello("하치와레가 자고 있어", "깨우면 바로 이야기할 수 있어");
    const b = el("button", "glass primary", "하치와레 깨우기");
    b.type = "button";
    b.style.marginTop = "14px";
    b.onclick = async () => {
      b.disabled = true;
      b.textContent = "깨우는 중";
      try { await post("/api/bots/assistant/start"); } catch {}
      // 컨테이너가 떠도 문을 여는 데 잠깐 걸린다. 문이 열릴 때까지 기다렸다가 다시 그린다.
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        try {
          const s = await (await fetch("/api/assistant", { cache: "no-store" })).json();
          if (!s.down) break;
        } catch {}
      }
      window.chiiRefresh?.();
      await load();
      focusChat();
    };
    li.append(b);
  }

  const DAYS = "일월화수목금토";
  const stamp = (t) => {
    const d = new Date(t * 1000);
    return `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };

  // 아침 보고 카드. 숫자는 비서 봇이 센 것을 그대로 보여 주고, 맨 위 한마디만 비서가 쓴 말이다.
  function briefRow(t) {
    const row = botRow();
    row.li.classList.add("brief");
    const d = t.brief || {};
    const head = el("div", "brief-head");
    head.append(el("b", "", "아침 보고"), el("span", "dim", stamp(t.t)));
    row.bubble.insertBefore(head, row.txt);
    row.txt.textContent = t.opening || "";
    const rows = el("dl", "brief-rows");
    const add = (k, v, cls) => {
      rows.append(el("dt", "", k));
      const dd = el("dd", cls || "");
      if (typeof v === "string") dd.textContent = v;
      else dd.append(v);
      rows.append(dd);
    };
    if (d.homeOk === false) add("봇", "홈 화면에 닿지 않아 못 봤어", "bad");
    else {
      add("봇", (d.bots || []).map((b) => `${b.name} ${b.status}`).join(" · ") || "올린 봇 없음");
      add("밤사이", (d.trouble || []).length ? d.trouble.join(" · ") : "쓰러진 봇 없음", (d.trouble || []).length ? "bad" : "");
      const todos = d.todos || [];
      add("할 일", todos.length ? `${todos.length}개 남음 · ${todos.join(", ")}` : "남은 할 일 없음");
    }
    const nt = d.night;
    if (nt && nt.status) {
      add("밤 작업", {
        done: `${nt.todo} · ${nt.repo} 에 커밋 ${nt.commits}개 올려 둠`,
        nothing: `${nt.todo} · 고친 것 없음`,
        failed: `${nt.todo} · 못 끝냄`,
        none: "혼자 해 둘 만한 할 일이 없었어",
        running: `${nt.todo} · 하는 중`,
      }[nt.status] || "");
    }
    const repos = d.repos || [];
    const total = repos.reduce((n, r) => n + r.commits, 0);
    if (total) {
      const det = el("details");
      det.append(el("summary", "", `커밋 ${total}개 · ${repos.filter((r) => r.commits).map((r) => `${r.name} ${r.commits}`).join(" · ")}`));
      const ul = el("ul");
      for (const r of repos) for (const s of r.subjects) ul.append(el("li", "", `${r.name} · ${s}`));
      det.append(ul);
      add("한 일", det);
    } else add("한 일", "지난 보고 뒤로 커밋 없음");
    const dirty = repos.filter((r) => r.dirty).map((r) => `${r.name} ${r.dirty}파일`);
    if (dirty.length) add("작업 중", `커밋 안 한 변경 · ${dirty.join(" · ")}`);
    const ahead = repos.filter((r) => r.ahead).map((r) => `${r.name} ${r.ahead}개`);
    if (ahead.length) add("백업 안 됨", `어느 원격에도 없는 커밋 · ${ahead.join(" · ")}`);
    row.bubble.append(rows);
    if (d.note) row.bubble.append(el("p", "dim small", d.note));
  }

  // 밤 작업 카드. 하치와레 대화와 따로, 홈 화면 서버(/api/state 의 night)가 쥔 결과를 대화 맨 아래에 붙인다.
  // 합치기는 기준 브랜치(main)에 올라가는 일이라 한 번 더 묻는다.
  let nightEl = null;
  let nightKey = "";
  function renderNight(n) {
    const run = n && n.run;
    const key = run ? JSON.stringify([run.id, run.status, run.steps, run.end, run.error]) : "";
    if (key === nightKey && (!nightEl || nightEl.isConnected)) return;
    nightKey = key;
    if (nightEl) nightEl.remove();
    nightEl = null;
    if (!run) return;
    const stick = nearBottom();
    const row = botRow();
    row.li.classList.add("brief", "night");
    const head = el("div", "brief-head");
    head.append(el("b", "", "밤 작업"), el("span", "dim", stamp(run.t)));
    row.bubble.insertBefore(head, row.txt);
    const todo = run.todo ? run.todo.text : "";
    const word = {
      running: `${todo} 하는 중이야. 지금 ${run.steps || 0}단계째`,
      done: run.summary || `${todo} 해 놨어`,
      nothing: run.summary || `${todo} 는 고친 게 없어`,
      failed: `${todo} 는 못 끝냈어${run.error ? `. ${run.error}` : ""}`,
      none: run.error || "혼자 해 둘 만한 할 일이 없었어",
    }[run.status] || "";
    row.txt.textContent = word;
    row.txt.classList.add("pre");
    const rows = el("dl", "brief-rows");
    const add = (k, v) => {
      rows.append(el("dt", "", k));
      const dd = el("dd");
      if (typeof v === "string") dd.textContent = v;
      else dd.append(v);
      rows.append(dd);
    };
    if (todo) add("할 일", todo);
    if (run.repo) add("저장소", `${run.repo}${run.branch ? ` · ${run.branch}` : ""}`);
    const commits = run.commits || [];
    if (commits.length) {
      const det = el("details");
      det.append(el("summary", "", `커밋 ${commits.length}개`));
      const ul = el("ul");
      for (const c of commits) ul.append(el("li", "", `${c.sha} ${c.subject}`));
      det.append(ul);
      add("한 일", det);
    }
    if (run.dirty) add("남은 변경", `커밋 안 한 파일 ${run.dirty}개 (밤 작업 폴더에 남아 있음)`);
    if (run.sessionId && run.cwd) {
      add("이어 하기", el("code", "mono small", `cd "${run.cwd}" && claude --resume ${run.sessionId}`));
    }
    if (rows.childElementCount) row.bubble.append(rows);
    const btns = el("div", "btns");
    const say = el("span", "dim small");
    const act = async (what, b) => {
      for (const x of btns.querySelectorAll("button")) x.disabled = true;
      say.textContent = what === "merge" ? "합치는 중..." : "";
      let r = null;
      try { r = await post(`/api/night/${run.id}/${what}`); } catch {}
      const data = r ? await r.json().catch(() => ({})) : {};
      if (r && r.ok) {
        nightKey = "";
        if (window.chiiRefresh) window.chiiRefresh();
      } else {
        say.textContent = data.error || "못 했어";
        for (const x of btns.querySelectorAll("button")) x.disabled = false;
        if (b) b.textContent = "합치기";
      }
    };
    if (run.status === "done") {
      if (run.compare) {
        const a = el("a", "glass", "GitHub 에서 보기");
        a.href = run.compare;
        a.target = "_blank";
        a.rel = "noopener";
        btns.append(a);
      }
      const merge = el("button", "glass primary", "합치기");
      const drop = el("button", "glass", "버리기");
      merge.type = drop.type = "button";
      let armed = false;
      merge.onclick = () => {
        if (!armed) {
          armed = true;
          merge.textContent = `${run.base || "main"} 에 올릴까? 한 번 더`;
          return;
        }
        act("merge", merge);
      };
      drop.onclick = () => act("drop");
      btns.append(merge, drop);
    } else if (run.status !== "running") {
      const ok = el("button", "glass", "알겠어");
      ok.type = "button";
      ok.onclick = () => act("seen");
      btns.append(ok);
    }
    if (btns.childElementCount) row.bubble.append(btns, say);
    nightEl = row.li;
    if (stick) toBottom();
  }
  window.chiiNight = renderNight;

  function renderTurns(turns) {
    const now = Date.now() / 1000;
    let last = -1;
    turns.forEach((t, i) => { if (t.role === "assistant") last = i; });
    turns.forEach((t, i) => {
      if (t.role === "user") return meRow(t.text);
      if (t.kind === "brief") return briefRow(t);
      const row = botRow();
      row.txt.textContent = t.text || "";
      row.txt.hidden = !t.text;
      for (const c of t.tools || []) chip(row, c);
      if (t.confirm) confirmBox(row, t.confirm, i === last && now - t.t < CONFIRM_TTL);
      if (t.error) errLine(row, t.error);
    });
  }

  async function load() {
    try {
      info = await (await fetch("/api/assistant", { cache: "no-store" })).json();
    } catch {
      info = null;
    }
    log.replaceChildren();
    const ok = !!info && !info.down && info.hasKey;
    input.disabled = sendBtn.disabled = !ok;
    input.placeholder = ok ? "하치와레에게 말 걸기  ·  Enter 보내기, Shift+Enter 줄바꿈"
      : info && info.down ? "하치와레를 깨우면 말을 걸 수 있어" : "열쇠를 넣으면 말을 걸 수 있어";
    if (!info) hello("집이랑 연락이 끊겼어", "홈 화면 서버가 꺼진 것 같아.");
    else if (info.down && info.missing) hello("하치와레 봇이 아직 없어", "Windows 쪽 chiiOS 폴더에서 setup.sh 를 다시 돌리면 구워서 깨운다.");
    else if (info.down) sleeping();
    else if (!info.hasKey) {
      // 열쇠가 없어도 아침 보고는 나온다(맨 위 한마디만 정해진 말로 바뀐다). 열쇠 칸 위에 같이 보여 준다.
      renderTurns(info.turns.filter((t) => t.kind === "brief"));
      keyForm();
    } else if (!info.turns.length) greet();
    else {
      renderTurns(info.turns);
      toBottom();
    }
    const turns = (info && info.turns) || [];
    shown = turns.length ? turns[turns.length - 1].t : 0;
    const today = new Date().setHours(0, 0, 0, 0) / 1000;
    const brief = turns.filter((t) => t.kind === "brief" && t.t >= today).pop();
    window.chiiBrief = brief ? brief.t : 0;
    markSeen();
  }

  // 아침 보고를 본 걸로 친다: 비서 탭이 보이고 창이 앞에 있을 때. 상태줄 말풍선이 이걸 보고 알림을 거둔다.
  function markSeen() {
    if (tab !== "chat" || document.visibilityState !== "visible" || !document.hasFocus() || !window.chiiBrief) return;
    try { localStorage.setItem("chii-brief-seen", String(window.chiiBrief)); } catch {}
  }
  window.addEventListener("focus", markSeen);

  // 아침 보고는 정해진 시각에 비서 봇 쪽에서 생긴다. 열어 둔 화면에도 1분 안에 올라오게 가끔 묻는다.
  let shown = 0;
  setInterval(async () => {
    if (busy) return;
    try {
      const s = await (await fetch("/api/assistant", { cache: "no-store" })).json();
      const latest = s.turns && s.turns.length ? s.turns[s.turns.length - 1].t : 0;
      if (latest !== shown || !!s.down !== !!(info && info.down)) await load();
    } catch {}
  }, 60000);

  // 보내기 --------------------------------------------------------------

  async function send(raw) {
    const text = raw.trim();
    if (!text || busy || !info || !info.hasKey) return;
    busy = true;
    sendBtn.disabled = true;
    input.value = "";
    grow();
    if (log.querySelector(".hello")) log.replaceChildren();
    meRow(text);
    const row = botRow();
    row.li.classList.add("typing");
    row.txt.replaceChildren(el("span", "dots"));
    row.txt.firstChild.append(el("i"), el("i"), el("i"));
    toBottom();

    let got = false;
    let keyBad = false;
    const handle = (ev) => {
      const stick = nearBottom();
      if (ev.t === "text") {
        if (!got) {
          got = true;
          row.li.classList.remove("typing");
          row.txt.textContent = "";
        }
        row.txt.textContent += ev.d;
      } else if (ev.t === "tool") chip(row, ev.d, ev.bad);
      else if (ev.t === "confirm") confirmBox(row, ev, true);
      else if (ev.t === "refresh") window.chiiRefresh?.();
      else if (ev.t === "error") {
        errLine(row, ev.d);
        if (ev.code === "key") keyBad = true;
      }
      if (stick) toBottom();
    };

    try {
      const r = await post("/api/assistant/chat", { text });
      if (!r.ok || !r.body) throw new Error(String(r.status));
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i);
          buf = buf.slice(i + 1);
          if (line.trim()) handle(JSON.parse(line));
        }
      }
    } catch {
      errLine(row, "집이랑 연락이 끊겼어. 잠시 뒤 다시 말해 줘.");
    }
    row.li.classList.remove("typing");
    if (!got) {
      row.txt.textContent = "";
      row.txt.hidden = true;
    }
    busy = false;
    sendBtn.disabled = false;
    window.chiiRefresh?.();
    if (keyBad) {
      keyForm("지금 열쇠가 안 맞아. 새 열쇠를 넣어 줘.");
      toBottom();
    } else {
      input.focus();
    }
  }

  // 한 줄일 땐 스크롤바 없이, 160px 을 넘을 때만 스크롤. scrollHeight 는 테두리를 빼고 재므로 2px 를 더한다.
  function grow() {
    input.style.height = "auto";
    const want = input.scrollHeight + 2;
    input.style.height = `${Math.min(want, 160)}px`;
    input.style.overflowY = want > 160 ? "auto" : "hidden";
  }
  input.addEventListener("input", grow);
  input.addEventListener("keydown", (e) => {
    // 한글은 조합 중에 Enter 가 한 번 더 들어온다. 그걸 보내기로 읽으면 마지막 글자가 두 번 간다.
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    send(input.value);
  });

  $("#chat-brief").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    if (busy || b.disabled) return;
    b.disabled = true;
    try { await post("/api/assistant/brief"); } catch {}
    b.disabled = false;
    await load();
  });

  $("#chat-new").addEventListener("click", async () => {
    if (busy) return;
    await post("/api/assistant/clear");
    await load();
    focusChat();
  });

  window.chiiChat = {
    // Alt+1: 1번 칸에 처음 들어오면 보던 탭으로, 이미 1번 칸 안이면 탭을 바꾼다.
    enter(already) {
      if (already) setTab(tab === "chat" ? "term" : "chat", true);
      else setTab(tab, true);
    },
    open: () => setTab("chat", true),
  };

  setTab(tab, false);
  load();
})();
