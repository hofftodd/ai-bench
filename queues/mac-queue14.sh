#!/bin/zsh
# Is a tuned Qwen3.8-Flash-Next the Mac's best model? Starts when queue13 is done.
# Every aibench run reserves the Mac's ai-swap and unloads ds4-q4 and flint while it runs.
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
log "queue14 waiting for queue13"
until grep -q "queue13 done" logs/mac-queue.log; do sleep 60; done
log "queue14 start"

fn=omlx-qwen3.8-flash-next
run $fn-budget64k-greedy livecodebench-64k      # greedy at 64k, never tried (~1.5 h)
run $fn-budget-greedy terminal-x3               # tool use with budget + greedy (~15 min)
run $fn-budget-greedy livecodebench-60          # 60 problems, its best 32k setting (~1.5 h)
run $fn-budget64k-greedy livecodebench-60-64k   # 60 problems at 64k (~3 h)
run ds4-q4 livecodebench-60-64k                 # ds4-q4's best setting on the same 60 (~8 h)
log "queue14 done"
