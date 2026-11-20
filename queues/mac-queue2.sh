#!/bin/zsh
# sushi + ds4 runs on the Mac, after mac-queue.sh (llama.cpp) finishes; each waits for its download.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }

while pgrep -f "logs/mac-queue.sh" > /dev/null; do sleep 60; done
log "queue2 start (sushi + ds4)"

run() {   # download marker, model key
  local marker=$1 model=$2
  while [[ ! -f logs/mac-downloads.done.$marker ]]; do
    if ! pgrep -f "logs/mac-downloads.sh" > /dev/null; then log "skip $model: download $marker never finished"; return; fi
    sleep 60
  done
  log "start $model"
  uv run aibench -c bench-mac.yaml run -m $model -s mac-engine --tag mac-baseline --no-dashboard > logs/mac-$model.log 2>&1
  log "$model exit $?"
}

run ds4f-q2               ds4-q2
run glm-5.3-flash         sushi-glm-5.3-flash
run mimo-v2.6-flash       sushi-mimo-v2.6-flash
run qwen3.8-flash-next-4b sushi-qwen3.8-flash-next-4bpw
run ds4f-q4               ds4-q4
log "queue2 done"
