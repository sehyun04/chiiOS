# chiiOS 를 이 Windows 에 깐다: .wslconfig, Debian, setup.sh, 자동 켜기, 바로가기, 확인까지.
# 노트북에서 손으로 밟았던 순서를 그대로 옮겼다. 여러 번 돌려도 결과가 같다.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Force   기존 .wslconfig 를 백업하고 덮어쓰기
param([switch]$Force)

# 일부러 Stop 을 걸지 않는다. PowerShell 5.1 은 네이티브 명령의 stderr(apt 경고 등)를
# 오류로 감싸 멈춰 버리므로, wsl 결과는 종료 코드로만 판단한다.
$ErrorActionPreference = 'Continue'
# 이게 없으면 wsl.exe 가 UTF-16 으로 출력해 배포판 이름 비교가 안 된다.
$env:WSL_UTF8 = '1'

$distro = 'Debian'
$ttydPort = 7681  # setup.sh 의 TTYD_PORT 기본값과 같아야 한다
$homePort = 7682  # setup.sh 의 HOME_PORT 기본값과 같아야 한다

function Step($msg) { Write-Host "`n== $msg" }
function Fail($msg) { Write-Host "실패: $msg" -ForegroundColor Red; exit 1 }
function Invoke-Wsl {
    & wsl.exe @args
    if ($LASTEXITCODE -ne 0) { Fail "wsl $args (exit $LASTEXITCODE)" }
}

# $pairs 는 @(원본, 대상) 쌍의 목록. 사용자 폴더 맨 위에 내 계정으로 파일을 못 만드는 PC 가 있었다
# (i7 데스크톱, 원인 모름. 관리자 창에서는 써졌다). 그래서 액세스 거부면 같은 복사를 관리자 권한으로 다시 한다.
function Copy-Files($pairs) {
    try {
        foreach ($p in $pairs) { Copy-Item -LiteralPath $p[0] -Destination $p[1] -Force -ErrorAction Stop }
        return
    } catch {
        if ($_.CategoryInfo.Category -ne 'PermissionDenied') { Fail "$_" }
    }
    Write-Host '이 계정으로는 못 쓴다. 관리자 권한으로 복사한다(UAC 창이 뜬다).'
    $lines = foreach ($p in $pairs) {
        $from = $p[0] -replace "'", "''"
        $to = $p[1] -replace "'", "''"
        "Copy-Item -LiteralPath '$from' -Destination '$to' -Force"
    }
    # 경로에 한글·공백이 섞여도 인자 따옴표가 깨지지 않게 명령을 통째로 인코딩해 넘긴다.
    $cmd = "`$ErrorActionPreference = 'Stop'`n" + ($lines -join "`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
    try {
        $proc = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop `
            -ArgumentList '-NoProfile', '-NonInteractive', '-EncodedCommand', $encoded
    } catch {
        Fail "관리자 권한을 받지 못했다: $_"
    }
    # 관리자 프로세스는 종료 코드를 못 받아 올 때가 있어($null) 그때는 아래 해시 비교에 맡긴다.
    if ($null -ne $proc.ExitCode -and $proc.ExitCode -ne 0) {
        Fail "관리자 권한으로도 복사가 막혔다(exit $($proc.ExitCode)). 백신이 막는지 본다."
    }
}

Step 'WSL'
& wsl.exe --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    # WSL 기능 설치만 관리자 권한과 재부팅이 필요하다. 그 뒤 단계는 전부 내 계정으로 된다.
    Write-Host 'WSL 이 없다. 관리자 권한으로 설치한다(UAC 창이 뜬다).'
    try {
        Start-Process wsl.exe -Verb RunAs -Wait -ArgumentList '--install', '--no-distribution' -ErrorAction Stop
    } catch {
        # UAC 를 취소했을 때 아래 RunOnce 까지 걸면 재부팅할 때마다 설치 창이 다시 뜬다.
        Fail "WSL 설치를 시작하지 못했다: $_"
    }
    # 재부팅 뒤 손으로 다시 돌리는 걸 잊기 쉽다(i7 데스크톱에서 "재부팅하니 아무것도 없다").
    # RunOnce 는 다음 로그온 때 한 번 돌고 Windows 가 지운다. -NoExit 라 결과를 읽을 수 있다.
    $runOnce = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
    # -Force 로 만들면 이미 있는 키의 값들을 날릴 수 있어서, 없을 때만 만든다.
    if (-not (Test-Path $runOnce)) { New-Item $runOnce | Out-Null }
    $resume = "powershell.exe -NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($Force) { $resume += ' -Force' }
    Set-ItemProperty $runOnce -Name 'chiiOS-install' -Value $resume
    Write-Host '재부팅하고 로그온하면 이 스크립트가 저절로 이어 돈다.'
    exit 1
}
Write-Host '있다.'

Step '.wslconfig'
$src = Join-Path $PSScriptRoot 'wslconfig'
$dst = Join-Path $env:USERPROFILE '.wslconfig'
$changed = $false
if (-not (Test-Path $dst)) {
    Copy-Files @(, @($src, $dst))
    $changed = $true
    Write-Host "새로 썼다: $dst"
} elseif ((Get-FileHash $src).Hash -eq (Get-FileHash $dst).Hash) {
    Write-Host '이미 같다.'
} elseif ($Force) {
    $bak = "$dst.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Copy-Files @(@($dst, $bak), @($src, $dst))
    $changed = $true
    Write-Host "기존 것을 $bak 로 백업하고 덮어썼다."
} else {
    # 다른 WSL 설정이 들어 있을 수 있는 사용자 파일이라 말없이 덮어쓰지 않는다.
    # instanceIdleTimeout=-1 이 빠지면 창이 없을 때 Debian 이 꺼져 봇도 죽으니 그냥 넘어가지도 않는다.
    Fail "$dst 가 이미 있고 chiiOS 의 $src 와 다르다. 손으로 합치거나 -Force 로 백업 후 덮어쓴다."
}
if ($changed) {
    if ((Get-FileHash $src).Hash -ne (Get-FileHash $dst -ErrorAction SilentlyContinue).Hash) {
        Fail "$dst 를 썼는데 내용이 $src 와 다르다."
    }
    # .wslconfig 는 WSL VM 을 새로 띄울 때만 읽는다.
    Invoke-Wsl --shutdown
    Write-Host 'WSL 을 내렸다(새 설정 적용).'
}

Step "배포판 $distro"
$installed = @(& wsl.exe -l -q) | ForEach-Object { ($_ -replace "`0", '').Trim() }
if ($installed -contains $distro) {
    Write-Host '이미 있다.'
} else {
    # --no-launch 면 계정 만들기 질문 없이 깔린다. 계정은 setup.sh 가 만든다.
    Invoke-Wsl --install -d $distro --no-launch
}

Step 'setup.sh (Debian 안, root)'
$confBefore = & wsl.exe -d $distro -u root --exec sha256sum /etc/wsl.conf
Invoke-Wsl -d $distro -u root --cd $PSScriptRoot --exec bash ./setup.sh
$confAfter = & wsl.exe -d $distro -u root --exec sha256sum /etc/wsl.conf
if ("$confBefore" -ne "$confAfter") {
    # 기본 사용자·호스트 이름은 배포판을 다시 켜야 먹는다. 처음 깔 때만 해당한다.
    Invoke-Wsl --terminate $distro
    Write-Host "/etc/wsl.conf 가 바뀌어 $distro 를 껐다 켠다."
}

Step '자동 켜기'
& (Join-Path $PSScriptRoot 'autostart.ps1')

Step '바로가기'
& (Join-Path $PSScriptRoot 'shortcut.ps1')

Step '확인'
$state = & wsl.exe -d $distro --exec systemctl is-system-running --wait
$who = "$(& wsl.exe -d $distro --exec whoami)@$(& wsl.exe -d $distro --exec hostname)"
$services = (& wsl.exe -d $distro --exec systemctl is-active docker chii-term chii-home) -join ' '
function Probe($port) {
    for ($i = 0; $i -lt 10; $i++) {
        try { return (Invoke-WebRequest -UseBasicParsing "http://localhost:$port" -TimeoutSec 3).StatusCode }
        catch { Start-Sleep -Seconds 1 }
    }
    return 'down'
}
$http = Probe $ttydPort
$home200 = Probe $homePort
Write-Host "systemd: $state"
Write-Host "사용자: $who"
Write-Host "docker, chii-term, chii-home: $services"
Write-Host "브라우저 터미널 http://localhost:${ttydPort}: $http"
Write-Host "홈 화면 http://localhost:${homePort}: $home200"
if ($state -ne 'running' -or $services -ne 'active active active' -or $http -ne 200 -or $home200 -ne 200) {
    & wsl.exe -d $distro --exec systemctl --failed --no-legend
    Fail '확인 단계에서 걸렸다. 위 출력을 본다.'
}
Write-Host "`n끝. 바탕화면의 chiiOS 를 누르면 홈 화면이 열린다."
