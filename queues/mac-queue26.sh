#!/bin/zsh
# Ripple DFlash2 retry and flint-on-Splash check (2026-11-24), about 2-3 hours:
# 1. Build llama.cpp master (2e779d5e7) at ~/src/llama.cpp-1124; b12192 predates Ripple's DFlash2 support and
#    aborts loading the drafter.
# 2. Convert Ricursive's drafter (ricursiveAI/Ripple-65B-Preview-DFlash2, 8 GB safetensors) with that build's
#    converter, which has the NoPE metadata fix ashbash's Nov 6 GGUF lacks. --target-model-dir only needs the
#    target's config and tokenizer, so the 130 GB target weights are not downloaded.
# 3. Ripple on master alone and with the drafter: speed-quick-eos and speed-concurrent-eos.
# 4. terminal-x3 on swap-flint: flint as agents now get it from ai-swap (Splash, DFlash2, bf16 activations).
# Each run waits until ai-swap is free (three checks a minute apart).
cd "${0:A:h}/.."
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
source ~/.config/ai-swap/env
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
locked() { curl -s -H "Authorization: Bearer $AI_SWAP_API_KEY" localhost:8080/api/lock | grep -q '"owner"'; }
wait_free() { local n=0; while (( n < 3 )); do if locked; then n=0; else n=$((n+1)); fi; sleep 60; done; }
run() {   # tag model suite...
  local t=$1 m=$2; shift 2
  for s in "$@"; do
    local f=logs/mac-$m-$s-$t.log
    while :; do
      wait_free
      log "start $m $s ($t)"
      uv run aibench -c bench-mac.yaml run -m $m -s $s --tag $t > $f 2>&1
      rc=$?
      grep -q "already reserved by" $f && { log "$m $s: ai-swap taken, waiting"; continue; }
      break
    done
    log "$m $s ($t) exit $rc ($(grep -a -o -E '(pass@1|pass)=[0-9.]+%|tg@8k=[0-9.]+tok/s|agg@1k c8 tok/s *│ *[0-9.]+' $f | tr -s ' ' | tr '\n' ' '))"
  done
}

log "queue26 start (llama.cpp master build, Ripple DFlash2 drafter, flint terminal-x3 via ai-swap)"
L=~/src/llama.cpp-1124 R=~/models/ripple-65b
D=$R/Ripple-65B-Preview-DFlash2-m1124-Q8_0.gguf

# 1. build
if [[ ! -x $L/build/bin/llama-server ]]; then
  log "build llama.cpp master"
  [[ -d $L ]] || git -C ~/src/llama.cpp worktree add --detach $L 2e779d5e7 > logs/mac-build-1124.log 2>&1
  if cmake -S $L -B $L/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF >> logs/mac-build-1124.log 2>&1 \
     && cmake --build $L/build -j 16 --target llama-server llama-quantize >> logs/mac-build-1124.log 2>&1; then
    log "build llama.cpp master done"; else log "build llama.cpp master FAILED (logs/mac-build-1124.log)"; exit 1; fi
fi

# 2. drafter
if [[ ! -s $D ]]; then
  log "convert Ripple DFlash2 drafter"
  {
    uvx --from huggingface_hub hf download ricursiveAI/Ripple-65B-Preview-DFlash2 --local-dir $R/dflash2-hf &&
    uvx --from huggingface_hub hf download ricursiveAI/Ripple-65B-Preview --local-dir $R/target-hf \
        --include "*.json" --include "*.jinja" --exclude "*.safetensors*" &&
    (cd $L && uv run --no-project --python 3.12 --with-requirements requirements/requirements-convert_hf_to_gguf.txt \
        python convert_hf_to_gguf.py $R/dflash2-hf --target-model-dir $R/target-hf \
        --outtype q8_0 --outfile $D)
  } > logs/mac-convert-ripple-dflash2.log 2>&1
  if [[ -s $D ]]; then log "convert Ripple DFlash2 drafter done ($(du -h $D | cut -f1))"
  else log "convert Ripple DFlash2 drafter FAILED (logs/mac-convert-ripple-dflash2.log)"; fi
fi

# 3. Ripple speed
run ripple-dflash2 ripple-65b-m1124 speed-quick-eos speed-concurrent-eos
[[ -s $D ]] && run ripple-dflash2 ripple-65b-dflash2 speed-quick-eos speed-concurrent-eos

# 4. flint through ai-swap
run flint-splash-swap swap-flint terminal-x3
log "queue26 done"
