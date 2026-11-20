#!/bin/zsh
# speed-quick-eos for the sushi + ds4 models (speed-quick failed on them: ignore_eos), after mac-queue2.sh.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
while pgrep -f "logs/mac-queue2.sh" > /dev/null; do sleep 60; done
log "queue3 start (speed-quick-eos)"
uv run aibench -c bench-mac.yaml run -m ds4-q2 -m ds4-q4 -m sushi-glm-5.3-flash -m sushi-mimo-v2.6-flash \
  -m sushi-qwen3.8-flash-next-4bpw -s speed-quick-eos --tag mac-baseline --no-dashboard > logs/mac-speed-eos.log 2>&1
log "queue3 exit $?"
