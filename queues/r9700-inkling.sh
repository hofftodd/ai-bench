#!/bin/bash
# Inkling 2 Mini on the R9700 (2026-11-21), on Unsloth's ROCm llama.cpp fork with DSpark (see bench.yaml):
# 1. speed-quick (~5 min)
# 2. terminal-x3, the agentic suite (~1 h)
# 3. the 60-problem LiveCodeBench at 64k, the hard-problem budget ThinkingCap ran at (~8-10 h)
# Waits for other runs (the Radiance evaluation) to release ai-swap before each run: free for
# three checks a minute apart, and retried if another run takes the reservation first.
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
source ~/.config/ai-swap/env
log() { echo "$(date "+%F %T") $*" >> logs/r9700-queue.log; }
locked() { curl -s -H "Authorization: Bearer $AI_SWAP_API_KEY" localhost:8080/api/lock | grep -q "\"owner\""; }
wait_free() { local n=0; while (( n < 3 )); do if locked; then n=0; else n=$((n+1)); fi; sleep 60; done; }
run() { local m=$1; shift; for s in "$@"; do
  tag=inkling; [[ $s == *64k ]] && tag=inkling-64k
  grep -q "^$(date +%F) .* $m $s exit 0" logs/r9700-queue.log && continue  # rerun-safe
  while :; do
    wait_free
    log "start $m $s"
    ~/.local/bin/uv run aibench run -m $m -s $s --tag $tag > logs/r9700-$m-$s.log 2>&1
    rc=$?
    grep -q "already reserved by" logs/r9700-$m-$s.log && { log "$m $s: ai-swap taken, waiting"; continue; }
    break
  done
  log "$m $s exit $rc ($(grep -a -o -E "(pass@1|pass)=[0-9.]+%" logs/r9700-$m-$s.log | tail -1))"
done; }
log "inkling queue waiting for ai-swap"
run inkling-2-mini speed-quick terminal-x3 livecodebench-60-64k
log "inkling queue done"
