#!/bin/zsh
# oMLX vs llama.cpp vs sushi on Qwen3.8-Flash-Next. Waits for the oQ4e download, then:
# oMLX without MTP (speed), oMLX with MTP (speed + quality), and concurrency on llama.cpp and sushi.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
until grep -q -E "download qwen3.8-flash-next oQ4e-mtp (done|FAILED)" logs/mac-queue.log; do sleep 60; done
grep -q "download qwen3.8-flash-next oQ4e-mtp FAILED" logs/mac-queue.log && { log "queue9 aborted: download failed"; exit 1; }
log "queue9 start"
smoke() {
  if ! uv run aibench -c bench-mac.yaml run -m $1 -s humaneval-quick -n 2 --no-dashboard > logs/mac-$1-smoke.log 2>&1 \
       || grep -q -E "✗|failed to load|load: " logs/mac-$1-smoke.log; then
    log "$1 smoke test FAILED (see logs/mac-$1-smoke.log)"; return 1; fi
  log "$1 smoke ok"
}
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    tag=mac; [[ $s == livecodebench-64k ]] && tag=mac-64k
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
    log "$m $s exit $?"
  done
}
smoke omlx-qwen3.8-flash-next && run omlx-qwen3.8-flash-next speed-quick-eos speed-concurrent-eos
smoke omlx-qwen3.8-flash-next-mtp && run omlx-qwen3.8-flash-next-mtp speed-quick-eos speed-concurrent-eos humaneval-quick livecodebench-64k livecodebench
run qwen3.8-flash-next speed-concurrent-eos
run sushi-qwen3.8-flash-next-4bpw speed-concurrent-eos
log "queue9 done"
