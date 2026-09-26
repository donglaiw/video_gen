# SkyReels-V2 (Wan 14B) setup plan — cajal

Drafted 2026-09-26. Status: **plan only, nothing installed yet.**

## Machine facts (checked 2026-09-26)

- 2× RTX PRO 6000 Blackwell, 96 GB each, driver 595.91, CUDA 13.2 driver API.
- 246 GB RAM, 64 cores.
- Disk: `/` (holds `~/dw-os`) has **175 GB free**; `/data` has **5.9 TB free**.
- conda/mamba at `/data/donglai/miniforge3`. HF and GitHub reachable.

## Key constraints

1. **Upstream pins won't run on Blackwell.** `requirements.txt` pins
   `torch==2.5.1`, which has no sm_120 kernels. Use a current PyTorch cu128+
   build (2.8 or newer) and leave the other pins alone unless they conflict.
2. **flash_attn** has to be built or found as a wheel for sm_120 + our torch.
   If the build fails, check whether the repo falls back to torch SDPA (as
   upstream Wan does) and run without it first. It's slower but correct.
3. **Disk.** Each 14B checkpoint is about 69 GB (DF) or 82 GB (I2V-720P). Two of
   them would fill `/`. So `video_gen/models` will be a **symlink to
   `/data/donglai/video_gen/models`**. It still sits inside `video_gen/`, but the
   bytes live on `/data`. HF cache goes to the same place.

## Layout (everything under `~/dw-os/coding/video_gen/`)

```
video_gen/
├── PLAN.md          # this file
├── README.md        # how to run, once working
├── SkyReels-V2/     # upstream clone, pinned commit recorded in README
├── env/             # conda env (created with -p, Python 3.11)
├── models/  ->      /data/donglai/video_gen/models   (weights + HF cache)
├── scripts/         # our wrappers: smoke test, t2v, long video, 2-GPU
├── prompts/         # prompt text files
├── outputs/         # generated mp4s, one subfolder per run, plus the command
└── logs/            # stdout/stderr, timing, peak VRAM per run
```

`coding/` is gitignored in dw-os. Optionally `git init` inside `video_gen/`
to track `scripts/`, `prompts/` and `README.md` only (ignore `env/`, `models/`,
`outputs/` and `SkyReels-V2/`).

## Steps

Each step has a check. Don't move on until it passes.

### 1. Folders + clone
- `mkdir -p` the layout; create `/data/donglai/video_gen/models` and symlink it.
- `git clone https://github.com/SkyworkAI/SkyReels-V2` and record the commit SHA.
- **Check:** `models/` resolves to `/data`; the SHA is written to README.

### 2. Environment
- `mamba create -p video_gen/env python=3.11`
- Install PyTorch + torchvision for CUDA 12.8+ from the pytorch.org index.
- `pip install -r requirements.txt` **minus** the `torch`, `torchvision` and
  `flash_attn` lines (install from a filtered copy).
- Then try `flash_attn` (`pip install flash-attn --no-build-isolation`, ~20–40 min
  compile on 64 cores). If it fails, skip it and use the SDPA fallback.
- `xfuser` is only needed for the 2-GPU single-video mode (step 6).
- **Check:** `torch.cuda.get_device_capability()` returns `(12, 0)` on both
  GPUs, and a bf16 matmul runs on each.

### 3. Weights
- Set `HF_HOME=video_gen/models/hf`.
- Download **`Skywork/SkyReels-V2-DF-14B-540P` first** (69 GB). DF
  ("diffusion forcing") is the model that does long video.
- Add `DF-14B-720P` later if 540P quality isn't enough.
- **Check:** the download finishes and sizes match the HF listing.

### 4. Smoke test (1 GPU, short clip)
- DF-14B-540P, `--num_frames 97` (~4 s), fixed seed, with `--offload` off.
- **Check:** a valid mp4 is written. Log wall time and peak VRAM (upstream
  reports ~51 GB peak for 14B 540P).

### 5. Long video (1 GPU)
- Upstream recommended synchronous settings:
  `--ar_step 0 --base_num_frames 97 --overlap_history 17 --addnoise_condition 20`,
  with `--num_frames` 257 (10 s), then 737 (30 s), then 1457 (60 s).
- Optionally try `--teacache --use_ret_steps` for speed and compare quality by eye.
- **Check:** watch the transitions for seams and drift. Log time per second
  of video.

### 6. Using both GPUs
- **A. Throughput:** run one job per GPU with `CUDA_VISIBLE_DEVICES=0` and
  `CUDA_VISIBLE_DEVICES=1`. This is the simplest option and the default.
- **B. Latency:** `torchrun --nproc_per_node=2 ... --use_usp` to split one video
  across both GPUs. Needs `xfuser`, and `--prompt_enhancer` doesn't work with it.
- **Check:** option B gives the same output as 1 GPU for the same seed
  (roughly) and is faster.

### 7. Wrap up
- `scripts/run_long.sh` (prompt file, length, GPU id → `outputs/<timestamp>/`).
- README: install recap, commit SHA, measured timings and VRAM, known issues.

## Later (not in this pass)

- I2V-14B-720P (82 GB) for image-conditioned starts.
- Prompt enhancer (downloads an extra LLM; check size first).
- ComfyUI front end, reached only over an SSH tunnel. Never expose it publicly
  without strong authentication.

## Open questions

- Is 540P acceptable, or go straight to 720P?
- Should `video_gen/` get its own git repo for scripts and prompts?
