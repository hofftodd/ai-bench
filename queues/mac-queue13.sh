#!/bin/zsh
# Strata's behaviour on the Mac (TODO steps 1-3). Waits until 22:00, then runs one stage at a time.
# Every aibench run reserves the Mac's ai-swap and unloads ds4-q4 and flint while it runs.
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
log "queue13 waiting for 22:00"
until [[ $(date +%H) -ge 22 || $(date +%H) -lt 6 ]]; do sleep 30; done
log "queue13 start"

# 1. thinking budget on the base model at 32k, sampled and greedy
run omlx-qwen3.8-flash-next-budget livecodebench
run omlx-qwen3.8-flash-next-budget-greedy livecodebench
# 2. budget at 64k
run omlx-qwen3.8-flash-next-budget64k livecodebench-64k

# 3. ThinkingCap-Qwen3.8-Flash-Next (llama.cpp b12098), smoke test first; kernels last (it unloads the model)
m=thinkingcap-qwen3.8-flash-next
if uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
   && ! grep -q -E "✗|failed to load|load: " logs/mac-$m-smoke.log; then
  log "$m smoke ok"
  run $m speed-quick humaneval-quick livecodebench livecodebench-64k terminal-x3
  run $m-budget livecodebench
  run $m-budget64k livecodebench-64k
  run $m kernels
else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi
log "queue13 done"
