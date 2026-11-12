# 대장이 한 일 모으기. 작업 폴더의 git 저장소(읽기 전용으로 붙인 /work)와 GitHub 계정, 두 곳을 본다.
# 로컬만 보면 다른 PC 나 Codex 가 올린 커밋을 놓치고, GitHub 만 보면 원격이 없는 저장소(대신 등)와
# 아직 커밋하지 않은 작업을 놓친다. 같은 커밋은 SHA 로 하나로 합친다.
import calendar
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOTS = [Path(p) for p in os.environ.get("ASSIST_WORK_ROOTS", "/work").split(":") if p]
GITHUB_USER = os.environ.get("ASSIST_GITHUB_USER", "")
TOKEN_FILE = Path(os.environ.get("ASSIST_DATA", "/data")) / "github-token"
# 이보다 오래 손 안 댄 GitHub 저장소는 커밋을 묻지 않는다. 2025년 공부용 포크가 스무 개 넘게 있다.
GITHUB_SINCE_DAYS = 14


# 작업 폴더는 Windows git 이 관리하는 저장소다. 컨테이너의 Linux git 이 Windows git 과 같은 답을 내도록 맞춘다.
# - safe.directory: 파일 주인이 컨테이너 사용자와 다르게 보인다. 읽기만 하므로 검사를 끈다.
# - core.autocrlf=true: Git for Windows 는 시스템 설정으로 줄 끝을 바꿔 둔다. 이게 없으면 줄 끝만 다른 파일을
#   전부 '바뀜'으로 센다(11-12 실측: debi-marlene 0 -> 391, loa-bot 0 -> 89).
# - checkStat=minimal, trustctime=false: Windows git 이 적어 둔 inode·ctime 이 Linux 에선 달라 보여 파일을
#   전부 다시 읽는다. 크기와 수정 시각만 보게 하면 9개 저장소가 48초에서 8초로 준다.
GIT = ["git", "-c", "safe.directory=*", "-c", "core.autocrlf=true",
       "-c", "core.checkStat=minimal", "-c", "core.trustctime=false"]
# 대화 중 "어제 뭐 했지" 에 매번 저장소를 다 훑으면 기다리게 된다. 잠깐은 같은 답을 쓴다.
CACHE_SEC = 300
_cache = {}


def git(repo, *args, timeout=30):
    try:
        p = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def slug(url):
    """원격 주소에서 owner/repo 를 뽑는다. https 와 ssh 둘 다."""
    m = re.search(r"github\.com[:/]+([^/]+/[^/.]+?)(?:\.git)?/?$", url or "")
    return m.group(1).lower() if m else ""


# 저장소가 작업 폴더 바로 아래에만 있지 않다(포트폴리오는 pf/site). 세 단계까지 찾되, 저장소 안이나
# 의존성 폴더로는 내려가지 않는다. Windows 파일 시스템을 오가는 비용이 커서 넓게 뒤지지 않는다.
DEPTH = 3
SKIP = {"node_modules", ".venv", "venv", "target", "dist", "build", "__pycache__", ".next", ".cache"}


def local_repos():
    found = []

    def walk(d, depth):
        if (d / ".git").exists():
            found.append(d)
            return
        if depth >= DEPTH:
            return
        try:
            subs = sorted(e.path for e in os.scandir(d) if e.is_dir() and e.name not in SKIP and not e.name.startswith("."))
        except OSError:
            return
        for s in subs:
            walk(Path(s), depth + 1)

    for root in ROOTS:
        if root.is_dir():
            walk(root, 0)
    return found


def scan_repo(repo, since):
    code, remote = git(repo, "remote", "get-url", "origin")
    code, log = git(repo, "log", "--all", f"--since=@{int(since)}", "--format=%H%x09%an%x09%ct%x09%s")
    commits = []
    for line in log.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4 and parts[2].isdigit():
            commits.append({"sha": parts[0], "author": parts[1], "t": int(parts[2]), "subject": parts[3]})
    code, st = git(repo, "status", "--porcelain")
    dirty = len([l for l in st.splitlines() if l.strip()])
    # 어느 원격에도 없는 커밋 수. 추적 브랜치(@{u}) 기준으로 세면 푸시 권한이 없는 원본을 따라가는 저장소
    # (kasaterm: 거노 원본을 추적하고 포크로 올림)가 1086개 '안 올림' 으로 나왔다. 원격이 없는 저장소(대신)는
    # 커밋 전부가 여기 잡히는데, 어디에도 백업이 안 됐다는 뜻이라 그게 맞다.
    code, ahead = git(repo, "rev-list", "--count", "HEAD", "--not", "--remotes")
    # 폴더 이름보다 원격 저장소 이름이 알아보기 쉽다(pf/site -> Sehyun-portfolio, kasaspace -> chiispace).
    m = re.search(r"github\.com[:/]+[^/]+/([^/]+?)(?:\.git)?/?$", remote.strip())
    return {
        "name": m.group(1) if m else repo.name,
        "slug": slug(remote.strip()),
        "remote": bool(remote.strip()),
        "commits": commits,
        "dirty": dirty,
        "ahead": int(ahead.strip()) if code == 0 and ahead.strip().isdigit() else 0,
    }


def scan_local(since):
    # 저장소마다 Windows 파일 시스템을 오가느라 기다리는 시간이 대부분이라 같이 훑는다.
    repos = local_repos()
    if not repos:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(repos))) as pool:
        return list(pool.map(lambda r: scan_repo(r, since), repos))


def gh(path, timeout=15):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "chiios-assistant"}
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except OSError:
        pass
    req = urllib.request.Request("https://api.github.com" + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def utc(stamp):
    # GitHub 시각은 UTC("...Z")다. mktime 은 지역 시각으로 읽어 9시간 어긋나므로 timegm 으로 읽는다.
    try:
        return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0


def scan_github(since):
    """계정 저장소 중 최근에 밀어 넣은 것의 기본 브랜치 커밋. 토큰이 없으면 공개 저장소만 보인다."""
    if not GITHUB_USER:
        return [], "GitHub 계정이 설정되지 않음"
    has_token = TOKEN_FILE.exists()
    path = "/user/repos?affiliation=owner&sort=pushed&per_page=50" if has_token \
        else f"/users/{GITHUB_USER}/repos?sort=pushed&per_page=50"
    repos = gh(path)
    if repos is None:
        return [], "GitHub 에 닿지 않음"
    cutoff = time.time() - GITHUB_SINCE_DAYS * 86400
    out = []
    for r in repos:
        pushed = utc(r.get("pushed_at"))
        if pushed < max(since, cutoff):
            continue
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since))
        items = gh(f"/repos/{r['full_name']}/commits?since={iso}&per_page=100") or []
        commits = []
        for c in items:
            try:
                when = utc(c["commit"]["committer"]["date"])
                commits.append({"sha": c["sha"], "author": c["commit"]["author"]["name"], "t": int(when),
                                "subject": c["commit"]["message"].splitlines()[0]})
            except (KeyError, ValueError, TypeError):
                continue
        out.append({"name": r["name"], "slug": r["full_name"].lower(), "private": r.get("private", False), "commits": commits})
    return out, None if has_token else "토큰이 없어 비공개 저장소는 로컬에 있는 것만 보임"


def recent_work(since):
    """저장소별로 합친 결과: [{name, commits[], dirty, ahead}] 과 참고 메모."""
    key = int(since // 600)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SEC:
        return hit[1]
    result = _recent_work(since)
    _cache.clear()
    _cache[key] = (time.time(), result)
    return result


def _recent_work(since):
    local = scan_local(since)
    remote, note = scan_github(since)
    merged = {}
    for r in local:
        key = r["slug"] or f"local:{r['name']}"
        # 같은 저장소의 작업 사본(worktree, pf/site 와 pf/site-wt-braincrew)은 하나로 합친다. 커밋은 겹치니
        # SHA 로 합치고, 커밋 안 한 변경은 사본마다 따로라 더한다. 이름은 먼저 찾은(짧은) 쪽을 쓴다.
        m = merged.get(key)
        if m:
            m["commits"].update({c["sha"]: c for c in r["commits"]})
            m["dirty"] += r["dirty"]
            m["ahead"] = max(m["ahead"] or 0, r["ahead"] or 0)
            continue
        merged[key] = {"name": r["name"], "commits": {c["sha"]: c for c in r["commits"]},
                       "dirty": r["dirty"], "ahead": r["ahead"], "local": True, "remote": r["remote"]}
    for r in remote:
        m = merged.setdefault(r["slug"], {"name": r["name"], "commits": {}, "dirty": 0, "ahead": None,
                                          "local": False, "remote": True})
        for c in r["commits"]:
            m["commits"].setdefault(c["sha"], c)
    repos = []
    for m in merged.values():
        commits = sorted(m["commits"].values(), key=lambda c: c["t"], reverse=True)
        if commits or m["dirty"] or m["ahead"]:
            repos.append({**m, "commits": commits})
    repos.sort(key=lambda r: (-len(r["commits"]), -r["dirty"], r["name"]))
    return repos, note
