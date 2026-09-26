#!/usr/bin/env bash
# Rebuild env/ on a Blackwell (sm_120) machine. See PLAN.md for why each pin differs from upstream.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[ -d SkyReels-V2 ] || git clone https://github.com/SkyworkAI/SkyReels-V2
mamba create -y -p ./env python=3.11
P=./env/bin/pip
$P install -U pip
# Upstream pins torch 2.5.1 (no sm_120); 2.8 cu128 matches a prebuilt flash-attn wheel.
$P install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
$P install "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp311-cp311-linux_x86_64.whl"
grep -vE '^(torch|torchvision|flash_attn|opencv-python)\b' SkyReels-V2/requirements.txt > /tmp/skyreels_reqs.txt
$P install -r /tmp/skyreels_reqs.txt
# No libGL on this box; diffusers pinned to match transformers 4.49; decord + moviepy<2 are imported but not listed upstream.
$P install opencv-python-headless==4.10.0.84 diffusers==0.33.1 decord moviepy==1.0.3 huggingface_hub hf_transfer
