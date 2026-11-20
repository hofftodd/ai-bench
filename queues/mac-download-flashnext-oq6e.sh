#!/bin/zsh
# Qwen3.8-Flash-Next oQ6e with the MTP head (mlx-community, 150 GB): does 6-bit beat oQ4e with budget + greedy?
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
R=mlx-community/Qwen3.8-Flash-Next-oQ6e-mtp
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download $R"
if uvx --from huggingface_hub hf download $R --local-dir ~/models/qwen3.8-flash-next/oQ6e-mtp > logs/mac-download-flashnext-oq6e.log 2>&1; then
  ln -sfn ../qwen3.8-flash-next/oQ6e-mtp ~/models/omlx/qwen3.8-flash-next-oq6e-mtp
  log "download $R done"; else log "download $R FAILED"; fi
