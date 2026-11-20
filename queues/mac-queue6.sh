#!/bin/zsh
# Qwen3.8-Flash-Next on sushi at 64k, twice, after the 128k queue: a fairer score and a noise check vs Strata's 83.3%.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
while pgrep -f "logs/mac-queue[2345].sh" > /dev/null; do sleep 60; done
log "queue6 start (sushi qwen3.8-flash-next 64k x2)"
m=sushi-qwen3.8-flash-next-4bpw
for i in 1 2; do
  log "start $m 64k run $i"
  uv run aibench -c bench-mac.yaml run -m $m -s livecodebench-64k --tag mac-64k > logs/mac-64k-$m-$i.log 2>&1
  log "$m 64k run $i exit $?"
done
log "queue6 done"
