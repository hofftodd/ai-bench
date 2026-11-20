#!/bin/zsh
# Mac Studio baseline: `mac` profile for qwen3.8-27b and flint, then DeepSeek V4 Flash once its download is done.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }

log "start qwen3.8-27b + flint"
uv run aibench -c bench-mac.yaml run -m qwen3.8-27b -m flint -s mac --tag mac-baseline --no-dashboard > logs/mac-qwen-flint.log 2>&1
log "qwen3.8-27b + flint exit $?"

while pgrep -f "hf download unsloth/DeepSeek-V4-Flash-GGUF" > /dev/null; do sleep 60; done
n=$(ls ~/models/deepseek-v4-flash/UD-Q2_K_XL/*.gguf 2>/dev/null | wc -l | tr -d ' ')
if [[ $n -ne 3 ]]; then log "deepseek download incomplete ($n of 3 parts); skipping"; exit 1; fi

log "start deepseek-v4-flash"
uv run aibench -c bench-mac.yaml run -m deepseek-v4-flash -s mac --tag mac-baseline --no-dashboard > logs/mac-deepseek.log 2>&1
log "deepseek-v4-flash exit $?"
log "queue done"
