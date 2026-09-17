# dp - chestnut (eGPU) support on tici/tizi.
#
# chestnut enumerates on the aux USB-C port (a600000.ssusb - see usb.py's
# PRIMARY_USB_CONTROLLER and chestnut/flash.py's PM_PATHS), which boots in OTG idle
# ("none") on tici. The only thing that ever switches it to host is set_aux_panda in
# 10_tici_hw.sh, and that (a) runs only on F4/DOS and (b) reverts to "none" when no
# second panda shows up - so on TRES a chestnut is never enumerated, usbgpu_present()
# stays false, and the whole eGPU path is dead. mici does not need this: its port is
# not OTG-shared.
#
# Runs at 30_ so set_aux_panda (10_) has had its turn at the port. tici-only on purpose:
# mici's port is not OTG-shared, and tizi has not been looked at.

set_chestnut_hw() {
  grep -q "tici" /sys/firmware/devicetree/base/model 2>/dev/null || return 0

  local mode="/sys/devices/platform/soc/a600000.ssusb/mode"
  [ -e "$mode" ] || return 0

  # set_aux_panda already claimed host mode for an aux panda; leave it alone.
  [ "$(cat "$mode" 2>/dev/null)" = "host" ] && return 0

  echo "Checking for chestnut (switching USB-C port to host mode)..."
  echo host | sudo tee "$mode" >/dev/null 2>&1

  # CHESTNUT_USB_IDS plus the ASM ROM-bootloader ids an unflashed board shows as;
  # hardwared's Chestnut class flashes it offroad once it is visible.
  for _ in $(seq 1 8); do
    sleep 0.5
    if lsusb 2>/dev/null | grep -qiE 'add1:0001|3801:0001|174c:2464|174c:2463'; then
      echo "chestnut detected (USB host mode kept)"
      export CHESTNUT_HW=1
      return 0
    fi
  done

  # Nothing there: hand the port back so it still works as a USB device (PC connect).
  echo "no chestnut found; reverting USB-C port to device mode"
  echo none | sudo tee "$mode" >/dev/null 2>&1
}
DP_LAUNCH_HOOKS="$DP_LAUNCH_HOOKS set_chestnut_hw"
