# Queues

The scripts that ran each batch of Mac Studio benchmarks and downloads, kept so every result can be traced to
exactly how it was produced. `ANALYSIS-mac.md` and `TODO.md` refer to them by name (`mac-queue13.sh`, …).

- `mac-queueN.sh` runs a list of `aibench run` jobs one at a time. Most wait for the previous queue to log
  `queueN done` in `logs/mac-queue.log` before starting, so several can be lined up.
- `mac-download-*.sh` fetch model weights (`hf download`) and log `download <repo> done|FAILED`, which queues
  wait on.

They're zsh scripts that `cd` to the ai-bench checkout they're in and write their output to `logs/` (gitignored).
Start one detached so it outlives the terminal:

```bash
nohup caffeinate -i zsh queues/mac-queue19.sh >/dev/null 2>&1 & disown
```

Every run reserves the machine's ai-swap and unloads its models while it runs (`reserve:` in the config).
Scripts from before 2026-11-19 pointed at an older checkout path (`~/dev/ai-bench`); they now use their own location.
