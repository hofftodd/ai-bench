#!/bin/zsh
# Splash 1.7.2: Inkling 2 Mini with DFlash2, and flint before ai-swap upgrades (2026-11-24), about 5 h.
# Splash 1.7.2 is unpacked in ~/src/splash-1.7.2 with its own HOME (backend splash-172); Homebrew's 1.7.0 keeps
# serving ai-swap's flint. Splash reports 113-213 tok/s for Inkling 2 Mini on M5 Pro/Max; the R9700 gets 31-35.
# 1. Download Unsloth's current root-layout UD-Q4_K_XL (17.6 GB) and incoai/Inkling-2-Mini-DFlash2.
# 2. flint on 1.7.2: speed-quick-eos and livecodebench (the 30 at 32k; 66.7% on 1.7.0 with bf16).
# 3. Inkling 2 Mini at medium: speed-quick-eos, speed-concurrent-eos, terminal-x3, livecodebench-60-64k.
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

log "queue27 start (Splash 1.7.2: flint recheck, Inkling 2 Mini)"
M=~/models/inkling-2-mini/Inkling-2-Mini-UD-Q4_K_XL.gguf
if [[ ! -s $M ]]; then
  log "download Inkling 2 Mini UD-Q4_K_XL + DFlash2 draft"
  { uvx --from huggingface_hub hf download unsloth/Inkling-2-Mini-GGUF Inkling-2-Mini-UD-Q4_K_XL.gguf --local-dir ~/models/inkling-2-mini &&
    uvx --from huggingface_hub hf download incoai/Inkling-2-Mini-DFlash2; } > logs/mac-download-inkling2-mini.log 2>&1
  if [[ -s $M ]]; then log "download Inkling 2 Mini done ($(du -h $M | cut -f1))"; else log "download Inkling 2 Mini FAILED"; exit 1; fi
fi

run splash172 splash172-flint-bf16 speed-quick-eos livecodebench
run splash172 splash172-inkling-2-mini-medium speed-quick-eos speed-concurrent-eos terminal-x3 livecodebench-60-64k
log "queue27 done"
