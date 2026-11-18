// 바탕화면: Windows 바탕화면의 아이콘을 같은 칸 배치로 그린다. 두 번 누르면(또는 Enter) Windows 에서 연다.
// 상태줄의 chiiOS 를 누르거나 Alt+D 로 칸들과 바탕화면을 오간다. 배치는 열 때마다 Windows 에서 새로 읽는다.
(() => {
  const $ = (s) => document.querySelector(s);
  const desk = $(".desk");
  const view = $("#deskview");
  const grid = $("#desk-grid");
  const note = $("#desk-note");
  const brand = $("#brand");
  let layout = null;
  let on = false;
  let busy = false;

  const post = (path, body) => fetch(path, {
    method: "POST",
    headers: { "X-Chii": "1", "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

  async function fetchLayout() {
    try {
      layout = await (await fetch("/api/desktop", { cache: "no-store" })).json();
    } catch {
      layout = null;
    }
  }

  // Windows 는 아이콘 자리를 실제 픽셀로, 칸 간격(spacing)과 함께 준다. 몇째 줄·몇째 칸인지로 바꿔 같은 배치를
  // 만들고, chiiOS 화면이 더 작으면 칸 크기를 같은 비율로 줄여 한 화면에 다 들어오게 한다.
  function render() {
    grid.replaceChildren();
    const items = (layout && layout.items) || [];
    note.hidden = items.length > 0;
    if (!items.length) {
      note.textContent = layout && layout.missing
        ? "아직 Windows 바탕화면을 못 읽었어. 잠깐 뒤에 다시 열어 줘."
        : "바탕화면에 아무것도 없어.";
      return;
    }
    const dpr = window.devicePixelRatio || 1;
    const sp = layout.spacing || { x: 96, y: 112 };
    const minX = Math.min(...items.map((i) => i.x));
    const minY = Math.min(...items.map((i) => i.y));
    const cells = items.map((i) => ({ i, col: Math.round((i.x - minX) / sp.x), row: Math.round((i.y - minY) / sp.y) }));
    const cols = Math.max(...cells.map((c) => c.col)) + 1;
    const rows = Math.max(...cells.map((c) => c.row)) + 1;
    let cw = sp.x / dpr;
    let ch = sp.y / dpr;
    const scale = Math.min(1, (view.clientWidth - 16) / (cols * cw), (view.clientHeight - 16) / (rows * ch));
    cw *= scale;
    ch *= scale;
    grid.style.setProperty("--cw", `${cw}px`);
    grid.style.setProperty("--ch", `${ch}px`);
    grid.style.setProperty("--ic", `${Math.round(44 * Math.max(scale, 0.7))}px`);
    for (const { i, col, row } of cells) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "dicon";
      b.style.left = `${col * cw}px`;
      b.style.top = `${row * ch}px`;
      b.title = i.name;
      b.dataset.id = i.id;
      if (i.icon) {
        const img = document.createElement("img");
        img.src = `/desktop/icons/${i.id}.png?t=${layout.t}`;
        img.alt = "";
        b.append(img);
      }
      const label = document.createElement("span");
      label.textContent = i.name;
      b.append(label);
      b.addEventListener("dblclick", () => open(i));
      b.addEventListener("keydown", (e) => { if (e.key === "Enter") open(i); });
      grid.append(b);
    }
  }

  async function open(item) {
    const say = $("#say");
    const before = say.textContent;
    say.textContent = `대장, ${item.name} 열게`;
    try {
      const r = await post("/api/desktop/open", { id: item.id });
      if (!r.ok) say.textContent = `${item.name} 은(는) 못 열었어. 바탕화면을 새로 읽어 볼게`;
      if (!r.ok) refresh();
    } catch {
      say.textContent = before;
    }
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    view.classList.add("loading");
    try { await post("/api/desktop/refresh"); } catch {}
    await fetchLayout();
    view.classList.remove("loading");
    busy = false;
    if (on) render();
  }

  function toggle(force) {
    on = typeof force === "boolean" ? force : !on;
    desk.classList.toggle("desktop-on", on);
    view.hidden = !on;
    brand.setAttribute("aria-pressed", String(on));
    brand.title = on ? "칸으로 돌아가기 (Alt+D)" : "바탕화면 (Alt+D)";
    if (on) {
      // 읽어 둔 배치를 먼저 보여 주고, Windows 에서 새로 읽어 오면 다시 그린다.
      render();
      refresh();
      setTimeout(() => (grid.querySelector(".dicon") || view).focus(), 0);
    }
  }

  brand.addEventListener("click", () => toggle());
  // 붙잡는 단계에서 받는다. 터미널 안에서 Alt+D 는 셸의 '단어 지우기' 라 그냥 두면 셸이 먹는다.
  window.addEventListener("keydown", (e) => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === "KeyD") {
      e.preventDefault();
      e.stopPropagation();
      toggle();
    } else if (on && e.key === "Escape") {
      toggle(false);
    } else if (on && e.altKey && e.code === "Digit1") {
      // 바탕화면은 1번 칸 자리에 뜬다. Alt+1 은 그 칸(비서·터미널)으로 돌아가는 것으로 친다. 포커스는 app.js 가 옮긴다.
      toggle(false);
    }
  }, true);
  new ResizeObserver(() => { if (on) render(); }).observe(view);

  fetchLayout();
  window.chiiDesktop = { toggle };
})();
