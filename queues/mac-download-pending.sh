#!/bin/zsh
# New models parked in ~/models-pending until there's a free slot to benchmark them.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
dl() {   # repo dest files...
  local repo=$1 dest=$2; shift 2
  log "start download $repo -> $dest"
  if uvx --from huggingface_hub hf download $repo "$@" README.md --local-dir $dest >> logs/mac-download-pending.log 2>&1; then
    log "download $repo done"; else log "download $repo FAILED"; fi
}
P=~/models-pending
dl AtomicChat/Arete-27B-GGUF $P/arete-27b Arete-27B-AD-Q4_K_M.gguf
dl bartowski/AesCode-32B-GGUF $P/aescode-32b AesCode-32B-Q4_K_M.gguf mmproj-AesCode-32B-f16.gguf
dl ggml-org/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-GGUF $P/nemotron-3.5-super-vl \
   NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-Q4_0.gguf mtp-NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-Q4_0.gguf
log "pending downloads done"
