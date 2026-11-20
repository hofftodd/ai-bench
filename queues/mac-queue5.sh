#!/bin/zsh
# LiveCodeBench at 128k, after mac-queue4.sh (64k), for each model whose 64k run still had cut-off answers.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
while pgrep -f "logs/mac-queue[234].sh" > /dev/null; do sleep 60; done
log "queue5 start (livecodebench-128k)"
cut_off_64k() {   # prints the latest successful 64k cut-off count for model $1 on this box, or nothing
  uv run python -I - "$1" <<'PY'
import glob, json, sys
best = None
for f in sorted(glob.glob("results/*/run.json")):
    run = json.load(open(f))
    if run.get("hardware") != "m5ultra-metal" or run.get("limit"):
        continue
    for r in run.get("results", []):
        if r["model"] == sys.argv[1] and r["suite"] == "livecodebench-64k" and not r.get("error"):
            best = (r.get("metrics") or {}).get("truncated", {}).get("value")
print("" if best is None else int(best))
PY
}
for m in qwen3.8-27b deepseek-v4-flash flint ds4-q2 sushi-glm-5.3-flash sushi-mimo-v2.6-flash ds4-q4; do
  n=$(cut_off_64k $m)
  if [[ -z $n ]]; then log "skip $m 128k: no 64k result"; continue; fi
  if [[ $n -eq 0 ]]; then log "skip $m 128k: nothing cut off at 64k"; continue; fi
  log "start $m 128k ($n cut off at 64k)"
  uv run aibench -c bench-mac.yaml run -m $m -s livecodebench-128k --tag mac-128k > logs/mac-128k-$m.log 2>&1
  log "$m 128k exit $?"
done
log "queue5 done"
