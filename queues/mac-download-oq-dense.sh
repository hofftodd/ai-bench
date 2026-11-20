#!/bin/zsh
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
dl() {  # repo dir
  log "start download $1"
  if uvx --from huggingface_hub hf download $1 --local-dir $2 > logs/mac-download-${1:t}.log 2>&1; then log "download $1 done"; else log "download $1 FAILED"; fi
}
dl Jundot/Qwen3.8-27B-oQ4e-mtp ~/models/qwen3.8-27b/oQ4e-mtp
dl mlx-community/flint-oQ4e ~/models/flint/oQ4e
log "downloads oq-dense done"
