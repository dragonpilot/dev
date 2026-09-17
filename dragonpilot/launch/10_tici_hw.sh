# dp - TICI hardware detection (c3-0.11.1).
#
# Runs first (10_) because it exports TICI_HW / TICI_DOS / TICI_TRES that later
# hooks and process_config depend on. set_aux_panda and mount_nvme are helpers
# called from set_tici_hw, not registered hooks.

# Determine the panda MCU type (F4=DOS, H7=TRES) and set the TICI_* env vars.
# The MCU type is a permanent hardware fact, so it is detected once and cached in
# /persist (survives fork switch / reset / reflash); every later boot reads the
# cache and skips the panda query entirely.
set_tici_hw() {
  grep -q "tici" /sys/firmware/devicetree/base/model 2>/dev/null || return 0
  export TICI_HW=1

  local cache="/persist/dp_dev_panda_mcu_type"
  local attempts=15 confirm=3         # give up after N reads; trust after M in a row
  local mcu="" count=0 last="" cur cached

  # --- fast path: trust a valid (F4/H7) cached value, no panda query or sleep ---
  cached=$(cat "$cache" 2>/dev/null)
  case "$cached" in
    F4|H7) mcu="$cached"; echo "panda MCU $mcu [cached]" ;;
  esac

  # --- slow path: detect, requiring M consecutive identical reads to reject a
  #     transient misread while the panda enumerates, then persist for next boot ---
  if [ -z "$mcu" ]; then
    echo "Querying panda MCU type..."
    for attempt in $(seq 1 "$attempts"); do
      # wait long while the panda is still coming up, short between confirmations
      if [ -n "$last" ]; then sleep 1; else sleep 3; fi

      # Only the internal panda exists here: the aux USB-C port isn't switched to
      # host mode until after this runs (see set_aux_panda), so a plain connect is
      # unambiguous - there is exactly one panda to read.
      case "$(python -c "from panda_tici import Panda; p = Panda(cli=False); print(p.get_mcu_type()); p.close()" 2>/dev/null)" in
        *McuType.F4*) cur="F4" ;;
        *McuType.H7*) cur="H7" ;;
        *)            cur="" ;;
      esac

      if [ -n "$cur" ] && [ "$cur" = "$last" ]; then
        count=$((count + 1))
      else
        count=1
        last="$cur"
      fi

      if [ -n "$cur" ] && [ "$count" -ge "$confirm" ]; then
        mcu="$cur"
        break
      fi
      echo "panda MCU read='${cur:-UNKNOWN}' (confirmed $count/$confirm, attempt $attempt/$attempts)"
    done

    if [ -z "$mcu" ]; then
      echo "TICI (UNKNOWN) detected after $attempts attempts, stop processing."
      exit 1
    fi

    # Persist it so future boots skip detection. /persist is comma's protected,
    # read-only partition, so flip it rw just for this one write (happens once per
    # device) and back to ro. The fast-path cat above reads fine on a ro mount, so
    # only the write needs this. Any failure here is non-fatal: re-detect next boot.
    if sudo mount -o remount,rw /persist 2>/dev/null; then
      echo "$mcu" | sudo tee "$cache" >/dev/null 2>&1
      sudo mount -o remount,ro /persist 2>/dev/null
    fi
  fi

  # --- apply: DOS (F4) also mounts the NVMe; TRES (H7) does not ---
  if [ "$mcu" = "F4" ]; then
    echo "TICI (DOS) detected"
    mount_nvme
    export TICI_DOS=1
    set_aux_panda              # DOS uses pandad_tici, which supports a 2nd (aux) USB panda
  else
    echo "TICI (TRES) detected"
    export TICI_TRES=1
  fi
}
# The aux USB-C port (a600000.ssusb) boots in OTG idle ("none"); a 2nd panda
# plugged there only enumerates once the port is switched to USB host mode. Only
# DOS (pandad_tici) supports a 2nd USB panda, so this runs for F4 only, and only
# after set_tici_hw has fingerprinted the internal panda alone. Keep host mode
# only if a 2nd panda actually shows up; otherwise revert to "none" so the port
# stays usable as a USB device (PC connect) on units with no aux panda. Aux
# presence is dynamic (plug/unplug), so it is probed every boot, not cached.
set_aux_panda() {
  local mode="/sys/devices/platform/soc/a600000.ssusb/mode"
  [ -e "$mode" ] || return 0

  echo "Checking for aux panda (switching USB-C port to host mode)..."
  echo host | sudo tee "$mode" >/dev/null 2>&1
  for _ in $(seq 1 6); do          # ~3s budget; aux enumerated in ~1-2s in testing
    sleep 0.5
    if [ "$(lsusb 2>/dev/null | grep -c 'comma.ai panda')" -ge 2 ]; then
      echo "aux panda detected (USB host mode kept)"
      return 0
    fi
  done

  echo "no aux panda found; reverting USB-C port to device mode"
  echo none | sudo tee "$mode" >/dev/null 2>&1
}
mount_nvme() {
  for i in $(seq 1 10); do
    [ -b /dev/nvme0n1p1 ] && break
    sleep 1
  done

  # Returns 0 (success) so the boot process continues without errors
  if [ ! -b /dev/nvme0n1p1 ]; then
    return 0
  fi

  # We assume /data/media/0/realdata exists per defaults
  if ! mountpoint -q /data/media/0/realdata; then
    mount /dev/nvme0n1p1 /data/media/0/realdata
  fi

  if mountpoint -q /data/media/0/realdata; then
    OWNER="$(stat -c '%U' /data/media/0/realdata)"
    GROUP="$(stat -c '%G' /data/media/0/realdata)"
    PERM="$(stat -c '%a' /data/media/0/realdata)"

    if [ "$OWNER" != "comma" ] || [ "$GROUP" != "comma" ]; then
      chown comma:comma /data/media/0/realdata
    fi

    if [ "$PERM" != "755" ]; then
      chmod 755 /data/media/0/realdata
    fi
  fi
}
DP_LAUNCH_HOOKS="$DP_LAUNCH_HOOKS set_tici_hw"
