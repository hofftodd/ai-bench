#!/bin/zsh
# Inkling 2 Small, then DeepSeek V4.1 Flash, on oMLX 0.8.0. Starts when queue22 is done (first try 09:54 failed: no native kernels); DeepSeek runs overnight.
# Each model runs alone: the reservation unloads ai-swap's models, and aibench's oMLX server holds one model.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    tag=mac; [[ $s == *64k ]] && tag=mac-64k
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
    log "$m $s exit $? ($(grep -a -o -E '(pass@1|pass)=[0-9.]+%|tg@512=[0-9.]+tok/s' logs/mac-$m-$s.log | tail -1))"
  done
}
smoke() {   # model -> 0 if it answers a couple of HumanEval problems
  uv run aibench -c bench-mac.yaml run -m $1 -s humaneval-quick -n 2 --no-dashboard > logs/mac-$1-smoke.log 2>&1 \
    && ! grep -q -E "✗|failed to load|exited with|Error" logs/mac-$1-smoke.log
}
setting() {   # oMLX model id, key=value...: written to ~/.omlx/model_settings.json before the model loads
  python3 - "$@" <<'PY'
import json, sys
p = __import__("os").path.expanduser("~/.omlx/model_settings.json")
d = json.load(open(p)); m = d["models"].setdefault(sys.argv[1], {})
for kv in sys.argv[2:]:
    k, v = kv.split("="); m[k] = json.loads(v)
json.dump(d, open(p, "w"), indent=2)
PY
}
log "queue21 waiting for queue22"
until grep -q "queue22 done" logs/mac-queue.log; do sleep 60; done
log "queue21 start"

setting inkling-2-small-oq3 mtp_enabled=false
m=omlx-inkling-2-small
if smoke $m; then log "$m smoke ok"; run $m speed-quick-eos livecodebench-64k terminal-x3
else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi

setting deepseek-v4.1-flash-oq25h deepseek_v41_engram_ssd_offload=true mtp_enabled=false
m=omlx-deepseek-v4.1-flash
if smoke $m; then
  log "$m smoke ok"
  run $m speed-quick-eos livecodebench-60-64k
  run $m-budget livecodebench-60
else log "$m smoke test FAILED (see logs/mac-$m-smoke.log)"; fi
log "queue21 done"
