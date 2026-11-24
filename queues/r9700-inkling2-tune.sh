#!/bin/bash
# Inkling 2 Mini tuning on the R9700 (2026-11-23). Outside reports put it at 54-90 tok/s on this card,
# against our ~35 on Unsloth's ROCm fork; and at reasoning effort high it wrote 3.7x qwen3.8-27b's tokens.
# 1. Engine speed: same-day baseline (fork, ROCm, with/without DSpark) against llama.cpp master af5c58347
#    on Vulkan and ROCm and master + #32898 (Vulkan FA compact bias for Inkling 2) on Vulkan, with the
#    mainline-layout GGUF. Direct llama-server under an ai-swap lock: 64k context, q8_0 KV, one slot;
#    a short prompt, three ~8k-token code-review prompts and three story prompts each, plus llama-bench
#    (pp512 / tg128 at depth 0 and 16384) for the mainline builds. ~1 h. Waits for the builds
#    (~/models/inkling-2-mini/build-mainline-1123.sh) to finish.
# 2. Reasoning effort medium (inkling-2-mini-medium in bench.yaml) through ai-swap's existing entry:
#    terminal-x3 (~1-2 h), then livecodebench-64k, the 30 problems shared with the LCB-60 run (~6 h).
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
source ~/.config/ai-swap/env
H="Authorization: Bearer $AI_SWAP_API_KEY"
log() { echo "$(date "+%F %T") $*" >> logs/r9700-queue.log; }
locked() { curl -s -H "$H" localhost:8080/api/lock | grep -q "\"owner\""; }
wait_free() { local n=0; while (( n < 3 )); do if locked; then n=0; else n=$((n+1)); fi; sleep 60; done; }

# ---- 1. engine speed ----
speed() {
  local D=~/models/inkling-2-mini S=~/src
  local ROOT=$D/Inkling-2-Mini-UD-Q4_K_XL.gguf MAIN=~/models-test/inkling-2-mini-mainline/Inkling-2-Mini-UD-Q4_K_XL.gguf
  local FORK=$S/llama.cpp-unsloth-b12588/rocm
  local DSP="--model-draft $D/dspark-Inkling-2-Mini-Q8_0.gguf --spec-type draft-dspark --spec-draft-n-max 3 --n-gpu-layers-draft 99"
  local OUT=$D/speed/engines-$(date +%Y%m%d-%H%M); mkdir -p $OUT
  until grep -q "mainline builds done" $D/setup.log; do sleep 60; done
  wait_free
  local TOK
  TOK=$(curl -s -H "$H" -X POST localhost:8080/api/lock -d '{"owner":"inkling-engines","reason":"Inkling 2 Mini engine speed test","ttl_seconds":7200}' \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])') || { log "inkling engines: lock failed"; return 1; }
  curl -s -H "$H" -H "X-AI-Swap-Lock: $TOK" -X POST localhost:8080/api/unload >/dev/null; sleep 5
  log "start inkling engine speed -> $OUT"

  # Prompts: aibench's own source + a review task (~8k tokens), a short coding task, and speed-quick's story prompt.
  python3 - > $OUT/long.json <<'EOF'
import glob, json, os
src = "".join(open(f).read() for f in sorted(glob.glob(os.path.expanduser("~/dev/ai-tools/ai-bench/src/aibench/*.py"))))[:30000]
msg = src + "\n\nReview the Python code above. List the three most likely bugs, each with a short fix."
print(json.dumps({"messages":[{"role":"user","content":msg}],"max_tokens":256,"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0,"cache_prompt":False}))
EOF
  python3 -c 'import json; print(json.dumps({"messages":[{"role":"user","content":"Write a Python function that parses an ISO-8601 duration such as P3DT4H5M6S into a timedelta, with validation."}],"max_tokens":256,"temperature":1.0,"top_p":1.0,"top_k":0,"min_p":0,"cache_prompt":False}))' > $OUT/short.json
  uv run python - > $OUT/story.json <<'EOF'
import json, random, sys, os
sys.path.insert(0, os.path.expanduser("~/dev/ai-tools/ai-bench/src"))
from aibench.suites.throughput import _filler
body = "Session 0123abcd.\n\nNotes:\n" + _filler(5600, random.Random(1234)) + "\n\nWrite a long, detailed story inspired by the notes above."
print(json.dumps({"messages":[{"role":"user","content":body}],"max_tokens":128,"temperature":0.7,"ignore_eos":True,"cache_prompt":False}))
EOF
  local PARSE='import sys,json; d=json.load(sys.stdin); t=d.get("timings",{}); print("  %-5s prompt %5d tok at %6.0f tok/s | decode %5.1f tok/s (%d tok) | draft %s/%s" % (sys.argv[1], t.get("prompt_n",0), t.get("prompt_per_second",0), t.get("predicted_per_second",0), t.get("predicted_n",0), t.get("draft_n_accepted","-"), t.get("draft_n","-")))'

  dev() { # the R9700's device name in a build (Vulkan numbering includes the 780M)
    "$1/llama-server" --list-devices 2>/dev/null | grep -i "r9700\|navi 48\|gfx1201" | head -1 | sed -E 's/^ *([A-Za-z]+[0-9]+).*/\1/'; }
  variant() { # name bindir model extra-args...
    local name=$1 bin=$2 m=$3; shift 3
    local d; d=$(dev $bin); [ -n "$d" ] || { echo "=== $name: no R9700 device found"; return; }
    echo "=== $name ($d): $bin $*" | sed "s|$HOME|~|g"
    setsid nohup $bin/llama-server -m $m -ngl 99 --device $d --jinja --flash-attn on --threads 16 --port 5899 \
      -c 65536 -ctk q8_0 -ctv q8_0 --parallel 1 "$@" </dev/null >$OUT/$name.log 2>&1 &
    local pid=$!
    for i in $(seq 1 150); do curl -sf localhost:5899/health >/dev/null && break; sleep 2; done
    if ! curl -sf localhost:5899/health >/dev/null; then echo "  failed to start"; tail -3 $OUT/$name.log; kill -9 $pid; sleep 3; return; fi
    echo "  vram $(cat /sys/class/drm/card*/device/mem_info_vram_used | sort -n | tail -1 | awk '{printf "%.1f GiB", $1/2^30}')"
    curl -s localhost:5899/v1/chat/completions -d @$OUT/short.json | python3 -c "$PARSE" short
    for r in 1 2 3; do curl -s localhost:5899/v1/chat/completions -d @$OUT/long.json | python3 -c "$PARSE" code; done
    for r in 1 2 3; do curl -s localhost:5899/v1/chat/completions -d @$OUT/story.json | python3 -c "$PARSE" story; done
    kill $pid; sleep 3; kill -9 $pid 2>/dev/null; sleep 3
  }
  bench() { # name bindir model
    local d; d=$(dev $2); [ -n "$d" ] || return
    echo "=== llama-bench $1 ($d)"
    $2/llama-bench -m $3 -dev $d -ngl 99 -fa 1 -ctk q8_0 -ctv q8_0 -p 512 -n 128 -d 0,16384 -r 3 2>&1 | grep -E "^\|"
  }
  {
    variant fork-rocm-dspark  $FORK $ROOT $DSP
    variant fork-rocm         $FORK $ROOT
    variant master-vulkan     $S/llama.cpp-ink-master/build-vulkan/bin   $MAIN
    variant pr32898-vulkan    $S/llama.cpp-ink-pr32898/build-vulkan/bin  $MAIN
    variant master-rocm       $S/llama.cpp-ink-master/build-rocm/bin     $MAIN
    bench master-vulkan  $S/llama.cpp-ink-master/build-vulkan/bin  $MAIN
    bench pr32898-vulkan $S/llama.cpp-ink-pr32898/build-vulkan/bin $MAIN
    bench master-rocm    $S/llama.cpp-ink-master/build-rocm/bin    $MAIN
  } > $OUT/summary.txt 2>&1
  curl -s -H "$H" -H "X-AI-Swap-Lock: $TOK" -X DELETE localhost:8080/api/lock >/dev/null
  log "inkling engine speed done ($OUT/summary.txt)"
}

# ---- 2. reasoning effort medium ----
run() { local m=$1; shift; for s in "$@"; do
  local tag=effort-medium; [[ $s == *64k ]] && tag=effort-medium-64k
  grep -q "^$(date +%F) .* $m $s exit 0" logs/r9700-queue.log && continue  # rerun-safe
  while :; do
    wait_free
    log "start $m $s"
    uv run aibench run -m $m -s $s --tag $tag > logs/r9700-$m-$s.log 2>&1
    rc=$?
    grep -q "already reserved by" logs/r9700-$m-$s.log && { log "$m $s: ai-swap taken, waiting"; continue; }
    break
  done
  log "$m $s exit $rc ($(grep -a -o -E "(pass@1|pass)=[0-9.]+%" logs/r9700-$m-$s.log | tail -1))"
done; }

log "inkling tuning queue waiting"
speed
run inkling-2-mini-medium terminal-x3 livecodebench-64k
log "inkling tuning queue done"
