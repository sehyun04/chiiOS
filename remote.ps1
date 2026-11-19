# chiiOS: 다른 기기(노트북·폰)에서 이 PC 의 chiiOS 를 열게 한다. 상시 운영 PC(데스크톱)에서 한 번 돌린다.
# Tailscale 은 내 기기끼리만 이어지는 사설망이다. 인터넷에 포트를 열지 않고, 이 PC 의 Tailscale 이 받은 요청만
# 127.0.0.1:7682 로 넘긴다(Tailscale Serve). 주소는 https://<이 PC 이름>.<내 망>.ts.net/ 하나다.
# 홈 화면은 이 PC 주인 Tailscale 계정으로 온 요청만 받는다(home/server.py host_ok).
#
#   powershell -ExecutionPolicy Bypass -File remote.ps1          켜기 (재부팅해도 이어진다)
#   powershell -ExecutionPolicy Bypass -File remote.ps1 -Remove  끄기
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
if (-not (Test-Path $ts)) {
    Write-Host 'Tailscale 이 없다. https://tailscale.com/download 에서 Windows 판을 깔고 로그인한 뒤 다시 돌린다.'
    Write-Host '노트북·폰에도 같은 계정으로 깔고 로그인해 둔다.'
    return
}

if ($Remove) {
    & $ts serve --https=443 off
    Write-Host '다른 기기에서 chiiOS 를 여는 길을 닫았다.'
    return
}

$st = & $ts status --json | ConvertFrom-Json
if ($st.BackendState -ne 'Running') {
    Write-Host "Tailscale 이 아직 안 붙었다($($st.BackendState)). 작업 표시줄의 Tailscale 아이콘에서 로그인한 뒤 다시 돌린다."
    return
}

# Serve 는 망에 HTTPS 인증서가 켜져 있어야 한다. 꺼져 있으면 serve 가 허락 주소를 띄우고 기다리는데, 그 창을 닫으면
# 아무것도 안 걸린 채 끝난다(11-19 데스크톱에서 주소만 찍히고 안 열렸다). 그래서 미리 알리고, 끝난 뒤 실제로 걸렸는지 본다.
$name = "$($st.Self.DNSName)".TrimEnd('.')
if (-not $st.CertDomains) {
    Write-Host '이 망은 HTTPS 인증서가 아직 꺼져 있다. 곧 뜨는 허락 주소에서 켜거나,'
    Write-Host 'https://login.tailscale.com/admin/dns 맨 아래 HTTPS Certificates 의 Enable HTTPS 를 누른다.'
    Write-Host '(켜면 이 PC 이름이 공개 인증서 기록에 남는다. 이름만 남고 접속은 여전히 내 기기만 된다.)'
}
# --bg 로 걸어 두면 재부팅·재로그인 뒤에도 Tailscale 이 알아서 다시 연다.
& $ts serve --bg 7682
$on = $null
try { $on = (& $ts serve status --json | ConvertFrom-Json).TCP.'443' } catch {}
Write-Host ''
if (-not $on) {
    Write-Host '아직 안 걸렸다. HTTPS 인증서를 켠 뒤 이 스크립트를 다시 돌린다.'
    return
}
Write-Host "다른 기기에서 열 주소: https://$name/"
Write-Host '노트북 Edge 로 열고 상태줄 [앱으로 설치] 를 누르면 이 PC 이름이 붙은 chiiOS 앱이 따로 생긴다.'
