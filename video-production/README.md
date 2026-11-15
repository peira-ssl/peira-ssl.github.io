# PEIRA promotional video

Two renderers live here. Both write 1920 × 1080, 30 fps H.264 (yuv420p) + AAC to
`video-production/output/` (gitignored). The website does not load anything here.

- **`render_from_site.py` (current cut, ~95 s).** Captures the website's five step-by-step
  animations (`assets/anim/{question,idea,guarantee,lambda,cifar}.html?embed=1`) frame by
  frame in headless Chromium and frames them in the site's graphical chart (styles.css:
  background `#fbf9f6`, text `#1d1d1b`, muted `#5e5955`, brand `#e53516`, accent `#c42b10`,
  border `#e7e2dc`; Inria Serif / Inria Sans).
- **`render.py` (previous cut, ~77 s).** Every scene drawn with Pillow in the old palette
  (blue/rust, Inter). Unchanged and still runnable; its `soundtrack()`, `scene_results` and
  `scene_ending` were copied into `render_from_site.py` and recolored.

## Render (current cut)

Needs Pillow, numpy, imageio-ffmpeg and Playwright with Chromium
(`pip install -r requirements.txt playwright && playwright install chromium`).

```sh
python video-production/render_from_site.py --preview  # output/storyboard.jpg + preview_*.jpg
python video-production/render_from_site.py            # output/peira_video.mp4 (+ .srt)
```

The script serves the site itself on a random localhost port. Run the full render on a
compute node, not a login node. On the AMI cluster:

```sh
srun --partition=main --account=open_research --qos=normal --nodelist=slurm-cluster-amilabs-l40s-3 \
  --ntasks=1 --cpus-per-task=16 --mem=32G --time=00:45:00 \
  bash /home/basile.terver/shared/cc_scratch/peira_video/run_site_render.sh
```

### How the capture is deterministic

- `requestAnimationFrame` is replaced by a no-op before the page loads, so the page's own
  clock never advances.
- For each frame the script sets the page's global `elapsed = t` (with `playing = true`, so
  the controls read "Pause" and fades still run) and calls `render()`.
- CSS transitions and keyframe animations (step-tab highlight, `idea.html` flow/breathe) are
  paused via `document.getAnimations()` and seeked to the same clock.
- The mouse is parked at (0, 0); nothing is hovered, and the λ slider is only driven by the
  autoplay values.
- Each card is fitted into the slide (below the header) at ~1.5 device pixels per CSS pixel:
  the viewport width is chosen per animation so the card fills the available height.

Step captions are read from `#step-description` while capturing, and become the SRT cues
(one per step, shortened to whole sentences ≤ 120 characters). `captions.srt` and
`output/peira_video.srt` are rewritten on every full render; `output/timeline.json` records
each scene's start and duration.

## Timeline (current cut, 94.9 s)

Scenes overlap by a 0.3 s crossfade; a brand-color progress bar runs along the bottom.

| Start | Scene | Length |
| --- | --- | --- |
| 0:00.0 | Opening: PEIRA + full title | 3 s |
| 0:02.7 | 01 / The question (`question.html`, 4 steps) | 17 s |
| 0:19.4 | 02 / The idea (`idea.html`, 4 steps) | 16 s |
| 0:35.1 | 03 / The guarantee (`guarantee.html`, 4 steps) | 16 s |
| 0:50.8 | 04 / The role of λ (`lambda.html`, 4 steps) | 15 s |
| 1:05.5 | 05 / Real images (`cifar.html`, 3 steps) | 15 s |
| 1:20.2 | 06 / Results (Table 1) | 9 s |
| 1:28.9 | End card: links, pip install, authors | 6 s |

Animation lengths come from each page's `stageDurations`; change them there and re-render.

## Inputs (previous cut, `render.py`)

| Input | Scene | Notes |
| --- | --- | --- |
| `--toy-data` (default `data/toy_runs.json`) | 03 guarantee | Real toy runs (paper Fig. G.6 setup). `--toy-scale` picks the init scale (default: smallest). |
| `--cifar-data` (default `data/cifar_dynamics.json`, not yet available) | 05 CIFAR-10 | Falls back to `../assets/img/cifar10_dynamics.png`. |
| `RESULTS` | 06 results | Table 1 of the paper (controlled rows). |
| `SQRT_C` | 04 λ dial | Illustrative spectrum, labelled as such. |

`render.py --preview` writes a storyboard; `render.py` renders `output/peira_video.mp4` and
copies `captions.srt`, which the current cut now overwrites (its timestamps no longer match
`render.py`'s 0:00–1:17 timeline).

## Fonts

- `InriaSans-Regular.ttf`, `InriaSans-Bold.ttf`, `InriaSerif-Bold.ttf`: Inria Fonts
  (BlackFoundry), SIL Open Font License, `fonts/OFL-Inria.txt`. Inria Sans has no Greek
  glyphs, so the "λ" in the chapter label is drawn with the system DejaVu Sans Bold
  (falls back to "LAMBDA" if absent).
- `Inter-*.ttf`: Inter 4.1 (rsms/inter), SIL Open Font License, `fonts/OFL.txt`. Kept
  because `render.py` still uses them.
