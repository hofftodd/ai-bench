#!/bin/zsh
# Laguna S 2.1 (poolside, 118B-A8B), poolside's NVFP4 MLX build (72 GB), for oMLX.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
R=poolside/Laguna-S-2.1-NVFP4-mlx
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download $R"
if uvx --from huggingface_hub hf download $R --local-dir ~/models/laguna-s-2.1/nvfp4-mlx > logs/mac-download-laguna-s.log 2>&1; then
  ln -sfn ../laguna-s-2.1/nvfp4-mlx ~/models/omlx/laguna-s-2.1-nvfp4
  log "download $R done"; else log "download $R FAILED"; fi
