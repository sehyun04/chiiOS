#!/usr/bin/env bash
# 비서 봇 굽기: bots/assistant 를 이미지로 만든다. 띄우지는 않는다(봇 칸의 깨우기 몫).
# 코드가 레포 안에 있으니 가져올 것도 없다. 홈 화면 봇 칸의 다시 굽기가 이 파일을 돌린다.
set -euo pipefail
cd "$(dirname "$0")/assistant"
docker compose build
