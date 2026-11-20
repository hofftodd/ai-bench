#!/bin/zsh
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download Jundot/Qwen3.8-27B-oQ6e-mtp"
if uvx --from huggingface_hub hf download Jundot/Qwen3.8-27B-oQ6e-mtp --local-dir ~/models/qwen3.8-27b/oQ6e-mtp > logs/mac-download-oq6e.log 2>&1; then
  log "download Jundot/Qwen3.8-27B-oQ6e-mtp done"; else log "download Jundot/Qwen3.8-27B-oQ6e-mtp FAILED"; fi
