#!/usr/bin/env bash
# Submit one Slurm job per line of a jobs file: name|prompt_file|run_clip.sh args.
# Paths are relative to video_gen/ and are made absolute here.
# usage: scripts/submit_jobs.sh <jobs.txt> [extra sbatch flags, e.g. --hold]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOBS="$(realpath "$1")"; shift
cd "$ROOT"; mkdir -p logs/slurm
while IFS='|' read -r name prompt extra; do
  [ -z "$name" ] && continue
  extra=$(sed "s#\(--image\|--end_image\|--video_path\) \([^/ ][^ ]*\)#\1 $ROOT/\2#g" <<< "$extra")
  # shellcheck disable=SC2086
  id=$(sbatch --parsable --job-name="$name" "$@" scripts/sbatch_clip.sh "$name" "$ROOT/$prompt" $extra)
  echo "$id $name"
done < "$JOBS"
