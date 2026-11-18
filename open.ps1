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
    # 설치한 앱은 '켜면 chiiOS' 의 화면이라 최대화로 연다. 작업 표시줄이 자동 숨기기면 그 자리까지 덮는다.
    # --start-maximized 는 못 쓴다: Edge 가 이미 떠 있으면(시작 부스트) 먼저 뜬 Edge 의 명령줄만 본다. 그래서 창을 찾아 키운다.
    Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class ChiiWin {
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  public static IntPtr Find(string title, string cls, string exe) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      var t = new StringBuilder(256); GetWindowText(h, t, 256);
      var c = new StringBuilder(256); GetClassName(h, c, 256);
      if (t.ToString() != title || c.ToString() != cls) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      try { if (!System.Diagnostics.Process.GetProcessById((int)pid).ProcessName.Equals(exe, StringComparison.OrdinalIgnoreCase)) return true; }
      catch { return true; }
      found = h; return false;
    }, IntPtr.Zero);
    return found;
  }
}
"@
    # 켜자마자 부르면 Edge 가 처음 뜨는 데 몇 초 걸린다.
    for ($i = 0; $i -lt 60; $i++) {
        $h = [ChiiWin]::Find('chiiOS', 'Chrome_WidgetWin_1', 'msedge')
        if ($h -ne [IntPtr]::Zero) { [ChiiWin]::ShowWindow($h, 3) | Out-Null; break }
        Start-Sleep -Milliseconds 250
    }
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
