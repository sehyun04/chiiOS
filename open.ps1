# chiiOS 홈 화면 열기(start.cmd 가 Debian 을 깨운 뒤 부른다).
# 앱으로 설치돼 있으면 그 앱으로 연다: Windows 제목 줄 대신 홈 화면이 그린 작은 줄을 쓰는 창이다(창 컨트롤 오버레이).
# 설치 안 됐으면 주소창 없는 Edge 창(--app)으로 열고, 거기 상태줄의 [앱으로 설치] 로 깔 수 있다.
# 설치된 앱의 ID 는 Edge 가 만든 바로가기 안에만 있다(Chromium 식으로 계산한 값과 달랐다). 그래서 바로가기를 읽는다.
$url = 'http://localhost:7682/'
$sh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
# 바탕화면은 맨 위만 본다. 작업 폴더가 바탕화면 아래에 있으면 통째로 뒤지느라 한참 걸린다.
$links = @(Get-ChildItem $desktop -Filter *.lnk -ErrorAction SilentlyContinue) +
         @(Get-ChildItem ([Environment]::GetFolderPath('Programs')) -Recurse -Filter *.lnk -ErrorAction SilentlyContinue)
$app = $null
foreach ($f in $links) {
    $l = $sh.CreateShortcut($f.FullName)
    # 다른 프로필 폴더(--user-data-dir)로 깐 시험용 앱은 건너뛴다.
    if ($l.TargetPath -like '*msedge_proxy.exe' -and $l.Arguments -like "*--app-url=$url*" -and $l.Arguments -notlike '*--user-data-dir=*') {
        if (-not $app) { $app = $l }
        # Edge 는 설치할 때 바탕화면에 'chiiOS (1)' 을 하나 더 만든다(이미 chiiOS 바로가기가 있어서).
        # 같은 앱을 여는 아이콘이 둘이면 헷갈리니, 우리 것(Debian 을 깨우고 연다)을 남기고 그쪽을 지운다.
        if ($f.DirectoryName -eq $desktop -and $f.BaseName -like 'chiiOS (*' -and (Test-Path (Join-Path $desktop 'chiiOS.lnk'))) {
            Remove-Item $f.FullName -ErrorAction SilentlyContinue
        }
    }
}
if ($app) {
    Start-Process $app.TargetPath -ArgumentList $app.Arguments
    return
}
$edge = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction SilentlyContinue).'(default)'
if (-not $edge) {
    $edge = (Get-ItemProperty 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction SilentlyContinue).'(default)'
}
if ($edge) {
    Start-Process $edge -ArgumentList "--app=$url"
} else {
    Start-Process $url
}
