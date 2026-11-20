#!/bin/zsh
# Laguna S 2.1 (NVFP4 MLX) on oMLX. Starts when queue15 and the download are done.
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
log "queue16 waiting for queue15 and the Laguna S download"
until grep -q "queue15 done" logs/mac-queue.log; do sleep 60; done
until grep -q -E "download poolside/Laguna-S-2.1-NVFP4-mlx (done|FAILED)" logs/mac-queue.log; do sleep 60; done
log "queue16 start"
m=omlx-laguna-s-2.1
if ! grep -q "download poolside/Laguna-S-2.1-NVFP4-mlx done" logs/mac-queue.log; then log "skipping $m: download failed"
elif uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
     && ! grep -q -E "✗|failed to load" logs/mac-$m-smoke.log; then
  log "$m smoke ok"
  run $m speed-quick-eos terminal-quick terminal-x3 livecodebench-64k
else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi
log "queue16 done"
