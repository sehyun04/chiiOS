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
    } else if (focus) {
      focusChat();
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
    const li = hello("비서 열쇠가 아직 없어",
      "Claude Console 에서 만든 비서 전용 API 키를 넣어 줘. Debian 안(~/.config/chiios)에만 저장되고 화면에는 다시 나오지 않아.");
    li.classList.add("key");
    const f = el("form", "key-form");
    const k = el("input");
    k.id = "key-input";
    k.type = "password";
    k.placeholder = "sk-ant-...";
    k.autocomplete = "off";
    k.spellcheck = false;
    k.setAttribute("aria-label", "비서 API 키");
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

  function renderTurns(turns) {
    const now = Date.now() / 1000;
    let last = -1;
    turns.forEach((t, i) => { if (t.role === "assistant") last = i; });
    turns.forEach((t, i) => {
      if (t.role === "user") return meRow(t.text);
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
    const ok = !!info && info.sdk && info.hasKey;
    input.disabled = sendBtn.disabled = !ok;
    input.placeholder = ok ? "비서에게 말 걸기  ·  Enter 보내기, Shift+Enter 줄바꿈" : "열쇠를 넣으면 말을 걸 수 있어";
    if (!info) hello("집이랑 연락이 끊겼어", "홈 화면 서버가 꺼진 것 같아.");
    else if (!info.sdk) hello("비서 부품이 없어", "Windows 쪽 chiiOS 폴더에서 setup.sh 를 다시 돌리면 깔린다.");
    else if (!info.hasKey) keyForm();
    else if (!info.turns.length) greet();
    else {
      renderTurns(info.turns);
      toBottom();
    }
  }

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
