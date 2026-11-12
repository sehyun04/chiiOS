# chiiOS

봇을 돌리려고 손에 맞춘 Debian. Windows 위 WSL 에 올린다. 노트북에서 연습했고, 상시 운영은 계속 켜 두는 i7 데스크톱(게임도 하는 PC)에 같은 방식으로 옮긴다.

## 구성

- Debian 13 (trixie), systemd
- Docker Engine + Compose 플러그인 (Docker 공식 저장소)
- 홈 화면: `http://localhost:7682` (`chii-home.service`, `home/`). 1번 [비서][터미널] 칸·봇·오늘 할 일·오늘 기록 네 칸과 아래 상태줄, 낮·밤 두 벌
- 비서: 홈 화면 1번 칸 [비서] 탭. 오늘 정리, 할 일 관리, 봇 돌보기를 말로 한다(아래 '비서')
- 브라우저 터미널: ttyd 1.7.7, `http://localhost:7681` (`chii-term.service`). 홈 화면 1번 칸 [터미널] 탭은 이 ttyd 에 웹소켓으로 붙어 xterm 으로 직접 그린다
- 바탕화면·시작 메뉴의 `chiiOS` 바로가기: 홈 화면을 주소창 없는 Edge 앱 창으로 연다
- 사용자 `sehyun`, 호스트 이름 `chiios`
- 꺼진 Debian 을 다시 켜는 작업 스케줄러 작업 `chiiOS`

겉모습은 치이스페(`kasaspace`)의 색·글꼴·얼굴 그림을 그대로 쓴다. 봇은 봇 이름 그대로 두고, 캐릭터는 할 일 칸과 상태줄 말풍선의 꾸밈으로만 쓴다. 밤 색은 치이스페에 없어 같은 색조를 어두운 코코아 바탕으로 옮겨 만들었다(보라 없음).

## 새 PC 에 설치

git 이 없는 PC 면 먼저 깐다(UAC 창이 뜬다). 깐 뒤 PATH 를 다시 읽어야 같은 창에서 `git` 이 잡힌다.

```powershell
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
```

그다음 받아서 깐다. 비공개 레포라 clone 때 GitHub 로그인 창이 한 번 뜬다.

```powershell
git clone https://github.com/sehyun04/chiiOS.git $HOME\chiiOS
cd $HOME\chiiOS
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

`install.ps1` 이 하는 일, 순서대로:

1. WSL 이 없으면 관리자 권한으로 설치한다(UAC 창). 이때만 재부팅이 필요하다. 재부팅하고 로그온하면 `install.ps1` 이 PowerShell 창으로 저절로 이어 돈다(`RunOnce` 에 한 번만 걸어 둔다).
2. `wslconfig` 를 `%USERPROFILE%\.wslconfig` 로 복사한다. 이미 다른 내용이 있으면 덮어쓰지 않고 멈춘다(`-Force` 면 백업 후 덮어쓰기). 사용자 폴더에 내 계정으로 못 쓰는 PC 면(i7 데스크톱이 그랬다) 같은 복사를 관리자 권한으로 다시 한다(UAC 창).
3. Debian 이 없으면 `wsl --install -d Debian --no-launch` 로 깐다.
4. Debian 안에서 root 로 `setup.sh` 를 돌린다. `/etc/wsl.conf` 가 바뀌었으면 Debian 을 껐다 켜서 기본 사용자·호스트 이름을 적용한다.
5. `autostart.ps1` 로 자동 켜기 작업을 건다.
6. `shortcut.ps1` 로 바탕화면과 시작 메뉴에 `chiiOS` 바로가기를 만든다.
7. systemd, 사용자, docker·chii-term·chii-home, 브라우저 터미널과 홈 화면 응답을 확인한다.

여러 번 돌려도 결과가 같다. 설정을 바꾸면 해당 파일을 고치고 `install.ps1` 을 다시 돌린다.

## 쓰는 법

| 하려는 것 | 방법 |
|---|---|
| 홈 화면 열기 | 바탕화면의 `chiiOS` (또는 `start.cmd`). 꺼져 있으면 켜고, 다 뜨면 앱 창으로 연다 |
| 칸 옮기기 | `Alt+1~4`. 터미널 안에서 눌러도 셸로 가지 않고 칸이 옮겨진다. 1번 칸 안에서 `Alt+1` 을 한 번 더 누르면 비서·터미널 탭이 바뀐다 |
| 비서에게 말 걸기 | 1번 칸 [비서] 탭, 또는 상태줄 하치와레 말풍선을 누른다 |
| 낮·밤 바꾸기 | 상태줄 시계 옆 단추. 자동(저녁 7시~아침 7시 밤) -> 낮 -> 밤 순서로 돈다 |
| 터미널 복사·붙여넣기 | 글을 고르고 `Ctrl+C`(고른 글이 없으면 셸에 인터럽트), `Ctrl+V` |
| 터미널로 들어가기 | `wsl -d Debian` |
| Debian 안 설정만 다시 적용 | 이 폴더에서 `wsl -d Debian -u root -- bash ./setup.sh` |
| 끄기 | `wsl --terminate Debian` (WSL 전체는 `wsl --shutdown`). 자동 켜기가 걸려 있으면 5분 안에 다시 켜진다 |
| 자동 켜기 걸기·떼기 | `powershell -ExecutionPolicy Bypass -File autostart.ps1` (떼기는 뒤에 `-Remove`) |
| 바로가기 만들기·지우기 | `powershell -ExecutionPolicy Bypass -File shortcut.ps1` (지우기는 뒤에 `-Remove`) |
| 홈 화면 고친 것 반영 | 이 폴더에서 `git pull` 뒤 `install.ps1` (또는 Debian 설정만 `wsl -d Debian -u root -- bash ./setup.sh`). 돌아가는 화면은 `/opt/chiios` 의 사본이다 |

- WSL 은 Windows 재부팅이나 WSL 자동 업데이트(2026-11-10 3.0.1 -> 3.0.5 에서 겪음) 뒤에 Debian 을 다시 켜 주지 않는다. 그래서 `autostart.ps1` 이 작업 스케줄러에 `chiiOS` 작업을 걸어, 로그온할 때와 그 뒤 5분마다 Debian 을 깨운다. 관리자 권한은 필요 없다.
- 작업은 로그온한 내 계정으로 돈다. WSL 배포판이 사용자별이라, Windows 에 로그온하기 전에는 켜지지 않는다. 재부팅 뒤에는 Parsec 등으로 들어가 로그온하면 된다.
- 앱 창은 `msedge --app` 이다. Edge 는 창 크기를 기억하므로, 홈 화면이 처음 한 번만 창을 넉넉히 키우고 그 뒤로는 손대지 않는다. 바로가기는 `conhost --headless` 로 `start.cmd` 를 감싸 Debian 이 뜨는 동안 검은 창이 안 보인다.

## 비서

니나브처럼 따로 도는 봇(`bots/assistant/`, 컨테이너 `assistant`)이다. 봇 칸에 "비서"로 뜨고, 홈 화면 1번 칸 [비서] 탭이 이 봇과 이야기하는 창이다.

```
홈 화면 [비서] 탭 ──> chii-home(7682) ──> 비서 봇(7683) ──> Anthropic
                          ^                    │
                          └── 할 일·봇·상태 ───┘
```

- 할 줄 아는 것: 오늘 정리, 할 일 더하기·끝내기·지우기, 봇 상태 묻기·깨우기·재우기·다시 굽기·기록 읽기, 최근 한 일 모으기("어제 뭐 했지"). 터미널 명령은 대신 치지 않는다. 앞으로 검증·검토(대장이 만든 것), AI·GitHub 트렌드를 도구로 하나씩 붙인다.
- 아침 보고: 매일 08:00(그 시각에 꺼져 있었으면 켜진 뒤 1분 안)에 [비서] 탭에 올라오고, 상태줄 말풍선이 "아침 보고 왔어" 로 알린다. 봇 상태, 밤사이 쓰러진 봇, 남은 할 일, 지난 보고 뒤의 커밋, 커밋 안 한 변경, 어느 원격에도 없는 커밋(백업 안 됨)을 담는다. 숫자는 스크립트가 세고 비서는 맨 위 한마디만 쓴다(열쇠가 없으면 정해진 한마디). 머리줄 [지금 보고] 로 바로 받을 수도 있다.
- 한 일을 보는 곳: 작업 폴더의 모든 git 저장소(읽기 전용으로 `/work` 에 붙임, 세 단계 안쪽까지 찾고 node_modules 같은 폴더는 건너뜀, 이름은 원격 저장소 이름)와 GitHub 계정. 로컬만 보면 다른 PC·Codex 가 올린 커밋을, GitHub 만 보면 원격이 없는 저장소와 커밋 안 한 작업을 놓친다. 작업 폴더와 계정은 `/etc/chiios/chiios.conf` 에 있다(`setup.sh` 가 처음 정한다: 레포 바로 위 폴더, 레포 원격의 계정. 데스크톱처럼 `C:\chiiOS` 에 두면 작업 폴더는 비워 두고 GitHub 만 본다).
- 비공개 저장소를 GitHub 쪽에서도 보려면 읽기 전용 토큰(fine-grained, Contents·Metadata 읽기)을 `/var/lib/chiios/assistant/github-token`(600)에 둔다. 없으면 비공개 저장소는 작업 폴더에 있는 것만 보인다.
- 컨테이너의 Linux git 은 Windows git 과 같은 답을 내게 `core.autocrlf=true`, `core.checkStat=minimal` 로 돌린다. 이게 없으면 줄 끝만 다른 파일을 전부 바뀐 걸로 세고(11-12 실측 0 -> 391), 파일을 다 다시 읽어 48초가 걸렸다(지금 5초).
- 비서는 Docker 를 직접 만지지 않고 홈 화면 API 에 부탁한다. 그래서 니나브 깨우기 전 확인 같은 규칙은 홈 화면 한곳에만 있다. 주의가 있는 봇을 깨우라고 하면 대화 안에 확인 단추가 뜨고, 단추는 띄운 지 10분 안의 마지막 것만 눌린다. 비서는 자기 자신을 재우지 못한다.
- 머리: Anthropic API, 기본 모델 `claude-haiku-5-5`(effort `low`). 바꾸려면 `bots/assistant/compose.yaml` 에 `ASSIST_MODEL`·`ASSIST_EFFORT` 를 준다. SDK 는 이미지 안에만 `anthropic==2.3.0` 으로 고정해 깐다(`requirements.txt`). 홈 화면 서버는 표준 라이브러리만 쓴다.
- 열쇠: 처음 열면 [비서] 탭에 열쇠 칸이 뜬다. 넣으면 한 번 맞춰 본 뒤 `/var/lib/chiios/assistant/anthropic-key`(600)에만 저장하고, 화면과 API 응답에는 다시 내보내지 않는다.
- 같은 Anthropic 계정 안의 키는 잔액을 같이 쓴다. 비서가 잔액을 다 쓰면 니나브 답변도 멈추므로, Console 에서 월 한도를 건 작업 공간(`chiiOS`)을 만들고 그 안에서 만든 키를 넣는다.
- 대화는 `/var/lib/chiios/assistant/chat.jsonl` 에 쌓이고, 모델에게는 최근 20마디만 보낸다. [새 대화] 를 누르면 지우지 않고 `chat-archive/` 로 옮긴다. 레포 사본(`/opt/chiios`)은 `setup.sh` 때마다 새로 깔리므로 대화·열쇠는 거기 두지 않는다.
- `setup.sh` 는 비서 이미지를 매번 굽고, 처음 깔 때만 띄운다(재워 둔 비서를 다시 깨우지 않게). 코드가 바뀌면 봇 칸에 '새로 구운 판' 이 뜨고, 재웠다 깨우면 바뀐다.
- 비서 문(7683)은 홈 화면만 두드린다. Windows 브라우저에서도 열리는 주소라 `Host` 와 `X-Chii` 를 보고 막는다.
- 레포를 따로 뗄지는 아직 정하지 않았다. `bots/assistant/` 가 혼자 굽고 돌 수 있게 묶여 있어서, 떼기로 하면 `git subtree split --prefix=bots/assistant` 로 이력째 옮긴다.

## 상시 운영 PC 에서 챙길 것

- 절전 모드는 "안 함". 절전에 들어가면 봇도 멈추고 Parsec 도 붙지 못한다. 화면 끄기는 괜찮다.
- WSL2 는 Windows 가상화 기능을 켠다. 일부 게임 안티치트가 이것과 부딪히므로, 설치 뒤 하는 게임을 한 번씩 켜 본다.
- 봇 기록(`docker logs`)은 따로 정하지 않은 봇도 컨테이너마다 10MB 파일 3개까지만 남는다(`/etc/docker/daemon.json`, `setup.sh` 가 건다). 몇 달 켜 둬도 디스크를 다 먹지 않게.

## 백업

할 일, 오늘 기록, 비서 대화는 WSL 디스크 안에만 있어서 Debian 을 다시 깔면 사라진다. 그래서 매일 Windows 쪽에 묶어 둔다.

- 매일 04:00 에 레포 폴더 `backup/chiios-날짜.tar.gz` 로 쌓인다(그 시각에 꺼져 있었으면 켜진 뒤 바로). 두 주치를 남긴다. git 에는 올리지 않는다.
- 비서 열쇠(Anthropic 키, GitHub 토큰)는 넣지 않는다. Windows 쪽 폴더는 동기화·공유될 수 있어 비밀을 두지 않는다. 다시 깐 뒤에는 열쇠만 다시 넣는다.
- 되살리기: Debian 을 새로 깔고 `install.ps1`(또는 `setup.sh`)을 돌리면, 할 일 파일이 없을 때 마지막 백업을 알아서 편다. 데이터가 이미 있으면 손대지 않는다.
- 지금 바로 뜨려면 Debian 에서 `chii-backup`. 손으로 되살리려면 `tar -xzf backup/chiios-....tar.gz` 를 풀어 `home/` 은 `~/.local/share/chiios/` 로, `assistant/` 는 `/var/lib/chiios/assistant/` 로 옮긴다.

## 봇

| 봇 | 자리 | 평소 상태 |
|---|---|---|
| 니나브(loa-bot) | Debian 안 `~/loa-bot` | 이미지만 있고 꺼 둔다 |
| 비서(assistant) | 레포 `bots/assistant/` (사본 `/opt/chiios/bots/assistant`) | 늘 깨어 있다 |

- 홈 화면 봇 칸의 단추: 깨우기·재우기(`docker compose up -d`·`stop`), 다시 굽기(`bots/<봇>.sh`), 기록(`docker logs` 마지막 300줄).
- 봇 이름과 깨우기 전 주의 문구는 `bots/bots.json` 에 둔다. 주의 문구가 있는 봇은 깨우기를 누르면 확인 창이 먼저 뜬다.
- 준비·갱신을 손으로 하려면 이 폴더에서 `wsl -d Debian -- bash ./bots/loa-bot.sh`. Windows 쪽 loa-bot 의 커밋된 코드와 `.env` 를 가져와 이미지를 굽는다. 띄우지는 않는다. loa-bot 이 노트북과 다른 곳에 있으면 `LOA_SRC=/mnt/c/...` 로 알려 준다.
- 디스코드 토큰이 Oracle 운영 봇과 같다. 둘이 같이 켜지면 인터랙션이 두 쪽으로 갈려 응답이 꼬이므로, 운영을 멈춘 동안에만 켠다. 홈 화면의 확인 창은 묻기만 하고 Oracle 을 재우지는 않는다.
  1. `ssh loa docker stop loa-bot`
  2. 홈 화면에서 깨우기 (또는 Debian 에서 `cd ~/loa-bot && docker compose up -d`)
  3. 다 쓰면 재우기, 그다음 `ssh loa docker start loa-bot`
- 켜 둔 채로 두면 `restart: unless-stopped` 라 Debian 이 다시 켜질 때 같이 살아나 운영과 겹친다. 다 쓰면 꼭 재운다.

## `wslconfig` (Windows 쪽 WSL 전역 설정)

`install.ps1` 이 `%USERPROFILE%\.wslconfig` 로 복사한다. 바꾼 뒤에는 `wsl --shutdown` 해야 적용된다(`install.ps1` 은 바뀌었을 때 알아서 한다).

- `instanceIdleTimeout=-1`: 기본값이면 WSL 창이 없을 때 15초쯤 뒤 Debian 이 꺼져 봇과 터미널도 같이 죽는다.
- `memory=8GB`: 계속 켜 두므로 기본값(메모리 절반)보다 줄였다.

## 주의

- 브라우저 터미널과 홈 화면은 `127.0.0.1` 에만 열려 있다. 셸과 봇 단추를 통째로 내주는 것이라 다른 기기에서 열려면 Tailscale 같은 인증을 먼저 둔다.
- 비서 열쇠·대화·확인 단추도 같은 규칙 아래 있다. 열쇠를 넣는 요청은 POST 라 `X-Chii` 머리글 없이는 안 받는다.
- 봇은 compose 로 띄운 컨테이너(작업 폴더 라벨이 있는 것)만 센다. compose 가 구운 이미지에는 project 라벨이 박혀 있어서, 시험 삼아 `docker run` 한 컨테이너까지 봇으로 잡혀 오늘 기록이 더러워진 적이 있다.
- 다른 사이트가 몰래 요청하지 못하게, 홈 화면은 `localhost` 이름으로 온 요청만 받고 바꾸는 요청(POST)에는 `X-Chii: 1` 머리글을 요구한다. ttyd 는 `--check-origin` 으로 다른 출처의 웹소켓을 막는다.
- 터미널 칸의 웹소켓(`/term/ws`)은 홈 화면 서버가 ttyd 로 바이트 그대로 잇는다. `Origin` 이 홈 화면(`http://localhost:7682`)이 아니면 403 이다. ttyd 쪽으로 넘길 때는 Origin·Host 를 ttyd 주소로 맞춰 `--check-origin` 도 그대로 통과한다.
- 터미널 글꼴 D2Coding(OFL, 예약 이름 D2Coding)은 글리프를 건드리지 않고 woff2 로만 다시 싸서 `home/static/fonts/` 에 둔다. 보는 PC 에 글꼴이 없어도 한글 폭이 맞는다. xterm 5.5 는 `home/static/vendor/xterm/`(MIT).
- 홈 화면이 7680 이 아니라 7682 인 이유: 7680 은 Windows 배달 최적화(DoSvc)가 쥐고 있어 Windows 쪽 `localhost:7680` 이 Debian 까지 오지 않는다.
- 할 일과 홈 화면이 받아 적은 기록은 Debian 안 `~/.local/share/chiios/` 에 있다. 재부팅 기록은 systemd 저널에서 읽는다.
- WSL 에서는 sudo 비밀번호를 없앴다. Windows 계정이면 어차피 `wsl -u root` 로 root 가 되기 때문이다. WSL 이 아닌 순정 Debian 에 깔면 `setup.sh` 가 이 설정을 건너뛴다.
