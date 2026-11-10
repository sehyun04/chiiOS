# chiiOS

봇을 돌리려고 손에 맞춘 Debian. Windows 위 WSL 에 올린다. 노트북에서 연습했고, 상시 운영은 계속 켜 두는 i7 데스크톱(게임도 하는 PC)에 같은 방식으로 옮긴다.

## 구성

- Debian 13 (trixie), systemd
- Docker Engine + Compose 플러그인 (Docker 공식 저장소)
- 브라우저 터미널: ttyd 1.7.7, `http://localhost:7681`
- 사용자 `sehyun`, 호스트 이름 `chiios`
- 꺼진 Debian 을 다시 켜는 작업 스케줄러 작업 `chiiOS`

## 새 PC 에 설치

```powershell
git clone https://github.com/sehyun04/chiiOS.git
cd chiiOS
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` 이 하는 일, 순서대로:

1. WSL 이 없으면 관리자 권한으로 설치한다(UAC 창). 이때만 재부팅이 필요하고, 재부팅 뒤 `install.ps1` 을 다시 돌린다.
2. `wslconfig` 를 `%USERPROFILE%\.wslconfig` 로 복사한다. 이미 다른 내용이 있으면 덮어쓰지 않고 멈춘다(`-Force` 면 백업 후 덮어쓰기).
3. Debian 이 없으면 `wsl --install -d Debian --no-launch` 로 깐다.
4. Debian 안에서 root 로 `setup.sh` 를 돌린다. `/etc/wsl.conf` 가 바뀌었으면 Debian 을 껐다 켜서 기본 사용자·호스트 이름을 적용한다.
5. `autostart.ps1` 로 자동 켜기 작업을 건다.
6. systemd, 사용자, docker·chii-term, 브라우저 터미널 응답을 확인한다.

여러 번 돌려도 결과가 같다. 설정을 바꾸면 해당 파일을 고치고 `install.ps1` 을 다시 돌린다.

## 쓰는 법

| 하려는 것 | 방법 |
|---|---|
| 브라우저 터미널 열기 | `start.cmd` 더블클릭 (꺼져 있으면 켜고 연다) |
| 터미널로 들어가기 | `wsl -d Debian` |
| Debian 안 설정만 다시 적용 | 이 폴더에서 `wsl -d Debian -u root -- bash ./setup.sh` |
| 끄기 | `wsl --terminate Debian` (WSL 전체는 `wsl --shutdown`). 자동 켜기가 걸려 있으면 5분 안에 다시 켜진다 |
| 자동 켜기 걸기·떼기 | `powershell -ExecutionPolicy Bypass -File autostart.ps1` (떼기는 뒤에 `-Remove`) |

- WSL 은 Windows 재부팅이나 WSL 자동 업데이트(2026-11-10 3.0.1 -> 3.0.5 에서 겪음) 뒤에 Debian 을 다시 켜 주지 않는다. 그래서 `autostart.ps1` 이 작업 스케줄러에 `chiiOS` 작업을 걸어, 로그온할 때와 그 뒤 5분마다 Debian 을 깨운다. 관리자 권한은 필요 없다.
- 작업은 로그온한 내 계정으로 돈다. WSL 배포판이 사용자별이라, Windows 에 로그온하기 전에는 켜지지 않는다. 재부팅 뒤에는 Parsec 등으로 들어가 로그온하면 된다.

## 상시 운영 PC 에서 챙길 것

- 절전 모드는 "안 함". 절전에 들어가면 봇도 멈추고 Parsec 도 붙지 못한다. 화면 끄기는 괜찮다.
- WSL2 는 Windows 가상화 기능을 켠다. 일부 게임 안티치트가 이것과 부딪히므로, 설치 뒤 하는 게임을 한 번씩 켜 본다.

## 봇

| 봇 | 자리 | 평소 상태 |
|---|---|---|
| 니나브(loa-bot) | Debian 안 `~/loa-bot` | 이미지만 있고 꺼 둔다 |

- 준비·갱신: 이 폴더에서 `wsl -d Debian -- bash ./bots/loa-bot.sh`. Windows 쪽 loa-bot 의 커밋된 코드와 `.env` 를 가져와 이미지를 굽는다. 띄우지는 않는다. loa-bot 이 노트북과 다른 곳에 있으면 `LOA_SRC=/mnt/c/...` 로 알려 준다.
- 디스코드 토큰이 Oracle 운영 봇과 같다. 둘이 같이 켜지면 인터랙션이 두 쪽으로 갈려 응답이 꼬이므로, 운영을 멈춘 동안에만 켠다.
  1. `ssh loa docker stop loa-bot`
  2. Debian 에서 `cd ~/loa-bot && docker compose up -d` (끄기는 `docker compose stop`)
  3. `ssh loa docker start loa-bot`
- 켜 둔 채로 두면 `restart: unless-stopped` 라 Debian 이 다시 켜질 때 같이 살아나 운영과 겹친다. 다 쓰면 꼭 `stop` 한다.

## `wslconfig` (Windows 쪽 WSL 전역 설정)

`install.ps1` 이 `%USERPROFILE%\.wslconfig` 로 복사한다. 바꾼 뒤에는 `wsl --shutdown` 해야 적용된다(`install.ps1` 은 바뀌었을 때 알아서 한다).

- `instanceIdleTimeout=-1`: 기본값이면 WSL 창이 없을 때 15초쯤 뒤 Debian 이 꺼져 봇과 터미널도 같이 죽는다.
- `memory=8GB`: 계속 켜 두므로 기본값(메모리 절반)보다 줄였다.

## 주의

- 브라우저 터미널은 `127.0.0.1` 에만 열려 있다. 셸을 통째로 내주는 것이라 다른 기기에서 열려면 Tailscale 같은 인증을 먼저 둔다.
- WSL 에서는 sudo 비밀번호를 없앴다. Windows 계정이면 어차피 `wsl -u root` 로 root 가 되기 때문이다. WSL 이 아닌 순정 Debian 에 깔면 `setup.sh` 가 이 설정을 건너뛴다.
