# autoQuant tick store: an ext4 virtual disk on D:, attached to WSL.
#
#   D:\WSL\autoquant-ticks.vhdx   dynamic VHDX, 800 GB ceiling, grows with use
#   ext4 label  aq-ticks
#   WSL mount   /mnt/wsl/autoquant-ticks   (data/ticks symlinks here)
#
# Why a VHDX and not /mnt/d: /mnt/d is a 9p share and reads parquet several times slower
# than ext4. Why not the distro's own disk: that VHDX lives on C:, which has ~300 GB free
# and never shrinks back.
#
# Needs an elevated PowerShell (wsl --mount is admin-only). Run once, from WSL:
#   powershell.exe -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \\wsl.localhost\Ubuntu\home\seleis\autoQuant\code\shared\ticks_disk.ps1'"
# That creates + formats the disk, mounts it, links data/ticks to it, and registers the logon task
# "autoQuant ticks disk", which re-runs this script with -MountOnly at every logon.
# After a `wsl --shutdown` the disk is detached; remount without a UAC prompt with:
#   schtasks.exe /run /tn "autoQuant ticks disk"
param([switch]$MountOnly)

$ErrorActionPreference = 'Stop'
$Dir    = 'D:\WSL'
$Vhd    = "$Dir\autoquant-ticks.vhdx"
$Name   = 'autoquant-ticks'
$Label  = 'aq-ticks'
$Distro = 'Ubuntu'
$MaxMB  = 819200
$Log    = "$Dir\autoquant-ticks.log"
$Task   = 'autoQuant ticks disk'
$User   = 'seleis'
$Repo   = "/home/$User/autoQuant"
$FormatSh = "$Repo/code/shared/ticks_disk_format.sh"

New-Item -ItemType Directory -Force $Dir | Out-Null
Start-Transcript -Path $Log -Append | Out-Null
try {
    if (-not $MountOnly) {
        if (-not (Test-Path $Vhd)) {
            Write-Host "creating $Vhd ($MaxMB MB, expandable)"
            $dp = "$env:TEMP\aq_ticks_diskpart.txt"
            "create vdisk file=`"$Vhd`" maximum=$MaxMB type=expandable" |
                Set-Content $dp -Encoding ascii
            diskpart /s $dp
            if (-not (Test-Path $Vhd)) { throw "diskpart did not create $Vhd" }

            # Attach raw, format from inside WSL, detach.
            wsl.exe --mount --vhd $Vhd --bare
            $bytes = [int64]$MaxMB * 1MB
            wsl.exe -d $Distro -u root -- bash $FormatSh $bytes $Label
            if ($LASTEXITCODE -ne 0) { wsl.exe --unmount $Vhd; throw "format failed" }
            wsl.exe --unmount $Vhd
        }

        # Keep a copy on D: for the logon task, which may fire before the distro is up.
        Copy-Item -Force $PSCommandPath "$Dir\mount-autoquant-ticks.ps1"
        $act  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
                "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass " +
                "-File `"$Dir\mount-autoquant-ticks.ps1`" -MountOnly")
        $trig = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $prin = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
        Register-ScheduledTask -TaskName $Task -Action $act -Trigger $trig -Principal $prin -Force | Out-Null
        Write-Host "registered task '$Task'"
    }

    $mounted = wsl.exe -d $Distro -u root -- bash -c "mountpoint -q /mnt/wsl/$Name && echo yes"
    if ($mounted -ne 'yes') {
        wsl.exe --mount --vhd $Vhd --name $Name
        if ($LASTEXITCODE -ne 0) { throw "wsl --mount failed ($LASTEXITCODE)" }
    }
    wsl.exe -d $Distro -u root -- chown 1000:1000 /mnt/wsl/$Name
    # data/ticks -> the mount. Never replaces a real directory: that would hide its data.
    $mnt = "/mnt/wsl/$Name"
    wsl.exe -d $Distro -u $User --cd $Repo -e bash -c (
        "{ [ -e data/ticks ] || [ -L data/ticks ] || ln -s $mnt data/ticks; } && " +
        'test $(realpath data/ticks) = ' + $mnt)
    if ($LASTEXITCODE -ne 0) { throw "data/ticks exists and is not a link to the tick disk" }
    wsl.exe -d $Distro -u root -- df -h /mnt/wsl/$Name
    Write-Host "OK $(Get-Date -Format s)"
}
catch { Write-Host "FAILED: $_"; exit 1 }
finally { Stop-Transcript | Out-Null }
