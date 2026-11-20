#!/bin/zsh
# Ripple-65B Preview (AD-Q4_K_M) on llama.cpp b12192. Starts after queue11, the download and the build.
# terminal-quick early: tool calling is its headline claim. LCB 64k before 32k, like the other models.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    tag=mac; [[ $s == livecodebench-64k ]] && tag=mac-64k
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
    log "$m $s exit $?"
  done
}
BIN=~/src/llama.cpp-b12192/build/bin/llama-server
until grep -q "queue11 done" logs/mac-queue.log; do sleep 60; done
until grep -q -E "download Ripple-65B AD-Q4_K_M (done|FAILED)" logs/mac-queue.log; do sleep 30; done
log "queue12 start"
m=ripple-65b
if ! grep -q "download Ripple-65B AD-Q4_K_M done" logs/mac-queue.log; then log "skipping $m: download failed"
elif [[ ! -x $BIN ]]; then log "skipping $m: llama.cpp b12192 not built (see logs/llama-b12192-build.log)"
elif uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
     && ! grep -q -E "✗|failed to load|load: " logs/mac-$m-smoke.log; then
  log "$m smoke ok"
  run $m speed-quick-eos terminal-quick livecodebench-64k terminal-x3 livecodebench
else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi
log "queue12 done"
