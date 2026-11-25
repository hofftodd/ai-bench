#!/bin/zsh
# Inkling 2 Mini on Splash 1.7.2 against qwen3.8-27b and flint (2026-11-25), about 4-5 h.
# 1. livecodebench-64k (the 30): fills the LCB chart and scatter, and compares with the R9700's 22/30 and
#    qwen3.8-27b's 20-21/30 on the Mac.
# 2. terminal-x3 through ai-swap (swap-inkling-2-mini): checks the production entry, as swap-flint did for flint.
# 3. terminal-hard: terminal-x3 is saturated; flint scored 100% here on the R9700.
# 4. livecodebench-128k: qwen3.8-27b scored 83-87% at 128k on the Mac. Does Inkling gain as much?
# Each run waits until ai-swap is free (three checks a minute apart).
cd "${0:A:h}/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
source ~/.config/ai-swap/env
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
locked() { curl -s -H "Authorization: Bearer $AI_SWAP_API_KEY" localhost:8080/api/lock | grep -q '"owner"'; }
wait_free() { local n=0; while (( n < 3 )); do if locked; then n=0; else n=$((n+1)); fi; sleep 60; done; }
run() {   # tag model suite...
  local t=$1 m=$2; shift 2
  for s in "$@"; do
    local f=logs/mac-$m-$s-$t.log
    while :; do
      wait_free
      log "start $m $s ($t)"
      uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $t > $f 2>&1
      rc=$?
      grep -q "already reserved by" $f && { log "$m $s: ai-swap taken, waiting"; continue; }
      break
    done
    log "$m $s ($t) exit $rc ($(grep -a -o -E '(pass@1|pass)=[0-9.]+%|tg@8k=[0-9.]+tok/s|agg@1k c8 tok/s *│ *[0-9.]+' $f | tr -s ' ' | tr '\n' ' '))"
  done
}


log "queue28 start (Inkling 2 Mini: LCB-30 64k, ai-swap terminal-x3, terminal-hard, LCB-30 128k)"
run splash172 splash172-inkling-2-mini-medium livecodebench-64k
run swap swap-inkling-2-mini terminal-x3
run splash172 splash172-inkling-2-mini-medium terminal-hard livecodebench-128k
log "queue28 done"
