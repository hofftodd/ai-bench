#!/bin/zsh
# Inkling-Small MLX 4-bit (153 GB) for the oMLX warm-up run.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download inkling-small mlx-4bit"
if uvx --from huggingface_hub hf download mlx-community/Inkling-Small-mlx-4bit \
     --local-dir ~/models/inkling-small/mlx-4bit > logs/mac-download-inkling.log 2>&1; then
  log "download inkling-small mlx-4bit done"
else
  log "download inkling-small mlx-4bit FAILED"
fi
