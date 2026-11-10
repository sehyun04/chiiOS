# chiiOS: 꺼진 Debian 을 다시 켜는 작업을 Windows 작업 스케줄러에 건다.
# WSL 은 Windows 재부팅이나 WSL 자동 업데이트 뒤에 Debian 을 다시 켜 주지 않는다.
# 로그온할 때 한 번, 그 뒤로 5분마다 Debian 에 빈 명령을 보낸다. 꺼져 있으면 켜지고
# 켜져 있으면 아무 일도 없다. .wslconfig 의 instanceIdleTimeout=-1 덕에 켜진 뒤 그대로 남는다.
# 여러 번 돌려도 같은 이름의 작업 하나를 덮어쓴다.
#
#   powershell -ExecutionPolicy Bypass -File autostart.ps1          걸기
#   powershell -ExecutionPolicy Bypass -File autostart.ps1 -Remove  떼기
param([switch]$Remove)
$ErrorActionPreference = 'Stop'

$taskName = 'chiiOS'
$distro = 'Debian'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "작업 '$taskName' 를 뗐다."
    return
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$sys32 = "$env:SystemRoot\System32"

# wsl.exe 는 콘솔 프로그램이라 그냥 부르면 돌 때마다 검은 창이 번쩍인다. conhost --headless 로 감싸 창 없이 띄운다.
$action = New-ScheduledTaskAction -Execute "$sys32\conhost.exe" -Argument "--headless $sys32\wsl.exe -d $distro --exec /bin/true"

$triggers = @(
    New-ScheduledTaskTrigger -AtLogOn -User $user
    # 로그온 트리거에 반복을 달면 다음 로그온부터야 돌기 시작한다. 지금부터 도는 반복은 시각 트리거로 따로 둔다.
    New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
)

# 기본값은 "AC 전원일 때만 시작"이라 노트북이 배터리로 돌면 아예 실행되지 않는다.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

# WSL 배포판은 사용자별이라 로그온한 내 계정으로 돌아야 한다. 관리자 권한은 필요 없다.
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "작업 '$taskName' 를 걸었다: 로그온할 때 + 5분마다 $distro 깨우기"
