#!/bin/zsh
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download qwen3.8-flash-next oQ4e-mtp"
if uvx --from huggingface_hub hf download Jundot/Qwen3.8-Flash-Next-oQ4e-mtp --local-dir ~/models/qwen3.8-flash-next/oQ4e-mtp > logs/mac-download-flashnext-oq.log 2>&1; then
  log "download qwen3.8-flash-next oQ4e-mtp done"; else log "download qwen3.8-flash-next oQ4e-mtp FAILED"; fi
