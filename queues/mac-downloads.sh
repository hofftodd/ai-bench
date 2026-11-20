#!/bin/zsh
# Models for the sushi (MLX) and ds4 (DwarfStar) backends, one download at a time.
# Writes logs/mac-downloads.done.<name> when each one finishes, so the bench queue can wait on it.
cd "${0:A:h}/.."   # the ai-bench checkout this script is in
log() { echo "$(date '+%F %T') $*" >> logs/mac-downloads.log; }
export DS4_GGUF_DIR=$HOME/models/ds4
mkdir -p $DS4_GGUF_DIR

get() {   # name, command...
  local name=$1; shift
  log "start $name"
  if "$@" > logs/mac-download-$name.log 2>&1; then log "done $name"; touch logs/mac-downloads.done.$name
  else log "FAILED $name (exit $?)"; fi
}

get ds4f-q2                ds4-download ds4f-q2
get glm-5.3-flash          sushi pull glm-5.3-flash:2.4bpw
get mimo-v2.6-flash        sushi pull mimo-v2.6-flash:2.3bpw
get qwen3.8-flash-next-4b  sushi pull qwen3.8-flash-next:4bpw
get ds4f-q4                ds4-download ds4f-q4
log "all downloads finished"
