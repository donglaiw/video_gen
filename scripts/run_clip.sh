#!/usr/bin/env bash
# One SkyReels-V2 DF-14B-540P clip, conditioned on a start image (and optionally
# an end image or a prefix video to extend).
#
# usage: run_clip.sh <name> <prompt_file> <gpu> [--image X] [--end_image Y] [--video_path Z] [extra args]
# output: outputs/<name>_<timestamp>/{*.mp4, cmd.txt, run.log, vram.csv}
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="$1"; PROMPT_FILE="$2"; GPU="$3"; shift 3

MODEL=$(ls -d "$ROOT"/models/hf/hub/models--Skywork--SkyReels-V2-DF-14B-540P/snapshots/*/ | head -1)
OUT="$ROOT/outputs/${NAME}_$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

CMD=("$ROOT/env/bin/python" generate_video_df.py
  --model_id "$MODEL" --resolution 540P
  --num_frames "${NUM_FRAMES:-121}" --base_num_frames 97
  --overlap_history 17 --addnoise_condition 20 --ar_step 0
  --inference_steps "${STEPS:-30}" --seed "${SEED:-42}" --fps 24
  --prompt "$(cat "$PROMPT_FILE")" --outdir "$OUT" "$@")

printf '%q ' "${CMD[@]}" > "$OUT/cmd.txt"; echo >> "$OUT/cmd.txt"
cp "$PROMPT_FILE" "$OUT/prompt.txt"

nvidia-smi -i "$GPU" --query-gpu=timestamp,memory.used --format=csv -l 5 > "$OUT/vram.csv" &
SMI=$!
trap 'kill $SMI 2>/dev/null' EXIT

cd "$ROOT/SkyReels-V2"
export PATH="$ROOT/env/bin:$PATH" CC="$ROOT/env/bin/gcc"   # triton/inductor need a C compiler
START=$(date +%s)
CUDA_VISIBLE_DEVICES="$GPU" HF_HOME="$ROOT/models/hf" "${CMD[@]}" 2>&1 | tee "$OUT/run.log"
echo "wall_seconds=$(( $(date +%s) - START ))" | tee -a "$OUT/run.log"
echo "peak_vram_mib=$(tail -n +2 "$OUT/vram.csv" | awk -F', ' '{gsub(/ MiB/,"",$2); if($2>m)m=$2} END{print m}')" | tee -a "$OUT/run.log"
echo "out=$OUT"
