#!/bin/zsh
# Splash 1.7.0 (DFlash2) on Flint and Flash-Next (Unsloth UD-Q4_K_XL GGUFs). Starts when queue16 and the downloads are done.
# Compare: splash-flint vs flint / omlx-flint (livecodebench 30), splash-qwen3.8-flash-next vs
# omlx-qwen3.8-flash-next-budget-greedy (livecodebench-60 88.3%, terminal-x3 98.1%).
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    tag=mac; [[ $s == *64k ]] && tag=mac-64k
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
    log "$m $s exit $?"
  done
}
smoke_then() {   # model suite...
  local m=$1; shift
  if uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
     && ! grep -q -E "✗|failed to load|exited with" logs/mac-$m-smoke.log; then
    log "$m smoke ok"; run $m "$@"
  else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi
}
log "queue17 waiting for queue16 and the Splash downloads"
until grep -q "queue16 done" logs/mac-queue.log; do sleep 60; done
until grep -q -E "download splash models (done|FAILED)" logs/mac-queue.log; do sleep 60; done
log "queue17 start"
if ! grep -q "download splash models done" logs/mac-queue.log; then log "skipping Splash: download failed"
else
  smoke_then splash-flint speed-quick-eos terminal-x3 livecodebench
  smoke_then splash-qwen3.8-flash-next speed-quick-eos terminal-x3 livecodebench-60
fi
log "queue17 done"
