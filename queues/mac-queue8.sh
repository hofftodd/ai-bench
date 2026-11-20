#!/bin/zsh
# Inkling-Small (mlx-community 4-bit) on oMLX: smoke test, then speed (eos), HumanEval, LCB 64k and 32k.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
m=inkling-small
log "queue8 start: $m on omlx"
if ! uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
     || grep -q -E "✗|failed to load|load: " logs/mac-$m-smoke.log; then
  log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; exit 1; fi
log "$m smoke ok"
for s in speed-quick-eos humaneval-quick livecodebench-64k livecodebench; do
  tag=mac; [[ $s == livecodebench-64k ]] && tag=mac-64k
  log "start $m $s"
  uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
  log "$m $s exit $?"
done
log "queue8 done"
