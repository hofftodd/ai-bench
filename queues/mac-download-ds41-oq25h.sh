#!/bin/zsh
# DeepSeek V4.1 Flash 1017, Jundot's oQ2.5h with the MTP head (342 GB), for oMLX 0.8.0 (oQh needs it).
# Not linked into ~/models/omlx until oMLX is upgraded.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
R=Jundot/DeepSeek-V4.1-Flash-1017-oQ2.5h-mtp
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "start download $R"
if uvx --from huggingface_hub hf download $R --local-dir ~/models/deepseek-v4.1-flash/oQ2.5h-mtp > logs/mac-download-ds41-oq25h.log 2>&1; then
  log "download $R done"; else log "download $R FAILED"; fi
