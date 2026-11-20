#!/bin/zsh
# Speed for tuned Flash-Next (budget + greedy on oMLX), so the dashboard can plot the pick. After queue18.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "queue19 waiting for queue18"
until grep -q "queue18 done" logs/mac-queue.log; do sleep 30; done
log "queue19 start"
m=omlx-qwen3.8-flash-next-budget-greedy
log "start $m speed-quick-eos"
uv run aibench -c bench-mac.yaml run -m $m -s speed-quick-eos --tag mac > logs/mac-$m-speed-quick-eos.log 2>&1
log "$m speed-quick-eos exit $?"
log "queue19 done"
