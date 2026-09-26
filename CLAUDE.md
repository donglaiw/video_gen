# CLAUDE.md — video_gen on cajal

Guidance for Claude Code (and people) generating video on this machine.

## The one rule: every GPU job goes through Slurm

cajal has 2× RTX PRO 6000 Blackwell (96 GB each). The machine is shared and
Slurm manages both GPUs (`partition=gpu`, `ConstrainDevices=yes`).

- **Submit every generation job with `sbatch`.** Never run
  `generate_video_df.py`, `scripts/run_clip.sh` or any other GPU script
  directly from a shell, `nohup`, tmux or a background task.
- Why: Slurm only knows about jobs it launched. A job started outside Slurm is
  invisible to it, so Slurm will put the next job on the same GPU. One
  SkyReels-V2 14B clip peaks at about **63 GB**, so two on one card crash with
  out-of-memory, usually taking the other person's job down too. This has
  already happened once.
- Short interactive GPU checks also go through Slurm:
  `srun --gres=gpu:1 -t 10 <cmd>`.
- **Never `scancel` or kill jobs or processes you didn't start.** Check
  `squeue -o "%.8i %.10u %.20j %.8T %.10M"` before assuming a GPU is yours.
  If something outside Slurm is holding a GPU, tell the user; don't kill it.

## Submitting clips

From `~/dw-os/coding/video_gen`:

```bash
# one clip: <name> <prompt file> [generate_video_df.py args]; use absolute paths
sbatch scripts/sbatch_clip.sh W99_test $PWD/prompts/foo.txt --image $PWD/frames/foo.png

# many clips: a file with one "name|prompt_file|args" line each (paths relative to video_gen/)
scripts/submit_jobs.sh my_jobs.txt            # add --hold to queue without starting
```

- Each job gets 1 GPU (seen as device 0), 16 CPUs, 110 GB RAM and a 2 h limit.
  Two clips run at once and the rest wait in order.
- Output goes to `outputs/<name>_<timestamp>/`: one `<name>_seed<seed>.mp4`, `cmd.txt`,
  `prompt.txt`, `run.log` (includes `wall_seconds` and `peak_vram_mib`) and
  `vram.csv`. Slurm stdout goes to `logs/slurm/<name>_<jobid>.out`.
- Monitor with `squeue` and cancel your own job with `scancel <id>`. Slurm
  accounting is off, so `sacct` shows nothing; check `logs/slurm/` and the
  run folder instead.
- Useful `run_clip.sh` env overrides (sbatch passes your environment through, e.g. `NUM_FRAMES=257 sbatch ...`):
  `NUM_FRAMES` (default 121, i.e. 5 s at 24 fps), `STEPS` (30), `SEED` (42).

## Model and what it can do

- SkyReels-V2 **DF-14B-540P** (diffusion forcing, built on Wan 14B), 960×544
  at 24 fps. Weights live in `models/` → `/data/donglai/video_gen/models`. `/`
  has only ~175 GB free, so keep large files on `/data`.
- Conditioning: `--image` (start frame), `--end_image` (land on a frame),
  `--video_path` (extend an existing clip, reusing the last 17 frames). Longer
  videos in one call use `--num_frames` 257 / 377 / 737 / 1457 (10 / 15 / 30 /
  60 s) with `--overlap_history 17`.
- Cost: a 5 s clip (121 frames) takes about 15–18 min on one GPU. Plan batches
  accordingly (two clips per ~17 min).
- The model doesn't render text reliably (signs, plaques, calligraphy). Add
  lettering in post.
- Start images that aren't 16:9 get center-cropped to 960×544.

## Environment (don't upgrade casually)

- Conda env at `env/` (Python 3.11). Rebuild with `scripts/setup_env.sh`;
  `requirements.lock.txt` is the known-good set.
- It deliberately differs from SkyReels-V2's requirements:
  - torch 2.8 cu128, because upstream's 2.5.1 has no Blackwell (sm_120) kernels.
  - Prebuilt flash-attn 2.8.3. It's required: `transformer.py` calls FA2 directly.
  - diffusers 0.33.1, to match transformers 4.49.
  - opencv-python-headless, because there's no libGL.
  - decord and moviepy 1.0.3, which are imported but not listed upstream.
  - conda gcc/gxx inside `env/`, because the machine has no C compiler and
    `torch.compile` needs one. `run_clip.sh` puts them on PATH.
- Don't `pip install -U` into `env/` or change these pins without testing: other
  people's queued jobs use the same env.

## Layout

```
video_gen/
├── CLAUDE.md, PLAN.md      # this file; setup plan and decisions
├── scripts/                # sbatch_clip.sh, submit_jobs.sh, run_clip.sh, run_df.sh, setup_env.sh
├── prompts/                # prompt text files (one per clip)
├── SkyReels-V2/            # upstream clone (gitignored)
├── env/  models/  outputs/  logs/   # gitignored
└── projects/               # per-project plans, frames, job lists (gitignored)
```

This repo (`github.com/donglaiw/video_gen`) is **public**. Keep project
material (story frames, personal prompts, outputs) in gitignored folders, and
commit only generic scripts and docs.
