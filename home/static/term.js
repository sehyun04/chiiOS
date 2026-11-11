// 터미널 칸. ttyd 웹소켓을 홈 화면 서버(/term/ws)로 받아 xterm 으로 직접 그린다.
// ttyd 페이지를 iframe 으로 넣던 때는 출처가 달라 여백·스크롤바·밤 색을 못 바꿨고, 칸 안에서는 Alt+1~4 도 셸이 먹었다.
(() => {
  // 낮 색은 치이스페 Term.tsx 그대로, 보라(magenta) 자리만 코코아로 바꿨다. setup.sh 의 ttyd 단독 화면과 같은 값이다.
  const DAY = {
    background: "#fbf5ea", foreground: "#5b4433", cursor: "#6b5442", cursorAccent: "#fbf5ea",
    selectionBackground: "#f3bfc366",
    black: "#5b4433", red: "#c34741", green: "#4f7b4d", yellow: "#8a6d26",
    blue: "#2f77a1", magenta: "#96663d", cyan: "#38798b", white: "#836d5a",
    brightBlack: "#8f775c", brightRed: "#be2b22", brightGreen: "#3d703b", brightYellow: "#7e6003",
    brightBlue: "#196a99", brightMagenta: "#7f5530", brightCyan: "#1d6d83", brightWhite: "#5b4433",
  };
  // 밤 색은 같은 색조를 어두운 코코아 바탕 위로 옮긴 것. 글자색은 모두 바탕 대비 5 이상(black 만 바탕용이라 낮다).
  const NIGHT = {
    background: "#231c17", foreground: "#f1e4d1", cursor: "#f1e4d1", cursorAccent: "#231c17",
    selectionBackground: "#7cc0e64d",
    black: "#5c4d41", red: "#f08a84", green: "#9fcf9a", yellow: "#e5c66f",
    blue: "#7cc0e6", magenta: "#d9a978", cyan: "#80c9c4", white: "#d2c0a8",
    brightBlack: "#a08b74", brightRed: "#ffaaa4", brightGreen: "#b9e2b4", brightYellow: "#f3dc96",
    brightBlue: "#a8d8f3", brightMagenta: "#ebc49c", brightCyan: "#a6ddd9", brightWhite: "#f6ecdd",
  };

  const host = document.getElementById("term");
  const cover = document.getElementById("term-cover");
  const reopenBtn = document.getElementById("term-reopen");
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  const night = () => document.documentElement.dataset.theme === "night";

  const term = new Terminal({
    theme: night() ? NIGHT : DAY,
    // D2Coding 은 홈 화면이 글꼴 파일을 직접 내준다. 보는 PC 에 글꼴이 없어도 한글 폭이 어긋나지 않는다.
    fontFamily: '"chii-mono", "D2Coding", "Cascadia Mono", Consolas, monospace',
    fontSize: 15,
    lineHeight: 1.25,
    cursorBlink: true,
    // 기본 1000 줄은 빌드 기록 한 번에 밀려난다.
    scrollback: 10000,
    // 프로그램이 트루컬러로 직접 고른 색은 우리 팔레트를 안 거친다. 대비가 모자란 글자만 xterm 이 조여 준다.
    minimumContrastRatio: 4.5,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.loadAddon(new WebLinksAddon.WebLinksAddon((_e, uri) => window.open(uri, "_blank", "noopener")));

  let ws = null;
  const live = () => ws && ws.readyState === WebSocket.OPEN;
  const send = (text) => { if (live()) ws.send(enc.encode(text)); };

  function connect() {
    cover.hidden = true;
    ws = new WebSocket(`ws://${location.host}/term/ws`, ["tty"]);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      // ttyd 는 이 첫 메시지(창 크기)를 받고서야 셸을 띄운다.
      ws.send(enc.encode(JSON.stringify({ AuthToken: "", columns: term.cols, rows: term.rows })));
      term.focus();
    };
    ws.onmessage = (ev) => {
      const data = new Uint8Array(ev.data);
      // 첫 바이트가 종류다. 0 = 화면 출력, 1 = 창 제목, 2 = ttyd 쪽 화면 설정. 제목과 설정은 홈 화면이 정하므로 버린다.
      if (data[0] === 0x30) term.write(data.subarray(1));
    };
    ws.onclose = () => {
      ws = null;
      // 덮개가 터미널을 가리면 클릭이 터미널에 닿지 않는다. 터미널을 보던 중이었으면 다시 열기 단추로 포커스를 옮겨 Enter 가 바로 먹게 한다.
      const watching = host.contains(document.activeElement);
      cover.hidden = false;
      if (watching) reopenBtn.focus();
    };
  }

  function reopen() {
    if (live()) return;
    term.reset();
    connect();
  }

  term.onData((d) => send("0" + d));
  // 마우스 보고 같은 날 바이트는 UTF-8 로 다시 감싸면 깨진다. 한 글자 = 한 바이트로 그대로 보낸다.
  term.onBinary((d) => {
    if (!live()) return;
    const buf = new Uint8Array(d.length + 1);
    buf[0] = 0x30;
    for (let i = 0; i < d.length; i++) buf[i + 1] = d.charCodeAt(i) & 0xff;
    ws.send(buf);
  });
  term.onResize(({ cols, rows }) => send("1" + JSON.stringify({ columns: cols, rows })));

  term.attachCustomKeyEventHandler((e) => {
    if (e.type !== "keydown") return true;
    // 칸 옮기기는 문서 쪽 처리기에 넘긴다. 여기서 안 막으면 셸에 ESC+숫자가 들어간다.
    if (e.altKey && !e.ctrlKey && /^Digit[1-4]$/.test(e.code)) return false;
    const k = e.key.toLowerCase();
    // Windows 터미널처럼: 고른 글이 있으면 Ctrl+C 는 복사, 없으면 셸에 인터럽트.
    if (e.ctrlKey && k === "c" && term.hasSelection()) {
      navigator.clipboard?.writeText(term.getSelection()).catch(() => {});
      term.clearSelection();
      e.preventDefault();
      return false;
    }
    // Ctrl+V 는 xterm 이 먹으면 셸에 ^V 가 간다. 브라우저 붙여넣기가 일어나게 놓아준다.
    if (e.ctrlKey && k === "v") return false;
    return true;
  });

  reopenBtn.addEventListener("click", reopen);

  let pending = 0;
  new ResizeObserver(() => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => { if (host.clientWidth && host.clientHeight) fit.fit(); });
  }).observe(host);

  // 글꼴이 다 오기 전에 열면 xterm 이 대체 글꼴로 칸 폭을 재서 줄이 어긋난다. 늦어도 3초 뒤에는 연다.
  const fonts = Promise.all([
    document.fonts.load('15px "chii-mono"'),
    document.fonts.load('bold 15px "chii-mono"'),
  ]).catch(() => {});
  const fontsReady = Promise.race([fonts, new Promise((r) => setTimeout(r, 3000))]);

  // 숨은 탭 안에서 열면 xterm 이 칸 크기를 0 으로 재서 글자 폭이 틀어진다. 터미널 탭이 처음 보일 때 연다.
  // 셸도 그때 띄우므로, 비서만 쓰는 날엔 bash 가 뜨지 않는다.
  let opening = null;
  function show() {
    if (!opening) {
      opening = fontsReady.then(() => {
        term.open(host);
        fit.fit();
        connect();
      });
    }
    return opening;
  }

  window.chiiTerm = {
    show,
    focus: () => show().then(() => (cover.hidden ? term.focus() : reopenBtn.focus())),
    setTheme: (isNight) => { term.options.theme = isNight ? NIGHT : DAY; },
  };
})();
