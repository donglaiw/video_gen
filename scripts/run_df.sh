#!/usr/bin/env bash
# Run SkyReels-V2 diffusion-forcing generation on one GPU.
# Usage: scripts/run_df.sh <gpu> <name> <num_frames> <prompt_file> [extra generate_video_df.py args]
# Output: outputs/<timestamp>_<name>/ with the mp4, cmd.txt, run.log, vram.csv, summary.txt
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GPU="$1"; NAME="$2"; NFRAMES="$3"; PROMPT_FILE="$4"; shift 4

MODEL_ID="${MODEL_ID:-Skywork/SkyReels-V2-DF-14B-540P}"
RES="${RES:-540P}"
SEED="${SEED:-42}"

RUN="$ROOT/outputs/$(date +%Y%m%d_%H%M%S)_${NAME}"
mkdir -p "$RUN"
export HF_HOME="$ROOT/models/hf" HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES="$GPU"
# torch.compile (Triton) needs a C compiler; the machine has none, so use the env's conda gcc.
export PATH="$ROOT/env/bin:$PATH" CC="$ROOT/env/bin/gcc" CXX="$ROOT/env/bin/g++"

# Default long-video settings from the upstream README (synchronous mode).
CMD=("$ROOT/env/bin/python" "$ROOT/SkyReels-V2/generate_video_df.py"
  --model_id "$MODEL_ID" --resolution "$RES"
  --ar_step 0 --base_num_frames 97 --num_frames "$NFRAMES"
  --overlap_history 17 --addnoise_condition 20
  --seed "$SEED" --outdir "$NAME"
  --prompt "$(cat "$PROMPT_FILE")" "$@")

printf '%q ' "${CMD[@]}" > "$RUN/cmd.txt"; echo >> "$RUN/cmd.txt"
cp "$PROMPT_FILE" "$RUN/prompt.txt"
git -C "$ROOT/SkyReels-V2" rev-parse HEAD > "$RUN/skyreels_commit.txt"

nvidia-smi -i "$GPU" --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader -l 5 > "$RUN/vram.csv" &
SMI=$!
trap 'kill $SMI 2>/dev/null || true' EXIT

cd "$RUN"
START=$(date +%s)
set +e
"${CMD[@]}" > run.log 2>&1
STATUS=$?
set -e
END=$(date +%s)
kill $SMI 2>/dev/null || true

PEAK=$(awk -F', ' '{gsub(/ MiB/,"",$2); if ($2>m) m=$2} END {print m+0}' vram.csv)
MP4=$(find result -name '*.mp4' 2>/dev/null | head -1)
[ -n "$MP4" ] && mv "$MP4" . && rm -rf result
{
  echo "status=$STATUS"
  echo "gpu=$GPU model=$MODEL_ID res=$RES num_frames=$NFRAMES seed=$SEED extra=$*"
  echo "wall_seconds=$((END-START))"
  echo "peak_vram_mib=$PEAK"
  echo "video=$(ls *.mp4 2>/dev/null || echo none)"
} | tee summary.txt
exit $STATUS
