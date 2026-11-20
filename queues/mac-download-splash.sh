#!/bin/zsh
# GGUFs and DFlash2 drafts for the Splash test (queue17). The drafts go to the Hugging Face cache,
# where `splash serve --model-dir` looks for them; the GGUFs go where bench-mac.yaml's llama.cpp entries had them.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-queue.log; }
hf() { uvx --from huggingface_hub hf "$@" >> logs/mac-download-splash.log 2>&1; }
log "start download splash models"
ok=1
hf download incoai/Flint-DFlash2 || ok=0
hf download incoai/Qwen3.8-Flash-Next-DFlash2 || ok=0
hf download unsloth/flint-GGUF flint-UD-Q4_K_XL.gguf --local-dir ~/models/flint || ok=0
hf download unsloth/Qwen3.8-Flash-Next-GGUF --include 'UD-Q4_K_XL/*' --local-dir ~/models/qwen3.8-flash-next || ok=0
if (( ok )); then log "download splash models done"; else log "download splash models FAILED"; fi
