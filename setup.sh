#!/usr/bin/env bash
# chiiOS: 순정 Debian 13 위에 봇 실행 환경(Docker)과 브라우저 터미널(ttyd), 홈 화면을 얹는다.
# 지금은 WSL 에서 연습하고 나중에 i7 PC 실기에도 그대로 돌릴 거라, WSL 전용 처리는 is_wsl 안에만 둔다.
# 몇 번을 다시 돌려도 결과가 같게 짰다. 설정을 바꾸면 이 파일을 고치고 다시 돌리면 된다.
#
#   WSL:  wsl -d Debian -u root -- bash /mnt/c/.../chiiOS/setup.sh
#   실기: sudo bash setup.sh
set -euo pipefail

CHII_USER="${CHII_USER:-sehyun}"
CHII_HOST="${CHII_HOST:-chiios}"
TTYD_PORT="${TTYD_PORT:-7681}"
# 7680 은 Windows 배달 최적화(DoSvc)가 쥐고 있어서 Windows 쪽 localhost 로는 닿지 않는다.
HOME_PORT="${HOME_PORT:-7682}"
# 비서 봇 문. 바꾸면 bots/assistant/compose.yaml 의 ASSIST_PORT 도 같이 바꾼다.
ASSIST_PORT="${ASSIST_PORT:-7683}"
TTYD_VERSION=1.7.7
CHII_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "root 로 실행해야 한다: sudo bash setup.sh" >&2
  exit 1
fi

is_wsl() { grep -qi microsoft /proc/sys/kernel/osrelease; }
step() { printf '\n== %s\n' "$*"; }

export DEBIAN_FRONTEND=noninteractive

step "사용자 $CHII_USER"
if ! id "$CHII_USER" >/dev/null 2>&1; then
  # Debian WSL 첫 실행 스크립트(/usr/lib/wsl/oobe.sh)는 UID 1000 이 있으면 계정 만들기 질문을 건너뛴다.
  # 그 스크립트와 같은 UID·그룹으로 만들어서, 실기 설치 때 생기는 첫 계정과도 모양을 맞춘다.
  useradd -m -u 1000 -s /bin/bash -G adm,cdrom,sudo,dip,plugdev "$CHII_USER"
fi

if is_wsl; then
  step "WSL 설정"
  # WSL 에선 Windows 계정만 있으면 `wsl -u root` 로 언제든 root 가 되므로 sudo 비밀번호가 막아 주는 게 없다.
  # 실기에선 이 줄을 두지 않고 설치 때 정한 비밀번호를 쓴다.
  echo "$CHII_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-chii
  chmod 440 /etc/sudoers.d/90-chii

  cat > /etc/wsl.conf <<EOF
[boot]
systemd=true

[user]
default=$CHII_USER

[network]
hostname=$CHII_HOST
generateResolvConf=false
EOF

  # Windows 10 의 WSL(NAT)은 이름을 Windows 쪽 DNS 중계(기본 길목 주소)에 묻는데, 이 중계가 부팅에 따라 아예 답을
  # 안 할 때가 있다(데스크톱 11-20: 인터넷은 되는데 이름만 안 풀려 이미지 굽기가 멈췄다. 같은 날 노트북은 멀쩡).
  # 상시 봇 PC 가 그 운에 기대지 않게 공용 DNS 를 직접 쓴다. Windows 11 의 dnsTunneling 은 Windows 10 에 없다.
  # /etc/resolv.conf 는 WSL 이 걸어 둔 링크(/mnt/wsl/resolv.conf, 다른 배포판과 같이 씀)라 따라가 쓰지 않고 바꿔 끼운다.
  printf '# chiiOS setup.sh: WSL 의 DNS 중계 대신 공용 DNS\nnameserver 1.1.1.1\nnameserver 8.8.8.8\noptions timeout:2\n' > /etc/resolv.conf.chii
  mv -f /etc/resolv.conf.chii /etc/resolv.conf
else
  step "호스트 이름"
  hostnamectl set-hostname "$CHII_HOST"
fi

step "기본 패키지"
apt-get update -q
apt-get install -y -q ca-certificates curl git htop python3

step "Docker"
# Debian 저장소의 docker.io 대신 Docker 공식 저장소를 쓴다. compose v2 플러그인이 같이 오고 업데이트가 빠르다.
if [ ! -f /etc/apt/sources.list.d/docker.sources ]; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update -q
fi
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# docker 그룹은 사실상 root 권한이다. 혼자 쓰는 기계라 매번 sudo 를 붙이는 수고를 덜기로 했다.
usermod -aG docker "$CHII_USER"
systemctl enable --now docker
# 봇 기록(docker logs)은 기본값이면 끝없이 쌓인다. 몇 달 켜 두는 데스크톱에서 디스크를 다 먹지 않게, 따로 정하지
# 않은 봇은 컨테이너마다 10MB 파일 3개까지만 남긴다. 이미 있는 설정은 지우지 않고 합친다.
# 바뀌었을 때만 docker 를 다시 켠다(그 순간 깨어 있던 봇이 잠깐 내려갔다 restart 정책대로 다시 뜬다).
# 이미 만들어진 컨테이너는 옛 설정 그대로고, 다시 만들어질 때(새 판으로 깨우기 등) 새 기본값을 받는다.
log_changed="$(python3 - <<'PY'
import json, pathlib
p = pathlib.Path("/etc/docker/daemon.json")
raw = p.read_text() if p.exists() else ""
cfg = json.loads(raw) if raw.strip() else {}
before = json.dumps(cfg, sort_keys=True)
if cfg.get("log-driver", "json-file") == "json-file":
    cfg["log-driver"] = "json-file"
    opts = cfg.setdefault("log-opts", {})
    opts.setdefault("max-size", "10m")
    opts.setdefault("max-file", "3")
if json.dumps(cfg, sort_keys=True) != before:
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    print("changed")
PY
)"
if [ "$log_changed" = "changed" ]; then
  systemctl restart docker
  echo "docker 기록 상한을 걸고 docker 를 다시 켰다."
fi

step "브라우저 터미널 (ttyd $TTYD_VERSION, 포트 $TTYD_PORT)"
# Debian 13 저장소에는 ttyd 가 없어서 공식 릴리스의 정적 바이너리를 받는다.
# 남의 실행 파일을 root 로 까는 셈이라 버전과 해시를 고정해, 릴리스가 바꿔치기되면 설치가 멈추게 했다.
case "$(uname -m)" in
  x86_64)  ttyd_arch=x86_64;  ttyd_sha=8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55 ;;
  aarch64) ttyd_arch=aarch64; ttyd_sha=b38acadd89d1d396a0f5649aa52c539edbad07f4bc7348b27b4f4b7219dd4165 ;;
  *) echo "ttyd 바이너리가 없는 아키텍처: $(uname -m)" >&2; exit 1 ;;
esac
if ! /usr/local/bin/ttyd --version 2>/dev/null | grep -q "$TTYD_VERSION"; then
  tmp="$(mktemp)"
  curl -fsSL -o "$tmp" "https://github.com/tsl0922/ttyd/releases/download/$TTYD_VERSION/ttyd.$ttyd_arch"
  echo "$ttyd_sha  $tmp" | sha256sum -c --quiet
  install -m 0755 "$tmp" /usr/local/bin/ttyd
  rm -f "$tmp"
fi
# 치이스페(kasaspace/ui/Term.tsx)의 밝은 터미널 색을 그대로 쓴다. 파스텔은 크림 바탕에서 안 읽혀
# 명도를 내린 값들이다. 다만 magenta 는 보라라서 쓰지 않기로 했고, 그 자리에 코코아를 넣었다.
TTYD_THEME='{"background":"#fbf5ea","foreground":"#5b4433","cursor":"#6b5442","cursorAccent":"#fbf5ea","selectionBackground":"#f3bfc355","black":"#5b4433","red":"#c34741","green":"#4f7b4d","yellow":"#8a6d26","blue":"#2f77a1","magenta":"#96663d","cyan":"#38798b","white":"#836d5a","brightBlack":"#8f775c","brightRed":"#be2b22","brightGreen":"#3d703b","brightYellow":"#7e6003","brightBlue":"#196a99","brightMagenta":"#7f5530","brightCyan":"#1d6d83","brightWhite":"#5b4433"}'
# 글꼴은 보는 쪽 브라우저가 가진 것만 쓸 수 있다. 치이스페와 같은 D2Coding 계열을 먼저 찾고, 없으면 Windows 기본 등폭으로.
# 따옴표로 시작하면 ttyd 가 값을 JSON 으로 읽어 첫 글꼴만 남기므로 따옴표 없이 쓴다(CSS 는 그래도 된다).
TTYD_FONT='D2KodingLigature Nerd Font, D2Coding, Cascadia Mono, Consolas, monospace'
cat > /etc/systemd/system/chii-term.service <<EOF
[Unit]
Description=chiiOS browser terminal
After=network.target

[Service]
User=$CHII_USER
WorkingDirectory=/home/$CHII_USER
# 127.0.0.1 에만 묶는다. 브라우저 터미널은 셸을 통째로 내주는 것이라,
# 다른 기기에서 열려면 Tailscale 같은 인증 뒤에 둔 다음에 바꾼다.
# ttyd 1.7 부터는 기본이 읽기 전용이라 --writable 이 있어야 입력이 들어간다.
# 그리기는 DOM 으로 둔다. 기본값 WebGL 은 화면 배율이 어긋나면(시험 브라우저에서 1.25 와 1) 캔버스가
# 아래로 밀려 위쪽 다섯 줄쯤이 비었다. DOM 은 그런 일이 없고 이 정도 출력엔 충분히 빠르다.
# --check-origin: 다른 사이트의 페이지가 이 터미널 웹소켓에 몰래 붙지 못하게 한다. 홈 화면의 터미널 칸은
# 홈 화면 서버(/term/ws)가 출처를 먼저 보고, Origin·Host 를 이 ttyd 주소로 맞춰 넘기므로 그대로 통과한다.
# 아래 -t 색·글꼴은 7681 을 브라우저로 바로 열 때만 쓰인다. 홈 화면 칸의 색은 home/static/term.js 가 정한다.
ExecStart=/usr/local/bin/ttyd --interface 127.0.0.1 --port $TTYD_PORT --writable --check-origin -t titleFixed=chiiOS -t disableResizeOverlay=true -t rendererType=dom -t fontSize=15 -t lineHeight=1.25 -t cursorBlink=true -t 'fontFamily=$TTYD_FONT' -t 'theme=$TTYD_THEME' bash -l
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable chii-term.service
systemctl restart chii-term.service

step "셸 꾸밈 (프롬프트, 로그인 요약)"
install -d /etc/chiios
cat > /etc/chiios/bashrc <<'EOF'
# chiiOS 셸 꾸밈. setup.sh 가 쓰는 파일이라 여기를 고쳐도 다음 실행 때 덮인다.
case $- in *i*) ;; *) return ;; esac

PS1='\[\e[1;34m\]\u@\h\[\e[0m\]:\w\$ '

# 로그인할 때만 요약을 보인다. 셸 안에서 bash 를 또 띄울 때마다 찍히면 시끄럽다.
chii_summary() {
  local up mins os mem disk bots states all run
  read -r up _ < /proc/uptime
  mins=$(( ${up%.*} / 60 ))
  if (( mins < 60 )); then up="${mins}분째"
  elif (( mins < 1440 )); then up="$(( mins / 60 ))시간째"
  else up="$(( mins / 1440 ))일째"
  fi
  os=$(. /etc/os-release && echo "${NAME%% *} $VERSION_ID ($VERSION_CODENAME)")
  mem=$(awk '/^MemTotal/ {t=$2} /^MemAvailable/ {a=$2} END {printf "%.1f / %.1f GB", (t-a)/1048576, t/1048576}' /proc/meminfo)
  disk=$(df -h --output=used / | tail -n 1 | tr -d ' ')
  # 봇은 compose 로 띄운 컨테이너다. docker 가 늦게 답해도 로그인이 붙잡히지 않게 2초에서 끊는다.
  bots=""
  if states=$(timeout 2 docker ps -a --filter label=com.docker.compose.project.working_dir --format '{{.State}}' 2>/dev/null); then
    all=$(grep -c . <<<"$states")
    run=$(grep -c '^running$' <<<"$states")
    bots="봇 ${all}개 (일하는 중 ${run} · 쉬는 중 $(( all - run ))) · "
  fi
  # 색은 터미널 테마와 상관없이 같게 보이도록 24비트로 직접 준다(코코아, 흐린 갈색).
  printf '\n  \e[1;38;2;150;102;61mchiiOS\e[0m · %s · %s 깨어 있음\n' "$os" "$up"
  printf '  \e[38;2;136;113;88m%s메모리 %s · 디스크 %s 씀\e[0m\n\n' "$bots" "$mem" "$disk"
}
shopt -q login_shell && chii_summary
unset -f chii_summary

# chii 명령 빈칸 채우기: 첫 칸은 할 말, 둘째 칸은 봇 이름이나 할 일 동작.
_chii() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  if (( COMP_CWORD == 1 )); then
    COMPREPLY=($(compgen -W "status bots wake sleep bake logs todo log night open backup update help" -- "$cur"))
  elif (( COMP_CWORD == 2 )); then
    case ${COMP_WORDS[1]} in
      wake|sleep|bake|logs) COMPREPLY=($(compgen -W "$(chii _names 2>/dev/null)" -- "$cur")) ;;
      todo) COMPREPLY=($(compgen -W "add done undo rm" -- "$cur")) ;;
      night) COMPREPLY=($(compgen -W "on off run triage" -- "$cur")) ;;
    esac
  fi
}
complete -F _chii chii
EOF
# 사용자 ~/.bashrc 가 PS1 을 다시 정하므로, 그 끝에서 위 파일을 불러야 덮어쓴다.
bashrc_hook='[ -f /etc/chiios/bashrc ] && . /etc/chiios/bashrc'
user_bashrc="/home/$CHII_USER/.bashrc"
if ! grep -qxF "$bashrc_hook" "$user_bashrc" 2>/dev/null; then
  printf '\n# chiiOS\n%s\n' "$bashrc_hook" >> "$user_bashrc"
  chown "$CHII_USER:$CHII_USER" "$user_bashrc"
fi

step "chii 명령"
install -m 755 "$CHII_DIR/bin/chii" /usr/local/bin/chii
# 업데이트 본체는 root 로 돈다(setup.sh 를 다시 돌린다). install 은 새 파일로 바꿔 넣으므로, 업데이트 도중
# 이 setup.sh 가 자기를 부른 chii-update 를 바꿔 깔아도 돌던 쪽은 옛 파일을 끝까지 읽는다.
install -m 755 "$CHII_DIR/bin/chii-update" /usr/local/sbin/chii-update
install -d /var/lib/chiios

step "되살리기 (새로 깐 Debian 이면)"
# 백업은 Windows 쪽 레포 폴더에 쌓인다(bin/chii-backup). Debian 을 다시 깔아 할 일 파일이 없으면 마지막 백업을 편다.
# 데이터가 이미 있으면 손대지 않는다: 돌아가던 chiiOS 의 오늘 기록을 어제 백업으로 덮으면 안 된다.
backup_dir="$CHII_DIR/backup"
latest="$(ls -1t "$backup_dir"/chiios-*.tar.gz 2>/dev/null | head -n 1 || true)"
if [ -n "$latest" ] && [ ! -e "/home/$CHII_USER/.local/share/chiios/todos.json" ]; then
  rtmp="$(mktemp -d)"
  tar -xzf "$latest" -C "$rtmp"
  install -d -o "$CHII_USER" -g "$CHII_USER" "/home/$CHII_USER/.local/share/chiios" /var/lib/chiios
  install -d -m 700 -o "$CHII_USER" -g "$CHII_USER" /var/lib/chiios/assistant
  cp -a "$rtmp/home/." "/home/$CHII_USER/.local/share/chiios/"
  cp -a "$rtmp/assistant/." /var/lib/chiios/assistant/
  chown -R "$CHII_USER:$CHII_USER" "/home/$CHII_USER/.local/share/chiios" /var/lib/chiios/assistant
  rm -rf "$rtmp"
  echo "백업에서 되살렸다: $latest (비서 열쇠는 백업에 없으니 다시 넣는다)"
else
  echo "되살릴 것 없음"
fi

step "홈 화면 (포트 $HOME_PORT)"
# Windows 쪽 폴더(/mnt/c)에서 바로 돌리지 않고 Debian 안으로 복사해 둔다. 레포를 옮기거나 지워도
# 홈 화면이 살아 있어야 하고, 무엇이 돌고 있는지는 마지막으로 돌린 setup.sh 가 정한다.
install -d /opt/chiios
rm -rf /opt/chiios/home /opt/chiios/bots
cp -r "$CHII_DIR/home" "$CHII_DIR/bots" /opt/chiios/
# 지금 깔린 판. 홈 화면의 업데이트 알림이 레포의 새 커밋과 비교하는 기준이다.
git -c safe.directory='*' -C "$CHII_DIR" rev-parse HEAD > /opt/chiios/VERSION 2>/dev/null || echo unknown > /opt/chiios/VERSION
cat > /etc/systemd/system/chii-home.service <<EOF
[Unit]
Description=chiiOS home screen
After=network.target docker.service chii-term.service
Wants=docker.service

[Service]
# 봇을 깨우고 재우려면 docker 그룹이 필요하다. 그 그룹은 $CHII_USER 에게 이미 있다.
User=$CHII_USER
WorkingDirectory=/home/$CHII_USER
Environment=CHII_HOME_PORT=$HOME_PORT CHII_TERM_PORT=$TTYD_PORT CHII_ASSIST_PORT=$ASSIST_PORT
# 터미널 칸처럼 127.0.0.1 에만 묶는다. 봇을 깨우고 재우는 단추가 있는 화면이다.
ExecStart=/usr/bin/python3 /opt/chiios/home/server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable chii-home.service
systemctl restart chii-home.service

step "비서 봇 (포트 $ASSIST_PORT)"
# 비서는 니나브처럼 따로 도는 봇이다(bots/assistant). 대화와 열쇠는 레포 사본(/opt/chiios)이 아니라
# 여기 둔다. setup.sh 를 다시 돌릴 때마다 /opt/chiios/bots 는 지우고 새로 깔기 때문이다.
install -d -m 700 -o "$CHII_USER" -g "$CHII_USER" /var/lib/chiios/assistant
install -d /var/lib/chiios/no-work

# 비서가 지켜볼 작업 폴더와 GitHub 계정. 한 번 정하면 /etc/chiios/chiios.conf 에 남고, 바꾸려면 그 파일을 고친다.
conf=/etc/chiios/chiios.conf
CHII_WORK="${CHII_WORK:-}"
CHII_GITHUB="${CHII_GITHUB:-}"
if [ -f "$conf" ]; then
  # shellcheck disable=SC1090
  . "$conf"
fi
if [ -z "$CHII_WORK" ]; then
  # 레포가 작업 폴더 안에 있으면(노트북: C:\Users\..\desktop\sehyun\chiiOS) 그 폴더를 본다.
  # 드라이브나 사용자 폴더 바로 아래(데스크톱: C:\chiiOS)면 너무 넓어서 붙이지 않고 GitHub 만 본다.
  parent="$(dirname "$CHII_DIR")"
  if [ "$(printf '%s' "$parent" | tr -cd / | wc -c)" -ge 5 ]; then
    CHII_WORK="$parent"
  fi
fi
if [ -z "$CHII_GITHUB" ]; then
  CHII_GITHUB="$(git -c safe.directory='*' -C "$CHII_DIR" remote get-url origin 2>/dev/null | sed -nE 's#.*github\.com[:/]+([^/]+)/.*#\1#p')"
fi
printf 'CHII_WORK=%s\nCHII_GITHUB=%s\nCHII_REPO=%s\nCHII_BACKUP=%s\n' "$CHII_WORK" "$CHII_GITHUB" "$CHII_DIR" "$backup_dir" > "$conf"
cp "$conf" /opt/chiios/bots/assistant/.env
echo "작업 폴더: ${CHII_WORK:-(없음, GitHub 만)} · GitHub: ${CHII_GITHUB:-(없음)}"

# 이미지는 매번 굽는다(캐시라 금방).
docker compose --project-directory /opt/chiios/bots/assistant build -q
# 깨어 있으면 새 판·새 설정으로 바꿔 띄우고, 처음이면 띄운다. 대장이 재워 둔 비서는 그대로 둔다.
assist_id="$(docker ps -aq --filter label=com.docker.compose.project=assistant --filter label=com.docker.compose.project.working_dir)"
if [ -z "$assist_id" ] || [ "$(docker inspect -f '{{.State.Running}}' "$assist_id")" = "true" ]; then
  # compose 는 설정이 같으면 이미지가 새로 구워져도 컨테이너를 그대로 둔다(봇 칸에 '새로 구운 판' 이 남았다).
  # 이미지가 바뀌었을 때만 새로 띄운다. 매번 새로 띄우면 setup.sh 를 돌릴 때마다 비서가 재움·깨어남을 남긴다.
  recreate=""
  if [ -n "$assist_id" ] && [ "$(docker inspect -f '{{.Image}}' "$assist_id")" != "$(docker image inspect -f '{{.Id}}' chiios-assistant:latest)" ]; then
    recreate="--force-recreate"
  fi
  docker compose --project-directory /opt/chiios/bots/assistant up -d $recreate
fi

step "백업 (매일 04:00 -> $backup_dir)"
install -m 755 "$CHII_DIR/bin/chii-backup" /usr/local/bin/chii-backup
cat > /etc/systemd/system/chii-backup.service <<EOF
[Unit]
Description=chiiOS backup

[Service]
Type=oneshot
User=$CHII_USER
ExecStart=/usr/local/bin/chii-backup
EOF
# Persistent: 04:00 에 PC 가 꺼져 있었으면 켜진 뒤 바로 한다. 노트북은 새벽에 대개 꺼져 있다.
cat > /etc/systemd/system/chii-backup.timer <<EOF
[Unit]
Description=chiiOS daily backup

[Timer]
OnCalendar=*-*-* 04:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now chii-backup.timer >/dev/null

step "확인"
docker --version
docker compose version
ttyd --version
systemctl is-active docker chii-term chii-home
if is_wsl; then
  echo
  echo "wsl.conf 를 바꿨으면 Windows 에서 'wsl --terminate Debian' 뒤 다시 켜야 기본 사용자·호스트 이름이 적용된다."
fi
echo "홈 화면: http://localhost:$HOME_PORT"
echo "브라우저 터미널: http://localhost:$TTYD_PORT"
