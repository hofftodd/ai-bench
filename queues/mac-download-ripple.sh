#!/bin/zsh
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download AtomicChat/Ripple-65B-Preview-GGUF AD-Q4_K_M"
if uvx --from huggingface_hub hf download AtomicChat/Ripple-65B-Preview-GGUF Ripple-65B-Preview-AD-Q4_K_M.gguf README.md LICENSE \
     --local-dir ~/models/ripple-65b > logs/mac-download-ripple.log 2>&1; then
  log "download Ripple-65B AD-Q4_K_M done"; else log "download Ripple-65B AD-Q4_K_M FAILED"; fi
