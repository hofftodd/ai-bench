#!/bin/bash
# R9700 gaps (2026-11-20), after the terminal-hard queue:
# 1. speed for qwen3.8-27b-medium, the quick-edits pick, which had none (~5 min)
# 2. speed-concurrent for the two executor models ai-factory shares (~10 min each)
# 3. the 60-problem LiveCodeBench for the two hard-problem candidates, one problem apart on 30:
#    strata at 32k (never cut off; ~4 h), thinkingcap at 64k (its better budget; ~9 h)
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"   # strata lives here; a detached shell lacks it
log() { echo "$(date "+%F %T") $*" >> logs/r9700-queue.log; }
run() { local m=$1; shift; for s in "$@"; do
  tag=gaps; [[ $s == *64k ]] && tag=gaps-64k
  grep -q "^$(date +%F) .* $m $s exit 0" logs/r9700-queue.log && continue  # rerun-safe
  log "start $m $s"
  ~/.local/bin/uv run aibench run -m $m -s $s --tag $tag > logs/r9700-$m-$s.log 2>&1
  log "$m $s exit $? ($(grep -a -o -E "(pass@1|pass)=[0-9.]+%" logs/r9700-$m-$s.log | tail -1))"
done; }
log "gaps queue waiting for the terminal-hard queue"
until grep -q "terminal-hard queue done" logs/r9700-queue.log; do sleep 60; done
log "gaps queue start"
run qwen3.8-27b-medium speed-quick
run thinkingcap-qwen3.8-27b speed-concurrent
run flint speed-concurrent
run strata livecodebench-60
run thinkingcap-qwen3.8-27b livecodebench-60-64k
run strata terminal-hard   # failed in the terminal-hard queue: strata was not on PATH
log "gaps queue done"
