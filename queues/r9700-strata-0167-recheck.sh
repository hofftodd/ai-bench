#!/bin/bash
# Flash-Next (strata, IQ3_S) recheck on engine 0.1.67 (Strata 0.2.21): LiveCodeBench 30 at 32k,
# against 83.3% on engine 0.1.48 (Nov 20). Speed was already rechecked: 77.2 tok/s at 8k vs 67.8.
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
source ~/.config/ai-swap/env
H="Authorization: Bearer $AI_SWAP_API_KEY"
log() { echo "$(date "+%F %T") $*" >> logs/r9700-queue.log; }
locked() { curl -s -H "$H" localhost:8080/api/lock | grep -q "\"owner\""; }
wait_free() { local n=0; while (( n < 3 )); do if locked; then n=0; else n=$((n+1)); fi; sleep 60; done; }
m=strata s=livecodebench tag=strata-0167
while :; do
  wait_free; log "start $m $s ($tag)"
  uv run aibench run -m $m -s $s --tag $tag > logs/r9700-$m-$s-$tag.log 2>&1; rc=$?
  grep -q "already reserved by" logs/r9700-$m-$s-$tag.log && { log "$m $s: ai-swap taken, waiting"; continue; }
  break
done
log "$m $s ($tag) exit $rc ($(grep -a -o -E "pass@1=[0-9.]+%" logs/r9700-$m-$s-$tag.log | tail -1))"
