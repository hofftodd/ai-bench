#!/bin/zsh
# splash-flint with bf16 activations on livecodebench (vs 63.3% with the default 8-bit activations), plus speed.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "queue18 start"
m=splash-flint-bf16
for s in livecodebench speed-quick-eos; do
  log "start $m $s"
  uv run aibench -c bench-mac.yaml run -m $m -s $s --tag mac > logs/mac-$m-$s.log 2>&1
  log "$m $s exit $?"
done
log "queue18 done"
