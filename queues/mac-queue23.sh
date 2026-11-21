#!/bin/zsh
# DeepSeek V4.1 Flash rerun with --memory-guard aggressive (2026-11-20). queue21's runs were void: oMLX's
# default guard left ~0.1 GB for prefill beside the 206.6 GB resident model and rejected 59 of 60 prompts.
cd "${0:A:h}/.."
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
run() {   # model suite...
  local m=$1; shift
  for s in "$@"; do
    tag=mac; [[ $s == *64k ]] && tag=mac-64k
    log "start $m $s"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $tag > logs/mac-$m-$s.log 2>&1
    log "$m $s exit $? ($(grep -a -o -E '(pass@1|pass)=[0-9.]+%|tg@512=[0-9.]+tok/s' logs/mac-$m-$s.log | tail -1); rejected by guard: $(grep -a -c 'memory guard rejected' logs/mac-$m-$s.log))"
  done
}
log "queue23 start"
run omlx-deepseek-v4.1-flash speed-quick-eos livecodebench-60-64k
run omlx-deepseek-v4.1-flash-budget livecodebench-60
log "queue23 done"
