# chiiOS: 바탕화면과 시작 메뉴에 chiiOS 바로가기를 만든다(하치와레 아이콘).
# 누르면 start.cmd 가 Debian 을 깨우고, 홈 화면을 주소창·탭 없는 Edge 앱 창으로 연다.
# start.cmd 를 그냥 가리키면 Debian 이 뜨는 몇 초 동안 검은 콘솔 창이 보인다. 자동 켜기처럼 conhost --headless 로 감싼다.
# 여러 번 돌려도 같은 바로가기를 덮어쓴다.
#
#   powershell -ExecutionPolicy Bypass -File shortcut.ps1          만들기
#   powershell -ExecutionPolicy Bypass -File shortcut.ps1 -Remove  지우기
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$sys32 = "$env:SystemRoot\System32"
$start = Join-Path $PSScriptRoot 'start.cmd'
$icon = Join-Path $PSScriptRoot 'chiios.ico'
$places = @(
    [Environment]::GetFolderPath('Desktop')
    [Environment]::GetFolderPath('Programs')
)

$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $places) {
    $path = Join-Path $dir 'chiiOS.lnk'
    if ($Remove) {
        if (Test-Path $path) { Remove-Item $path; Write-Host "지웠다: $path" }
        continue
    }
    # 바탕화면 하나가 막혀 있어도(OneDrive 동기화 잠금 등) 설치 전체를 멈추지는 않는다.
    try {
        $lnk = $shell.CreateShortcut($path)
        $lnk.TargetPath = "$sys32\conhost.exe"
        $lnk.Arguments = "--headless `"$sys32\cmd.exe`" /c `"$start`""
        $lnk.WorkingDirectory = $PSScriptRoot
        $lnk.IconLocation = "$icon,0"
        $lnk.Description = 'chiiOS 홈 화면'
        $lnk.Save()
        Write-Host "만들었다: $path"
    } catch {
        Write-Host "못 만들었다: $path ($($_.Exception.Message))" -ForegroundColor Yellow
    }
}
