#!/bin/zsh
# oMLX 0.8.0 checks, then Splash under load (2026-11-20).
# 1. Tuned Flash-Next (budget + greedy) on livecodebench: 90.0% on oMLX 0.7.3 (46 min).
# 2. ai-swap's tuned qwen3.8-flash-next still forces greedy on 0.8.0: two identical requests sent at
#    temperature 1.0 must give identical answers (force_sampling in ~/.omlx/model_settings.json).
# 3. splash-flint-bf16 (production flint-splash's settings) at 1/2/4/8 requests in flight.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
log "queue20 start (oMLX $(omlx --version 2>&1 | head -1))"
m=omlx-qwen3.8-flash-next-budget-greedy
log "start $m livecodebench"
uv run aibench -c bench-mac.yaml run -m $m -s livecodebench --tag mac-omlx080 > logs/mac-$m-livecodebench-omlx080.log 2>&1
log "$m livecodebench exit $? ($(grep -a -o 'pass@1=[0-9.]*%' logs/mac-$m-livecodebench-omlx080.log | tail -1))"

H="Authorization: Bearer $AI_SWAP_API_KEY"
body='{"model":"qwen3.8-flash-next","temperature":1.0,"top_p":0.95,"messages":[{"role":"user","content":"Write a Python function that merges two sorted lists. Code only."}],"max_tokens":3000}'
a=$(curl -s -m 900 localhost:8080/v1/chat/completions -H "$H" -H 'Content-Type: application/json' -d "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['choices'][0]['message'].get('content',''))")
b=$(curl -s -m 900 localhost:8080/v1/chat/completions -H "$H" -H 'Content-Type: application/json' -d "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['choices'][0]['message'].get('content',''))")
if [[ -n "$a" && "$a" == "$b" ]]; then log "ai-swap qwen3.8-flash-next: forced greedy holds on 0.8.0 (identical answers at temperature 1.0)"
else log "ai-swap qwen3.8-flash-next: answers DIFFER at temperature 1.0 (force_sampling may not hold on 0.8.0)"; fi

m=splash-flint-bf16
log "start $m speed-concurrent-eos"
uv run aibench -c bench-mac.yaml run -m $m -s speed-concurrent-eos --tag mac > logs/mac-$m-speed-concurrent-eos.log 2>&1
log "$m speed-concurrent-eos exit $?"
log "queue20 done"
