# chiiOS: 켜면 chiiOS. Windows 에 로그인하면 chiiOS 홈 화면이 바로 뜨게 한다. 상시 운영 PC(데스크톱)에서 한 번 돌린다.
# 자동 로그인까지 걸면 전원만 켜도 chiiOS 가 뜬다. 정전·업데이트로 재부팅돼도 로그인 없이 봇이 다시 살아난다
# (WSL 은 로그인한 사용자 몫이라, 로그인 전에는 Debian 도 봇도 켜지지 않는다).
#
#   powershell -ExecutionPolicy Bypass -File boot.ps1             로그인하면 chiiOS 열기 (시작프로그램에 바로가기)
#   powershell -ExecutionPolicy Bypass -File boot.ps1 -Autologon  위 + 자동 로그인 도우미 띄우기
#   powershell -ExecutionPolicy Bypass -File boot.ps1 -Remove     시작프로그램에서 빼기 (자동 로그인은 도우미에서 Disable)
param([switch]$Autologon, [switch]$Remove, [string]$StartupDir = [Environment]::GetFolderPath('Startup'))
$ErrorActionPreference = 'Stop'

$link = Join-Path $StartupDir 'chiiOS.lnk'
if ($Remove) {
    if (Test-Path $link) { Remove-Item $link; Write-Host "시작프로그램에서 뺐다: $link" } else { Write-Host '시작프로그램에 없다.' }
    Write-Host '자동 로그인을 걸어 뒀다면 Autologon 을 다시 열어 Disable 을 누른다.'
    return
}

# 바탕화면 바로가기와 같은 길로 연다: Debian 을 깨우고, 앱으로 깔려 있으면 그 앱(제목 줄 없는 창)으로.
$sys32 = "$env:SystemRoot\System32"
$sh = New-Object -ComObject WScript.Shell
$l = $sh.CreateShortcut($link)
$l.TargetPath = "$sys32\conhost.exe"
$l.Arguments = "--headless `"$sys32\cmd.exe`" /c `"$(Join-Path $PSScriptRoot 'start.cmd')`""
$l.WorkingDirectory = $PSScriptRoot
$l.IconLocation = "$(Join-Path $PSScriptRoot 'chiios.ico'),0"
$l.Description = '로그인하면 chiiOS 열기'
$l.Save()
Write-Host "로그인하면 chiiOS 가 뜬다: $link"

if (-not $Autologon) {
    Write-Host '전원만 켜도 뜨게 하려면 -Autologon 을 붙여 다시 돌린다.'
    return
}

# 자동 로그인은 마이크로소프트 Sysinternals 의 Autologon 으로 건다. 비밀번호를 레지스트리에 그대로 두는 대신
# Windows 가 암호화해 보관하는 자리(LSA secret)에 넣는다. 받은 파일은 마이크로소프트 서명을 확인한 뒤에만 연다.
$dir = Join-Path $env:LOCALAPPDATA 'chiiOS\autologon'
$exe = Join-Path $dir 'Autologon64.exe'
if (-not (Test-Path $exe)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $zip = Join-Path $dir 'AutoLogon.zip'
    Invoke-WebRequest -UseBasicParsing 'https://download.sysinternals.com/files/AutoLogon.zip' -OutFile $zip
    Expand-Archive -Force $zip $dir
    Remove-Item $zip
}
$sig = Get-AuthenticodeSignature $exe
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notlike '*Microsoft Corporation*') {
    throw "Autologon 서명이 마이크로소프트 것이 아니다($($sig.Status)). 열지 않는다: $exe"
}
Write-Host ''
Write-Host 'Autologon 창이 뜬다. Username·Domain 은 채워져 있고, Password 에 Windows 로그인 비밀번호를 넣고 Enable.'
Write-Host 'Microsoft 계정이면 그 계정 비밀번호(PIN 아님). 안 되면 설정 > 계정 > 로그인 옵션에서'
Write-Host '"이 디바이스의 Microsoft 계정에 대해 Windows Hello 로그인만 허용" 을 끈다.'
Write-Host '이제 이 PC 앞에 앉은 사람은 누구나 바로 들어간다는 점은 알고 켠다.'
Start-Process $exe
