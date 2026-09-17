# dp - LITE hardware detection (o3-v2)

set_lite_hw() {
  if grep -q "tici" /sys/firmware/devicetree/base/model 2>/dev/null; then
    output=$(i2cget -y 0 0x10 0x00 2>/dev/null)

    if [ -z "$output" ]; then
      echo "Lite HW"
      export LITE=1
    fi
  fi
}
DP_LAUNCH_HOOKS="$DP_LAUNCH_HOOKS set_lite_hw"
