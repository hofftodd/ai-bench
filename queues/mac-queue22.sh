#!/bin/zsh
# oMLX speed reruns after rebuilding Homebrew oMLX 0.8.0 with its native kernels (--with-custom-kernel,
# 2026-11-20). Every earlier oMLX number ran on the fallback path. About 20 minutes; queue21 waits for it.
cd "${0:A:h}/.."
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag mac-kernels > logs/mac-$m-$s-kernels.log 2>&1
    log "$m $s exit $? ($(grep -a -o -E 'tg@512=[0-9.]+tok/s|tg@8k=[0-9.]+tok/s' logs/mac-$m-$s-kernels.log | tail -1))"
  done
}
log "queue22 start (oMLX with native kernels)"
run omlx-flint speed-quick-eos speed-concurrent-eos
run omlx-qwen3.8-flash-next-budget-greedy speed-quick-eos
run omlx-qwen3.8-flash-next-mtp speed-quick-eos
log "queue22 done"
