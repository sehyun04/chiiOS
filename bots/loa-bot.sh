#!/usr/bin/env bash
# 니나브(loa-bot)를 chiiOS 의 Docker 로 올릴 준비: 코드, .env, 첫 데이터, 이미지 빌드.
# 띄우기는 일부러 뺐다. 지금 .env 의 디스코드 토큰이 Oracle 운영 봇과 같아서
# 둘이 같이 켜지면 인터랙션이 두 인스턴스로 갈려 응답이 꼬인다. 운영을 멈춘 동안에만 켠다.
#
#   wsl -d Debian -- bash /mnt/c/Users/kshkj/desktop/sehyun/chiiOS/bots/loa-bot.sh
set -euo pipefail

SRC="${LOA_SRC:-/mnt/c/Users/kshkj/desktop/sehyun/loa-bot}"
DEST="${LOA_DEST:-$HOME/loa-bot}"

# Windows 쪽 작업 폴더를 원본으로 clone/pull 한다. 커밋된 것만 따라오므로
# 작업 중인 미커밋 변경이 봇에 섞이지 않고, Debian 안에 GitHub 키를 둘 필요도 없다.
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  git clone "$SRC" "$DEST"
fi

# .env 는 레포 밖(gitignore)이라 따로 옮긴다. Windows 쪽이 원본이라 매번 덮어쓴다.
install -m 600 "$SRC/.env" "$DEST/.env"

# SQLite 를 /mnt/c 에 두면 느리고 파일 잠금도 믿을 수 없어 Debian 안에 둔다.
# 처음 한 번만 Windows 쪽 개발 DB 를 씨앗으로 복사하고, 그 뒤로는 덮어쓰지 않는다.
if [ ! -e "$DEST/data/loabot.db" ] && [ -f "$SRC/data/loabot.db" ]; then
  install -d "$DEST/data"
  cp "$SRC/data/loabot.db" "$DEST/data/"
fi

cd "$DEST"
docker compose build
echo
echo "준비 끝: $(git log -1 --oneline)"
echo "켜기: cd $DEST && docker compose up -d  (운영 봇을 먼저 멈출 것)"
