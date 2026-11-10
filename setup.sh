#!/usr/bin/env bash
# chiiOS: 순정 Debian 13 위에 봇 실행 환경(Docker)과 브라우저 터미널(ttyd)을 얹는다.
# 지금은 WSL 에서 연습하고 나중에 i7 PC 실기에도 그대로 돌릴 거라, WSL 전용 처리는 is_wsl 안에만 둔다.
# 몇 번을 다시 돌려도 결과가 같게 짰다. 설정을 바꾸면 이 파일을 고치고 다시 돌리면 된다.
#
#   WSL:  wsl -d Debian -u root -- bash /mnt/c/.../chiiOS/setup.sh
#   실기: sudo bash setup.sh
set -euo pipefail

CHII_USER="${CHII_USER:-sehyun}"
CHII_HOST="${CHII_HOST:-chiios}"
TTYD_PORT="${TTYD_PORT:-7681}"
TTYD_VERSION=1.7.7

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
EOF
else
  step "호스트 이름"
  hostnamectl set-hostname "$CHII_HOST"
fi

step "기본 패키지"
apt-get update -q
apt-get install -y -q ca-certificates curl git htop

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
ExecStart=/usr/local/bin/ttyd --interface 127.0.0.1 --port $TTYD_PORT --writable -t titleFixed=chiiOS bash -l
Restart=always

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable chii-term.service
systemctl restart chii-term.service

step "확인"
docker --version
docker compose version
ttyd --version
systemctl is-active docker chii-term
if is_wsl; then
  echo
  echo "wsl.conf 를 바꿨으면 Windows 에서 'wsl --terminate Debian' 뒤 다시 켜야 기본 사용자·호스트 이름이 적용된다."
fi
echo "브라우저 터미널: http://localhost:$TTYD_PORT"
