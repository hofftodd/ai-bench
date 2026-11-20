#!/bin/zsh
# LiveCodeBench at 64k for every Mac model that had cut-off answers at 32k, after mac-queue3.sh.
# Models with an R9700 64k score first. Each run rebuilds RESULTS-mac.md / RESULTS-compare.md.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
while pgrep -f "logs/mac-queue[23].sh" > /dev/null; do sleep 60; done
log "queue4 start (livecodebench-64k)"
for m in qwen3.8-27b deepseek-v4-flash flint ds4-q2 sushi-glm-5.3-flash sushi-mimo-v2.6-flash ds4-q4; do
  log "start $m 64k"
  uv run aibench -c bench-mac.yaml run -m $m -s livecodebench-64k --tag mac-64k > logs/mac-64k-$m.log 2>&1
  log "$m 64k exit $?"
done
log "queue4 done"
