#!/bin/zsh
# 1. terminal-quick on flint (oMLX): checks the Docker sandbox on OrbStack and oMLX's tool calls.
# 2. qwen3.8-27b at 6 bits on oMLX (oQ6e): is oMLX's ~3-point LCB deficit the 4-bit quant? 64k and 32k.
# 3. terminal-x3 for the Foreman picks: flint on oMLX, ds4-q4 on DwarfStar.
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
log "queue11 start"
run omlx-flint terminal-quick
until grep -q -E "download Jundot/Qwen3.8-27B-oQ6e-mtp (done|FAILED)" logs/mac-queue.log; do sleep 30; done
m=omlx-qwen3.8-27b-6bit
if grep -q "download Jundot/Qwen3.8-27B-oQ6e-mtp done" logs/mac-queue.log; then
  if uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
     && ! grep -q -E "✗|failed to load|load: " logs/mac-$m-smoke.log; then
    log "$m smoke ok"; run $m speed-quick-eos livecodebench-64k livecodebench
  else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi
else log "skipping $m: download failed"; fi
run omlx-flint terminal-x3
run ds4-q4 terminal-x3
log "queue11 done"
