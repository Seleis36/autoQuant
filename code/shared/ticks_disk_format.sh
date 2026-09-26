#!/usr/bin/env bash
# Format the freshly attached tick-store VHDX. Called as root by ticks_disk.ps1.
# The disk is picked by exact byte size and "no filesystem"; anything other than
# exactly one match aborts rather than risk formatting the wrong device.
set -euo pipefail
bytes="$1"; label="$2"
devs=$(lsblk -dnbpo NAME,SIZE,FSTYPE | awk -v b="$bytes" '$2==b && $3=="" {print $1}')
n=$(printf '%s\n' "$devs" | grep -c '^/dev/' || true)
if [ "$n" -ne 1 ]; then
    echo "expected one blank ${bytes}-byte disk, found $n: $devs" >&2
    lsblk -dnbpo NAME,SIZE,FSTYPE >&2
    exit 1
fi
echo "formatting $devs as ext4 label=$label"
mkfs.ext4 -F -m 0 -L "$label" "$devs"
