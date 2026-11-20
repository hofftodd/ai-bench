#!/bin/zsh
# Tuned Flash-Next in ai-swap, plus the 6-bit check. Starts when queue14 (ds4-q4) is done.
# 1. Sets greedy + a 24,576-token thinking budget as oMLX model settings for the id ai-swap serves
#    (qwen3.8-flash-next-oq4e), so every agent request gets them. Backup: ~/.omlx/model_settings.json.pre-tuning
# 2. Checks it through ai-swap: smoke test, livecodebench-60 (vs 88.3%), terminal-x3 (vs 98.1%).
# 3. oQ6e with the same settings per request on livecodebench-60.
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
log "queue15 waiting for queue14"
until grep -q "queue14 done" logs/mac-queue.log; do sleep 60; done
log "queue15 start"

S=~/.omlx/model_settings.json
cp -n $S $S.pre-tuning
python3 - $S <<'EOF'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
m = d["models"].setdefault("qwen3.8-flash-next-oq4e", {})
m.update(temperature=0.0, force_sampling=True, thinking_budget_enabled=True, thinking_budget_tokens=24576)
json.dump(d, open(p, "w"), indent=2)
EOF
log "oMLX settings: qwen3.8-flash-next-oq4e greedy (forced) + thinking budget 24576 (backup $S.pre-tuning)"

m=swap-qwen3.8-flash-next
if uv run aibench -c bench-mac.yaml run -m $m -s humaneval-quick -n 2 --no-dashboard > logs/mac-$m-smoke.log 2>&1 \
   && ! grep -q -E "✗|failed to load" logs/mac-$m-smoke.log; then
  log "$m smoke ok"
  run $m livecodebench-60 terminal-x3
else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi

until grep -q -E "download mlx-community/Qwen3.8-Flash-Next-oQ6e-mtp (done|FAILED)" logs/mac-queue.log; do sleep 60; done
if grep -q "download mlx-community/Qwen3.8-Flash-Next-oQ6e-mtp done" logs/mac-queue.log; then
  run omlx-qwen3.8-flash-next-6bit-budget-greedy livecodebench-60
else log "skipping the 6-bit run: download failed"; fi
log "queue15 done"
