#!/bin/bash
# Inkling 2 Mini on Strata (2026-11-24), about 7 h. Strata 0.2.21 added a native Inkling 2 Mini engine
# (strata-inkling 0.1.67, Linux HIP build for gfx1201); its release notes report 66 tok/s on an RX 7900 XT,
# where every llama.cpp build here decodes at 31-35. The engine was updated 0.1.48 -> 0.1.67 first
# (`strata components rollback` returns to 0.1.48).
# 1. Download the strata-inkling engine and the SQ-20 pack (19.3 GB) with one start under an ai-swap lock.
# 2. Flash-Next (`strata`) speed-quick on the new engine, against its 0.1.48 numbers.
# 3. strata-inkling-2-mini-medium: speed-quick-eos, terminal-x3, livecodebench-64k (the 30), against
#    llama.cpp's inkling-2-mini-medium (96.3% in 38.5 min, 22/30).
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
source ~/.config/ai-swap/env
H="Authorization: Bearer $AI_SWAP_API_KEY"
log() { echo "$(date "+%F %T") $*" >> logs/r9700-queue.log; }
locked() { curl -s -H "$H" localhost:8080/api/lock | grep -q "\"owner\""; }
wait_free() { local n=0; while (( n < 3 )); do if locked; then n=0; else n=$((n+1)); fi; sleep 60; done; }

# ---- 1. download ----
log "inkling-strata queue start"
if [[ ! -s logs/r9700-strata-inkling-probe.json ]]; then
wait_free
TOK=$(curl -s -H "$H" -X POST localhost:8080/api/lock -d '{"owner":"inkling-strata-setup","reason":"Strata Inkling download + first start","ttl_seconds":7200}' \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])') || { log "inkling-strata: lock failed"; exit 1; }
curl -s -H "$H" -H "X-AI-Swap-Lock: $TOK" -X POST localhost:8080/api/unload >/dev/null; sleep 5
log "strata inkling first start (download)"
timeout 7000 strata launch --family inkling-2-mini --model sq-20 --context 80k --vision off --parallel 3 --tune skip \
  --yes --no-tui --port 8091 > logs/r9700-strata-inkling-setup.log 2>&1
ok=no
for i in $(seq 1 120); do curl -sf localhost:8091/v1/models >/dev/null && { ok=yes; break; }; sleep 10; done
if [[ $ok == yes ]]; then
  curl -s localhost:8091/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"inkling-2-mini-sq-20","max_tokens":400,
    "messages":[{"role":"user","content":"Write a Python function that checks whether a string is a palindrome."}],
    "chat_template_kwargs":{"reasoning_effort":"medium"}}' > logs/r9700-strata-inkling-probe.json
  log "strata inkling up ($(python3 -c 'import json;d=json.load(open("logs/r9700-strata-inkling-probe.json"));print(d.get("usage"))' 2>&1 | head -c 200))"
else
  log "strata inkling FAILED to start (logs/r9700-strata-inkling-setup.log)"
fi
strata launch --stop >> logs/r9700-strata-inkling-setup.log 2>&1; sleep 10
curl -s -H "$H" -H "X-AI-Swap-Lock: $TOK" -X DELETE localhost:8080/api/lock >/dev/null
[[ $ok == yes ]] || exit 1
fi

# ---- 2 and 3 ----
run() { local tag=$1 m=$2; shift 2; for s in "$@"; do
  while :; do
    wait_free
    log "start $m $s ($tag)"
    uv run aibench run -m $m -s $s --tag $tag > logs/r9700-$m-$s-$tag.log 2>&1
    rc=$?
    grep -q "already reserved by" logs/r9700-$m-$s-$tag.log && { log "$m $s: ai-swap taken, waiting"; continue; }
    break
  done
  log "$m $s ($tag) exit $rc ($(grep -a -o -E "(pass@1|pass)=[0-9.]+%|tg@8k=[0-9.]+tok/s" logs/r9700-$m-$s-$tag.log | tr '\n' ' '))"
done; }

run strata-0167 strata speed-quick
run inkling-strata strata-inkling-2-mini-medium speed-quick terminal-x3 livecodebench-64k
log "inkling-strata queue done"
