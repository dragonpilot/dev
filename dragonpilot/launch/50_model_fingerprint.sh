# dp - force car model via FINGERPRINT env (model-selector)

# dp - model selector: if a car model has been selected, force it and skip the FW query
# (uses stock openpilot FINGERPRINT/SKIP_FW_QUERY env vars - no opendbc/card patch needed).
# AGNOS-only, so the params path is always /data/params/d.
set_model_fingerprint() {
  local model
  model=$(cat /data/params/d/dp_dev_model_selected 2>/dev/null)
  if [ -n "$model" ] && [ "$model" != "0" ]; then
    export FINGERPRINT="$model"
    export SKIP_FW_QUERY=1
  fi
}
DP_LAUNCH_HOOKS="$DP_LAUNCH_HOOKS set_model_fingerprint"
