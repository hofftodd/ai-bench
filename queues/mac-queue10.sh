#!/bin/zsh
# oMLX vs llama.cpp on qwen3.8-27b and flint, plus the true MTP-off Flash-Next speed runs.
# Waits for the oQ4e downloads. qwen3.8-27b on oMLX gets 128k last (5 h on llama.cpp; stop it if the GPU is needed).
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
until grep -q "downloads oq-dense done" logs/mac-queue.log; do sleep 60; done
grep -q -E "download (Jundot/Qwen3.8-27B-oQ4e-mtp|mlx-community/flint-oQ4e) FAILED" logs/mac-queue.log && { log "queue10 aborted: a download failed"; exit 1; }
log "queue10 start"
smoke() {
  if ! uv run aibench -c bench-mac.yaml run -m $1 -s humaneval-quick -n 2 --no-dashboard > logs/mac-$1-smoke.log 2>&1 \
       || grep -q -E "✗|failed to load|load: " logs/mac-$1-smoke.log; then
    log "$1 smoke test FAILED (see logs/mac-$1-smoke.log)"; return 1; fi
  log "$1 smoke ok"
}
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    tag=mac; [[ $s == livecodebench-64k ]] && tag=mac-64k; [[ $s == livecodebench-128k ]] && tag=mac-128k
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
    log "$m $s exit $?"
  done
}
run omlx-qwen3.8-flash-next speed-quick-eos speed-concurrent-eos
run qwen3.8-27b speed-concurrent-eos
run flint speed-concurrent-eos
smoke omlx-flint && run omlx-flint speed-quick-eos speed-concurrent-eos humaneval-quick livecodebench-64k livecodebench
smoke omlx-qwen3.8-27b && run omlx-qwen3.8-27b speed-quick-eos speed-concurrent-eos humaneval-quick livecodebench-64k livecodebench livecodebench-128k
log "queue10 done"
