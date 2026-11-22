#!/bin/zsh
# oMLX native kernels, keep or roll back (TODO.md): speed-quick-eos on the three production oMLX models,
# three rounds each with and without the kernels, alternating so drift through the day hits both alike;
# then speed-concurrent-eos for flint once each way. About 1.5 hours.
#
# "Without" moves the five native extensions (custom_kernels/*/_ext*.so) aside, so their imports fail and
# oMLX takes the same fallback path as a default Homebrew install (no reinstall needed). The script holds
# an ai-swap reservation while it swaps them, so no oMLX process runs on a half-changed install, and puts
# the kernels back at the end, leaving production as it was. The decision is then made from the results.
cd "${0:A:h}/.."
source ~/.config/ai-swap/env
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
CK=/opt/homebrew/Cellar/omlx/0.8.0/libexec/lib/python3.11/site-packages/omlx/custom_kernels
STASH=~/.omlx/kernels-stash
PKGS=(attention lowbit oqh quant_matmul sparse_index)
api() { curl -s -H "Authorization: Bearer $AI_SWAP_API_KEY" "$@"; }

kernels() {   # on | off
  local tok
  until tok=$(api -X POST localhost:8080/api/lock -d '{"owner":"omlx-kernels-ab","reason":"swapping oMLX kernels","ttl_seconds":300}' \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])' 2>/dev/null); do sleep 30; done
  api -H "X-AI-Swap-Lock: $tok" -X POST localhost:8080/api/unload >/dev/null
  sleep 5
  for p in $PKGS; do
    if [[ $1 == off ]]; then mkdir -p $STASH/$p; mv $CK/$p/_ext*.so $STASH/$p/ 2>/dev/null
    else mv $STASH/$p/_ext*.so $CK/$p/ 2>/dev/null; fi
  done
  log "oMLX kernels $1 ($(ls $CK/*/_ext*.so 2>/dev/null | wc -l | tr -d ' ') of 5 extensions in place)"
  api -H "X-AI-Swap-Lock: $tok" -X DELETE localhost:8080/api/lock >/dev/null
}

run() {   # label model suite...
  local k=$1 m=$2; shift 2
  for s in "$@"; do
    local f=logs/mac-$m-$s-$k.log
    log "start $m $s ($k)"
    uv run aibench -c bench-mac.yaml run -m $m -s $s --tag mac-$k > $f 2>&1
    log "$m $s ($k) exit $? ($(grep -a -o -E 'tg@512=[0-9.]+tok/s|tg@8k=[0-9.]+tok/s' $f | tr '\n' ' '))"
  done
}
models=(omlx-flint omlx-qwen3.8-flash-next-budget-greedy omlx-qwen3.8-flash-next-mtp)

log "queue24 start (oMLX kernels A/B)"
trap 'kernels on' EXIT   # never leave production without the kernels it had
for r in 1 2 3; do
  kernels on;  for m in $models; do run kernels-r$r   $m speed-quick-eos; done
  kernels off; for m in $models; do run nokernels-r$r $m speed-quick-eos; done
done
run nokernels omlx-flint speed-concurrent-eos
kernels on
run kernels omlx-flint speed-concurrent-eos
trap - EXIT
log "queue24 done"
