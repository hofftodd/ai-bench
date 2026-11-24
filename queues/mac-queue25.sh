#!/bin/zsh
# Flint and Ripple follow-ups (2026-11-23), about 3 hours:
# 1. Does flint on Splash (DFlash2, 260 tok/s alone at 8k) keep its lead with several agents? speed-concurrent-eos
#    (1/2/4/8 in flight) on splash-flint-bf16, with omlx-flint (the resident builder, 351 in total at 8) the same day.
# 2. Ripple-65B with its DFlash2 drafter: speed-quick-eos and speed-concurrent-eos, against plain ripple-65b
#    the same day (22 tok/s, ~23 in total with 3 in flight). Downloads the drafter GGUF (4.3 GB) first.
# 3. flint on the 60-problem LiveCodeBench at 64k (omlx-flint, ~1.5-2 h), the sample the other picks are scored on.
# Each run waits until ai-swap is free (three checks a minute apart), so an ai-factory run finishes first.
cd "${0:A:h}/.."
export PATH="$HOME/.local/bin:$PATH"
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
    log "$m $s ($t) exit $rc ($(grep -a -o -E '(pass@1|pass)=[0-9.]+%|tg@8k=[0-9.]+tok/s|total@8=[0-9.]+tok/s' $f | tr '\n' ' '))"
  done
}

log "queue25 start (flint on Splash with several agents, Ripple + DFlash2, flint LCB-60)"
D=~/models/ripple-65b/Ripple-65B-Preview-DFlash2-Q8_0.gguf
if [[ ! -s $D ]]; then
  log "download Ripple DFlash2 drafter"
  if uvx --from huggingface_hub hf download ashbash/Ripple-65B-Preview-DFlash2-GGUF Ripple-65B-Preview-DFlash2-Q8_0.gguf \
       --local-dir ~/models/ripple-65b > logs/mac-download-ripple-dflash2.log 2>&1; then
    log "download Ripple DFlash2 drafter done"; else log "download Ripple DFlash2 drafter FAILED"; fi
fi

run flint-concurrency splash-flint-bf16 speed-concurrent-eos
run flint-concurrency omlx-flint speed-concurrent-eos
run ripple-dflash ripple-65b speed-quick-eos
[[ -s $D ]] && run ripple-dflash ripple-65b-dflash speed-quick-eos speed-concurrent-eos
run flint-lcb60 omlx-flint livecodebench-60-64k
log "queue25 done"
