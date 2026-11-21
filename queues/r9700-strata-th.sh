cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
log() { echo "$(date "+%F %T") $*" >> logs/r9700-queue.log; }
log "start strata terminal-hard (rerun: 10:59 attempt had no strata on PATH)"
~/.local/bin/uv run aibench run -m strata -s terminal-hard --tag gaps > logs/r9700-strata-terminal-hard.log 2>&1
log "strata terminal-hard exit $?"
