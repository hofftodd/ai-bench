#!/bin/zsh
# Inkling 2 Small, Hygaard's oQe 3.07 bpw MLX build with the MTP head (229 GB), for oMLX 0.8.0.
# Not linked into ~/models/omlx until oMLX is upgraded (0.7.3 can't load inkling2).
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
R=Hygaard/Inkling-2-Small-oQe-3.07bpw-MLX
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download $R"
if uvx --from huggingface_hub hf download $R --local-dir ~/models/inkling-2-small/oQe-3.07bpw-mtp > logs/mac-download-inkling2-oq.log 2>&1; then
  log "download $R done"; else log "download $R FAILED"; fi
