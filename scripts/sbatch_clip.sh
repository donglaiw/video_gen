#!/usr/bin/env bash
# Slurm wrapper for one SkyReels-V2 clip. Slurm gives the job one GPU, which it
# sees as device 0 (ConstrainDevices=yes), so two clips never share a card.
#
# usage: sbatch [--hold] scripts/sbatch_clip.sh <name> <prompt_file> [run_clip.sh args, e.g. --image X]
#    or: scripts/submit_jobs.sh <jobs.txt>   (one sbatch per line)
#SBATCH --job-name=vgen
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --time=02:00:00
#SBATCH --output=logs/slurm/%x_%j.out
set -euo pipefail
ROOT="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
NAME="$1"; PROMPT="$2"; shift 2
echo "$(date '+%F %T') job=$SLURM_JOB_ID name=$NAME node=$(hostname) gpu=$(nvidia-smi -L)"
exec "$ROOT/scripts/run_clip.sh" "$NAME" "$PROMPT" 0 "$@"
