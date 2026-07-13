#!/usr/bin/env bash
# Read-only Proxmox audit — gathers exactly what's needed to plan GPU
# passthrough and the Nova AI VM, WITHOUT changing anything on the host.
#
# This is deliberately read-only: no VM creation, no config edits, no reboots.
# Run this first; its output decides what (if anything) needs manual BIOS/host
# work before Phase 0 can proceed.
#
# Requires: ops/secrets/infra.env (copy from infra.env.example and fill in).

set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS="$OPS_DIR/secrets/infra.env"

[[ -f "$SECRETS" ]] || {
  echo "missing $SECRETS — copy ops/secrets/infra.env.example and fill it in first" >&2
  exit 1
}
# shellcheck source=/dev/null
source "$SECRETS"

: "${PROXMOX_API_URL:?set in ops/secrets/infra.env}"
: "${PROXMOX_NODE:?set in ops/secrets/infra.env}"
: "${PROXMOX_API_TOKEN_ID:?set in ops/secrets/infra.env}"
: "${PROXMOX_API_TOKEN_SECRET:?set in ops/secrets/infra.env}"

command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }

CURL_OPTS=(-fsS)
[[ "${PROXMOX_API_INSECURE:-true}" == "true" ]] && CURL_OPTS+=(-k)
AUTH_HEADER="Authorization: PVEAPIToken=${PROXMOX_API_TOKEN_ID}=${PROXMOX_API_TOKEN_SECRET}"

papi() { curl "${CURL_OPTS[@]}" -H "$AUTH_HEADER" "$PROXMOX_API_URL$1" | jq '.data // .'; }

echo "═══ Node status ═══"
papi "/nodes/$PROXMOX_NODE/status" \
  | jq '{cpu: .cpuinfo.model, sockets: .cpuinfo.sockets, cores: .cpuinfo.cores, kernel: .kversion, memory_gb: (.memory.total / 1073741824 | floor)}'

echo
echo "═══ Existing VMs/LXCs (don't disturb these) ═══"
{
  papi "/nodes/$PROXMOX_NODE/qemu" | jq -r '.[] | "vm  \(.vmid)\t\(.name)\t\(.status)"'
  papi "/nodes/$PROXMOX_NODE/lxc"  | jq -r '.[] | "lxc \(.vmid)\t\(.name)\t\(.status)"'
} 2>/dev/null

echo
echo "═══ PCI devices — NVIDIA candidates (PVE 8+ API; may be empty on older versions) ═══"
papi "/nodes/$PROXMOX_NODE/hardware/pci" 2>/dev/null \
  | jq -r '.[] | select((.device_name // "" | test("NVIDIA|RTX"; "i")) or (.vendor_name // "" | test("NVIDIA"; "i"))) | "\(.id // .pciid)\t\(.vendor_name // "?")\t\(.device_name // .device // "?")"' \
  || echo "  (hardware/pci endpoint unavailable on this PVE version — rely on the SSH section below)"

if [[ -n "${PROXMOX_SSH_USER:-}" && -n "${PROXMOX_SSH_KEY_PATH:-}" ]]; then
  SSH_KEY="${PROXMOX_SSH_KEY_PATH/#\~/$HOME}"
  SSH_TARGET="${PROXMOX_SSH_USER}@${PROXMOX_HOST}"
  SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -p "${PROXMOX_SSH_PORT:-22}")

  echo
  echo "═══ IOMMU / VFIO / GPU grouping (via SSH — read-only commands only) ═══"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" '
    echo "--- kernel cmdline (need intel_iommu=on or amd_iommu=on) ---"
    cat /proc/cmdline

    echo
    echo "--- IOMMU messages in dmesg ---"
    dmesg 2>/dev/null | grep -i iommu | head -10 || echo "  none found (IOMMU likely disabled, or dmesg ring buffer rotated)"

    echo
    echo "--- vfio kernel modules loaded? ---"
    lsmod | grep -i vfio || echo "  not loaded (expected pre-passthrough-setup)"

    echo
    echo "--- NVIDIA GPU(s) + IOMMU group + group-mates ---"
    for dev in $(lspci -nn | grep -i nvidia | cut -d" " -f1); do
      echo "device 0000:$dev:"
      lspci -nnk -s "$dev" | sed "s/^/  /"
      group="$(readlink "/sys/bus/pci/devices/0000:$dev/iommu_group" 2>/dev/null | xargs -n1 basename 2>/dev/null || true)"
      if [[ -n "$group" ]]; then
        echo "  iommu_group: $group"
        echo "  other devices sharing this group (all must be passed through together):"
        for d in /sys/kernel/iommu_groups/"$group"/devices/*; do
          bd="$(basename "$d")"
          lspci -nns "${bd#0000:}" | sed "s/^/    /"
        done
      else
        echo "  iommu_group: NONE — IOMMU is off, or device path not found"
      fi
    done
  '
else
  echo
  echo "═══ IOMMU / VFIO / GPU grouping ═══"
  echo "  Skipped — set PROXMOX_SSH_USER + PROXMOX_SSH_KEY_PATH in ops/secrets/infra.env to run this."
  echo "  Strongly recommended: the API alone can't confirm IOMMU/kernel-cmdline state on most PVE versions."
fi

echo
echo "═══ What this tells us ═══"
echo "  - 'iommu' in kernel cmdline + dmesg IOMMU messages  -> BIOS VT-d/AMD-Vi is already on, no manual BIOS step needed."
echo "  - No IOMMU messages at all                          -> you'll need to enable VT-d/AMD-Vi in BIOS yourself (I can't do this remotely)."
echo "  - GPU's IOMMU group contains ONLY the GPU + its audio function -> clean passthrough."
echo "  - GPU shares a group with unrelated devices          -> may need 'pcie_acs_override' (a tradeoff, we'll discuss before applying)."
