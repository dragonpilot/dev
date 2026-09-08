# dp launch hooks

One file per feature: `NN_<name>.sh`. Sourced by `launch_chffrplus.sh` at startup, then
each entry in `DP_LAUNCH_HOOKS` is called in filename order.

```sh
# dragonpilot/launch/50_model_fingerprint.sh
set_model_fingerprint() {
  local model
  model=$(cat /data/params/d/dp_dev_model_selected 2>/dev/null)
  if [ -n "$model" ] && [ "$model" != "0" ]; then
    export FINGERPRINT="$model"
    export SKIP_FW_QUERY=1
  fi
}
DP_LAUNCH_HOOKS="$DP_LAUNCH_HOOKS set_model_fingerprint"
```

## Ordering

The `NN_` prefix is the run order and it is load-bearing:

- **00-49** hardware detection. `set_tici_hw` exports `TICI_DOS`/`TICI_TRES`.
- **50-99** anything that depends on hardware detection having run.

Pick a number with a gap either side so a later feature can slot between.

## Why one file per feature

Every feature used to append a function body *and* a call, at two shared anchors in
`launch_chffrplus.sh`. That produced a conflict per feature pair, and because shell
functions have no import boundary, git could put a shared `fi }` tail below the conflict
marker - so "keep both sides" left one function unterminated, silently swallowing the next
definition. Valid shell, wrong behaviour, no error.

Hooks run inside the `if [ -f /AGNOS ]` block, before `agnos_init`.

A hook named in `DP_LAUNCH_HOOKS` but not defined is skipped with a message rather than
aborting boot.
