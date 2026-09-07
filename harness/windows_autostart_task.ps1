# autoQuant - OPTIONAL true at-boot autostart (runs before anyone logs in).
#
#   Run in an ELEVATED PowerShell:
#     powershell -ExecutionPolicy Bypass -File \\wsl$\Ubuntu\home\seleis\autoQuant\harness\windows_autostart_task.ps1
#
# install_autostart.sh already installs a Startup-folder hook that works at LOGON
# without admin, which is enough for a machine you log into. This script is only
# needed if you want the harness running while the machine sits at the lock screen.
#
# Remove with:  Unregister-ScheduledTask -TaskName "autoQuant WSL" -Confirm:$false

param(
  [string]$Distro   = "Ubuntu",
  [string]$LinuxUser = "seleis"
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
      ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error "This script must be run from an elevated PowerShell (Run as administrator)."
  exit 1
}

$cmd = "wsl.exe"
$args = "-d $Distro -u $LinuxUser --exec /bin/bash -lc `"systemctl --user start autoquant.target`""

$action    = New-ScheduledTaskAction -Execute $cmd -Argument $args
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
               -DontStopIfGoingOnBatteries -StartWhenAvailable `
               -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
               -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "autoQuant WSL" -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings -Force `
  -Description "Boot the WSL distro at Windows startup so autoQuant's systemd units come up."

Write-Host "Registered scheduled task 'autoQuant WSL' (at startup, as SYSTEM)."
Write-Host "NOTE: a WSL instance started by SYSTEM does not share the interactive user's"
Write-Host "      session. If the units do not come up, prefer the Startup-folder hook"
Write-Host "      that install_autostart.sh writes, which runs as you at logon."
