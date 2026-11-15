#!/usr/bin/env python3
"""Render the ~85-second PEIRA promotional video (1920x1080, 30 fps).

Install requirements.txt, then run: python3 video-production/render.py
`--preview` writes one still per scene plus storyboard.jpg without encoding.
Default paths resolve relative to this repository, independently of cwd.
"""
import argparse, json, math, pathlib, shutil, subprocess, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

P = argparse.ArgumentParser(description=__doc__)
P.add_argument('--repo', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent)
P.add_argument('--out', type=pathlib.Path, help='Output directory; defaults to video-production/output.')
P.add_argument('--toy-data', type=pathlib.Path,
               default=pathlib.Path(__file__).resolve().parent / 'data/toy_runs.json',
               help='Toy-experiment export (export.py). A "data pending" placeholder is drawn if absent.')
P.add_argument('--toy-scale', type=float, help='Initialization scale to show; defaults to the smallest one.')
P.add_argument('--cifar-data', type=pathlib.Path,
               default=pathlib.Path(__file__).resolve().parent / 'data/cifar_dynamics.json',
               help='Optional per-epoch CIFAR-10 dynamics {epochs, spectrum, alignment}. '
                    'Falls back to the paper figure assets/img/cifar10_dynamics.png.')
P.add_argument('--preview', action='store_true', help='Render a storyboard without the full video.')
P.add_argument('--jobs', type=int, default=8, help='Scenes rendered in parallel.')
A = P.parse_args()
ROOT = A.repo.expanduser().resolve()
PRODUCTION = ROOT / 'video-production'
OUT = (A.out or PRODUCTION / 'output').expanduser().resolve()
FONTS = PRODUCTION / 'fonts'
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30

# Website palette (styles.css): text, muted, accent, accent-soft, border.
INK = '#1a1a1a'; MUTED = '#656565'; ACCENT = '#285a79'; SOFT = '#edf3f7'; BORDER = '#e6e6e6'
BG = '#fbfbfa'; WARM = '#b5603a'; WARM_SOFT = '#f7ece5'; GRID = '#ececec'; FAINT = '#c9cfd3'

_fonts = {}
def font(size, weight='regular'):
    key = (size, weight)
    if key not in _fonts:
        name = {'regular': 'Inter-Regular', 'medium': 'Inter-Medium', 'semibold': 'Inter-SemiBold',
                'bold': 'Inter-Bold', 'italic': 'Inter-Italic'}[weight]
        _fonts[key] = ImageFont.truetype(str(FONTS / f'{name}.ttf'), size)
    return _fonts[key]

def tx(d, xy, s, size=34, color=INK, weight='regular', anchor=None):
    d.text(xy, s, font=font(size, weight), fill=color, anchor=anchor)

def tlen(s, size, weight='regular'):
    return font(size, weight).getlength(s)

def ease(t):
    return 1 - (1 - max(0, min(1, t))) ** 3

def smooth(t):
    t = max(0, min(1, t)); return t * t * (3 - 2 * t)

def appear(im, t, t0, draw, dur=.5, rise=16):
    """Fade an element in from t0 while it rises into place."""
    a = ease((t - t0) / dur)
    if a <= 0:
        return im
    layer = im.copy(); draw(ImageDraw.Draw(layer), layer, round(rise * (1 - a)))
    return layer if a >= 1 else Image.blend(im, layer, a)

def arrow(d, x0, y0, x1, y1, col=INK, w=3, p=1.0, head=13):
    """Arrow from (x0, y0) toward (x1, y1), drawn to fraction p of its length."""
    if p <= 0:
        return
    x1, y1 = x0 + (x1 - x0) * p, y0 + (y1 - y0) * p
    ang = math.atan2(y1 - y0, x1 - x0)
    bx, by = x1 - head * .8 * math.cos(ang), y1 - head * .8 * math.sin(ang)
    d.line((x0, y0, bx, by), fill=col, width=w)
    pts = [(x1, y1)] + [(x1 - head * math.cos(ang + s * .45), y1 - head * math.sin(ang + s * .45)) for s in (1, -1)]
    d.polygon(pts, fill=col)

def dashed(d, x0, y0, x1, y1, col, w=2, dash=12, gap=9):
    L = math.hypot(x1 - x0, y1 - y0); n = int(L // (dash + gap)) + 1
    for i in range(n):
        a, b = i * (dash + gap) / L, min(1, (i * (dash + gap) + dash) / L)
        d.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), fill=col, width=w)

def box(d, xyxy, fill=SOFT, outline=ACCENT, w=2, r=14):
    d.rounded_rectangle(xyxy, radius=r, fill=fill, outline=outline, width=w)

CHAPTERS = {'question': '01 / The question', 'idea': '02 / The idea',
            'guarantee': '03 / The guarantee', 'lambda': '04 / The role of λ', 'cifar': '05 / Real images',
            'results': '06 / Results', 'ending': 'Explore the project'}
TITLES = {'question': 'Self-distillation works. But what does it optimize?',
          'idea': 'Align views through an optimal ridge regressor',
          'guarantee': 'Collapse becomes unstable',
          'lambda': 'λ selects how many directions to keep',
          'cifar': 'The same alignment on real images (CIFAR-10)',
          'results': 'Competitive linear-probe accuracy'}
SPECS = [('question', 10), ('idea', 14), ('guarantee', 15), ('lambda', 10),
         ('cifar', 10), ('results', 11), ('ending', 7)]
DURATION = sum(s for _, s in SPECS)
STARTS = {n: sum(s for _, s in SPECS[:i]) for i, (n, _) in enumerate(SPECS)}

def base(name):
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
    if name != 'ending':
        tx(d, (96, 47), 'PEIRA', 30, INK, 'bold')
        tx(d, (1824, 54), CHAPTERS[name].upper().replace('Λ', 'λ'), 21, MUTED, 'medium', anchor='ra')
        d.line((96, 100, 1824, 100), fill=BORDER, width=2)
        tx(d, (96, 150), TITLES[name], 54, INK, 'semibold')
    return im

def footnote(d, s, y=1022):
    tx(d, (96, y), s, 22, MUTED)

def footer(im, t):
    ImageDraw.Draw(im).rectangle((0, 1075, round(W * t / DURATION), 1079), fill=ACCENT)

# ---------------------------------------------------------------- data
def load_toy():
    if not A.toy_data.is_file():
        return None
    data = json.loads(A.toy_data.read_text())
    runs = data['runs']
    scales = sorted({r['init_scale'] for r in runs.values()})
    scale = A.toy_scale if A.toy_scale is not None else scales[0]
    pick = {}
    for r in runs.values():
        if math.isclose(r['init_scale'], scale, rel_tol=1e-6):
            pick[r['method']] = r
    if set(pick) != {'peira', 'self_distillation'}:
        raise SystemExit(f'No paired runs at init scale {scale} in {A.toy_data}')
    return {'scale': scale, 'meta': data['meta'], **pick}

def load_cifar():
    if not A.cifar_data.is_file():
        return None
    data = json.loads(A.cifar_data.read_text())
    return {k: np.asarray(data[k], dtype=float) for k in ('epochs', 'spectrum', 'alignment')}

TOY = load_toy()
CIFAR = load_cifar()
_figs = {}
def figure(path, size=None, crop=None):
    key = (str(path), size, crop)
    if key not in _figs:
        img = Image.open(path).convert('RGB')
        if crop:
            img = img.crop(crop)
        if size:
            img = img.resize(size, Image.Resampling.LANCZOS)
        _figs[key] = img
    return _figs[key]

# ---------------------------------------------------------------- plotting
class Axes:
    """Minimal linear/log plot frame. box = (x0, y0, x1, y1) in pixels."""
    def __init__(self, d, box, xlim, ylim, logx=False, logy=False):
        self.d, self.box, self.xlim, self.ylim, self.logx, self.logy = d, box, xlim, ylim, logx, logy
    def _n(self, v, lim, log):
        if log:
            v, lim = math.log10(max(v, 1e-300)), (math.log10(lim[0]), math.log10(lim[1]))
        return (v - lim[0]) / (lim[1] - lim[0])
    def px(self, x, y):
        x0, y0, x1, y1 = self.box
        u = min(1.02, max(-.02, self._n(x, self.xlim, self.logx)))
        v = min(1.02, max(-.02, self._n(y, self.ylim, self.logy)))
        return x0 + u * (x1 - x0), y1 - v * (y1 - y0)
    def frame(self, xticks, yticks, xlabel='', ylabel='', fmt_x=str, fmt_y=str):
        d = self.d; x0, y0, x1, y1 = self.box
        for v in yticks:
            _, y = self.px(self.xlim[0], v); d.line((x0, y, x1, y), fill=GRID, width=1)
            tx(d, (x0 - 12, y), fmt_y(v), 19, MUTED, anchor='rm')
        for v in xticks:
            x, _ = self.px(v, self.ylim[0]); tx(d, (x, y1 + 10), fmt_x(v), 19, MUTED, anchor='ma')
        d.line((x0, y1, x1, y1), fill=FAINT, width=2); d.line((x0, y0, x0, y1), fill=FAINT, width=2)
        if xlabel:
            tx(d, ((x0 + x1) / 2, y1 + 40), xlabel, 20, MUTED, anchor='ma')
        if ylabel:
            tx(d, (x0, y0 - 30), ylabel, 20, MUTED)
    def line(self, xs, ys, col, w=4, frac=1.0):
        n = len(xs); m = frac * (n - 1)
        if m <= 0:
            return None
        k = int(m); pts = [self.px(x, y) for x, y in zip(xs[:k + 1], ys[:k + 1])]
        if k < n - 1:
            a = m - k; (xa, ya), (xb, yb) = self.px(xs[k], ys[k]), self.px(xs[k + 1], ys[k + 1])
            pts.append((xa + a * (xb - xa), ya + a * (yb - ya)))
        self.d.line(pts, fill=col, width=w, joint='curve')
        return pts[-1]

VIRIDIS = ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725']
def viridis(u):
    u = max(0, min(1, u)) * (len(VIRIDIS) - 1); i = min(int(u), len(VIRIDIS) - 2); a = u - i
    c0, c1 = (np.array(Image.new('RGB', (1, 1), c).getpixel((0, 0))) for c in VIRIDIS[i:i + 2])
    return tuple(int(v) for v in c0 + a * (c1 - c0))

def mix(c, a):
    """Blend colour c toward white by 1 - a."""
    r = np.array(Image.new('RGB', (1, 1), c).getpixel((0, 0)), float)
    return tuple(int(v) for v in 255 - a * (255 - r))

# ---------------------------------------------------------------- scenes
def scene_question(t):
    im = base('question'); d = ImageDraw.Draw(im)
    tx(d, (98, 232), 'BYOL, SimSiam and DINO train a student to predict a teacher.', 30, MUTED)
    # Schematic student-teacher pair.
    rows = [(420, 'x', 'Student', 'Predictor', 'Prediction', ACCENT), (690, 'y', 'Teacher', None, 'Target', WARM)]
    def draw_row(i):
        y, v, enc, pred, outl, col = rows[i]
        def f(d, L, o):
            yy = y + o
            tx(d, (150, yy), v, 44, INK, 'italic', anchor='mm')
            arrow(d, 180, yy, 250, yy, INK)
            box(d, (255, yy - 50, 475, yy + 50), SOFT if i == 0 else WARM_SOFT, col)
            tx(d, (365, yy), enc, 30, INK, 'semibold', anchor='mm')
            if pred:
                arrow(d, 480, yy, 545, yy, INK); box(d, (550, yy - 50, 770, yy + 50), SOFT, col)
                tx(d, (660, yy), pred, 30, INK, 'semibold', anchor='mm')
            else:
                tx(d, (512, yy + 72), 'EMA or stop-gradient', 22, WARM, 'medium', anchor='ma')
                d.line((480, yy, 770, yy), fill=INK, width=3)
            arrow(d, 775, yy, 840, yy, INK)
            tx(d, (850, yy), outl, 30, col, 'semibold', anchor='lm')
        return f
    im = appear(im, t, .4, draw_row(0)); im = appear(im, t, 1.1, draw_row(1))
    def match(d, L, o):
        dashed(d, 915, 450, 915, 655, MUTED, 3)
        tx(d, (935, 555), 'match', 24, MUTED, 'medium', anchor='lm')
    im = appear(im, t, 1.9, match, rise=0)
    pts = [('They work well in practice.', 3.0), ('But they minimize no well-defined objective.', 4.6),
           ('And representations can collapse.', 6.2)]
    for i, (s, t0) in enumerate(pts):
        im = appear(im, t, t0, lambda d, L, o, s=s, i=i: (
            d.ellipse((1150, 352 + i * 78 + o, 1164, 366 + i * 78 + o), fill=WARM if i else ACCENT),
            tx(d, (1186, 340 + i * 78 + o), s, 30, INK, 'medium')))
    # Schematic collapse: points contract toward a single point.
    d = ImageDraw.Draw(im)
    if t > 6.6:
        a = smooth((t - 7.0) / 2.2)
        rng = np.random.default_rng(3); P0 = rng.normal(size=(60, 2)) * [150, 75]
        cx, cy = 1490, 760
        fade = ease((t - 6.6) / .5)
        d.rounded_rectangle((1150, 610, 1824, 920), radius=16, outline=mix(BORDER, fade), width=2)
        for (px_, py_), c in zip(P0 * (1 - .97 * a), range(60)):
            col = mix(ACCENT if c % 2 else WARM, fade)
            d.ellipse((cx + px_ - 6, cy + py_ - 6, cx + px_ + 6, cy + py_ + 6), fill=col)
        tx(d, (1170, 628), 'Schematic: collapse maps every input to one point', 21, mix(MUTED, fade))
    return im

def scene_idea(t):
    im = base('idea'); d = ImageDraw.Draw(im)
    tx(d, (98, 232), 'Predict one view from the other with a linear regressor, solved in closed form.', 30, MUTED)
    YU, YV = 400, 640
    def enc(y, v, name, out, t0):
        def f(d, L, o):
            yy = y + o
            tx(d, (130, yy), v, 46, INK, 'italic', anchor='mm')
            arrow(d, 160, yy, 230, yy, INK, p=1)
            box(d, (235, yy - 48, 395, yy + 48)); tx(d, (315, yy), name, 44, INK, 'italic', anchor='mm')
            arrow(d, 400, yy, 470, yy, INK); tx(d, (500, yy), out, 40, INK, 'italic', anchor='mm')
        return appear(im_ref[0], t, t0, f)
    im_ref = [im]
    im_ref[0] = enc(YU, 'x', 'U', 'u', .3); im_ref[0] = enc(YV, 'y', 'V', 'v', .8)
    im = im_ref[0]; d = ImageDraw.Draw(im)
    tx(d, (98, 760), 'two views of', 22, mix(MUTED, ease((t - .3) / .5)))
    tx(d, (98, 788), 'one image', 22, mix(MUTED, ease((t - .3) / .5)))
    # Statistics boxes.
    SB, NB = (700, 300, 1160, 420), (700, 620, 1160, 740)
    p = smooth((t - 2.6) / .9); d = ImageDraw.Draw(im)
    for y0 in (YU, YV):
        for b in (SB, NB):
            arrow(d, 530, y0, b[0] - 6, (b[1] + b[3]) / 2, FAINT if p < 1 else MUTED, 2, p=p, head=11)
    im = appear(im, t, 3.2, lambda d, L, o: (box(d, (SB[0], SB[1] + o, SB[2], SB[3] + o)),
        tx(d, (730, 333 + o), 'Σ', 46, ACCENT, 'semibold', anchor='lm'),
        tx(d, (790, 316 + o), 'Shared signal', 28, INK, 'semibold'),
        tx(d, (790, 354 + o), 'covariance across views', 23, MUTED)))
    im = appear(im, t, 3.8, lambda d, L, o: (box(d, (NB[0], NB[1] + o, NB[2], NB[3] + o), '#f3f3f1', FAINT),
        tx(d, (730, 653 + o), 'N', 46, MUTED, 'semibold', anchor='lm'),
        tx(d, (790, 636 + o), 'Within-view variability', 28, INK, 'semibold'),
        tx(d, (790, 674 + o), 'covariance inside each view', 23, MUTED)))
    # Ridge regressor.
    RB = (1300, 400, 1824, 640)
    d = ImageDraw.Draw(im); p = smooth((t - 5.4) / .8)
    arrow(d, SB[2] + 6, 360, RB[0] - 6, 480, MUTED, 3, p=p); arrow(d, NB[2] + 6, 680, RB[0] - 6, 560, MUTED, 3, p=p)
    def ridge(d, L, o):
        box(d, (RB[0], RB[1] + o, RB[2], RB[3] + o), SOFT, ACCENT, 3)
        tx(d, (1562, 432 + o), 'Optimal ridge regressor', 30, INK, 'semibold', anchor='ma')
        s = 'P = Σ(N + λI)'; f = font(50, 'medium'); x = 1562 - (f.getlength(s) + 40) / 2
        d.text((x, 500 + o), s, font=f, fill=ACCENT); d.text((x + f.getlength(s) + 4, 490 + o), '−1', font=font(28, 'medium'), fill=ACCENT)
        tx(d, (1562, 584 + o), 'signal-to-noise ratio between views', 22, MUTED, anchor='ma')
    im = appear(im, t, 6.0, ridge)
    # Objective.
    def loss(d, L, o):
        d.line((RB[0] + 262, RB[3] + 6, RB[0] + 262, 800), fill=ACCENT, width=3)
        box(d, (700, 805 + o, 1824, 950 + o), '#ffffff', ACCENT, 3)
        tx(d, (740, 830 + o), 'PEIRA maximizes the trace of P', 32, INK, 'semibold')
        tx(d, (740, 885 + o), 'Tr(P) sums the signal shared across views, one direction at a time.', 26, MUTED)
        tx(d, (1784, 834 + o), '+ a norm penalty on U, V', 24, MUTED, anchor='ra')
    im = appear(im, t, 8.6, loss)
    d = ImageDraw.Draw(im)
    footnote(d, 'Simplified diagram. The paper also gives a stable training algorithm with EMA statistics and an auxiliary loss.')
    return im

def scene_guarantee(t):
    im = base('guarantee'); d = ImageDraw.Draw(im)
    tx(d, (98, 232), 'Toy experiment of the paper: both methods start from a tiny initialization.', 30, MUTED)
    cols = [(96, 'Self-distillation', 'self_distillation', WARM), (1000, 'PEIRA', 'peira', ACCENT)]
    K = 6
    reveal = smooth((t - 1.4) / 8.8)
    for x0, label, key, col in cols:
        tx(d, (x0, 300), label, 36, col, 'semibold')
        b = (x0 + 100, 420, x0 + 790, 840)
        if TOY is None:
            ax = Axes(d, b, (100, 1e5), (0, 1), logx=True)
            ax.frame([], [0, .5, 1], ylabel='Spectral ratio (learned / target)', fmt_y=lambda v: f'{v:g}')
            d.rounded_rectangle((b[0] + 180, 600, b[2] - 180, 660), radius=12, fill='#fff4e0', outline='#d9a441', width=2)
            tx(d, ((b[0] + b[2]) / 2, 630), 'DATA PENDING', 26, '#9a6b10', 'bold', anchor='mm')
            continue
        r = TOY[key]; steps = np.asarray(r['step'], float) + TOY['meta']['log_interval']
        Y = np.asarray(r['spectrum_ratio'], float); target = np.asarray(r['target_ratio'], float)[-1]
        xl = (steps[0], steps[-1])
        xt = [10 ** e for e in range(int(math.ceil(math.log10(xl[0]))), int(math.log10(xl[1])) + 1)]
        sup = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
        ax = Axes(d, b, xl, (0, 1.08), logx=True)
        ax.frame(xt, [0, .5, 1], xlabel='training step', ylabel='Spectral ratio (learned / target)',
                 fmt_x=lambda v: '10' + str(int(round(math.log10(v)))).translate(sup), fmt_y=lambda v: f'{v:g}')
        for i in reversed(range(K)):
            c = mix(col, 1 - .14 * i) if target[i] > 0 else FAINT
            ax.line(steps, Y[:, i], c, 5 if target[i] > 0 else 3, reveal)
        k = int(reveal * (len(steps) - 1))
        reached = int(((Y[k, :K] > .9) & (target[:K] > 0)).sum())
        n_target = int((target > 0).sum())
        tx(d, (b[0], 915), f'Target directions reached: {reached} of {n_target}', 28, INK, 'semibold')
        if reveal >= 1:
            verdict = 'Stays collapsed' if Y[-1, 0] < .05 else f'Recovers all {n_target}' if reached == n_target else 'Partial'
            im = appear(im, t, 10.4, lambda d, L, o, v=verdict, c=col, x=x0: (
                d.rounded_rectangle((x + 500, 290 + o, x + 790, 342 + o), radius=26, fill=c),
                tx(d, (x + 645, 316 + o), v, 26, 'white', 'semibold', anchor='mm')))
            d = ImageDraw.Draw(im)
    if TOY is None:
        footnote(d, 'Toy experiment export pending: anim_data.json not found. Panels will fill from real data.')
    else:
        footnote(d, f'Real runs (paper Fig. G.6 setup), init scale {TOY["scale"]:g}, seed 0. Top {K} directions; '
                    'coloured lines are the 4 target directions, grey lines should stay at 0.')
    return im

SQRT_C = [.92, .80, .66, .52, .40, .29, .19, .10]  # illustrative, not from the paper
def scene_lambda(t):
    im = base('lambda'); d = ImageDraw.Draw(im)
    tx(d, (98, 232), 'PEIRA keeps only directions whose canonical correlation clears λ.', 30, MUTED)
    lam = .05 + .80 * smooth((t - 1.2) / 7.4)
    panels = [(96, '√cᵢ  and the threshold λ'), (1000, 'Learned amplitude g(cᵢ, λ)')]
    n = len(SQRT_C); kept = sum(s > lam for s in SQRT_C)
    for pi, (x0, label) in enumerate(panels):
        tx(d, (x0, 300), label, 32, INK, 'semibold')
        b = (x0 + 70, 380, x0 + 800, 820); ax = Axes(d, b, (0, n), (0, 1))
        ax.frame([], [0, .5, 1], fmt_y=lambda v: f'{v:g}')
        bw = (b[2] - b[0]) / n
        for i, s in enumerate(SQRT_C):
            g = math.sqrt(max(s - lam, 0))
            v = s if pi == 0 else g
            xa = b[0] + i * bw + bw * .18; xb = b[0] + (i + 1) * bw - bw * .18
            _, yt = ax.px(0, v)
            col = (ACCENT if s > lam else FAINT) if pi == 0 else ACCENT
            if v > 0:
                d.rectangle((xa, yt, xb, b[3]), fill=col)
            tx(d, ((xa + xb) / 2, b[3] + 10), f'{i + 1}', 20, MUTED, anchor='ma')
        tx(d, ((b[0] + b[2]) / 2, b[3] + 42), 'direction i', 20, MUTED, anchor='ma')
        if pi == 0:
            _, yl = ax.px(0, lam)
            d.line((b[0], yl, b[2], yl), fill=WARM, width=4)
            tx(d, (b[2] + 8, yl), 'λ', 32, WARM, 'semibold', anchor='lm')
    # Formula and dial readout.
    s = 'g(c, λ) = max(√c − λ, 0)'; f = font(36, 'medium')
    tx(d, (1000, 915), s, 36, ACCENT, 'medium'); tx(d, (1000 + f.getlength(s) + 4, 907), '1/2', 22, ACCENT, 'medium')
    tx(d, (96, 915), f'λ = {lam:.2f}', 36, WARM, 'semibold')
    tx(d, (330, 920), f'directions kept: {kept} of {n}', 30, INK, 'medium')
    # Dial track.
    d.rounded_rectangle((96, 980, 800, 988), radius=4, fill=BORDER)
    xk = 96 + 704 * (lam - .05) / .80; d.ellipse((xk - 13, 971, xk + 13, 997), fill=WARM)
    footnote(d, 'Illustrative spectrum. The filter g is the exact form from the paper; larger λ keeps fewer directions.', 1022)
    return im

def scene_cifar(t):
    im = base('cifar'); d = ImageDraw.Draw(im)
    tx(d, (98, 232), 'One PEIRA training run on CIFAR-10: signal and noise align their eigenvectors.', 30, MUTED)
    if CIFAR is not None:
        ep, S, Al = CIFAR['epochs'], CIFAR['spectrum'], CIFAR['alignment']
        k = smooth((t - .8) / 7.5) * len(ep)
        for x0, Y, yl, logy in ((96, Al, 'Alignment αᵢ', False), (1000, S, 'Spectrum of Σ', True)):
            b = (x0 + 110, 340, x0 + 820, 830); n = Y.shape[1]
            ylim = (max(Y[Y > 0].min(), 1e-12), Y.max() * 1.5) if logy else (0, 1.02)
            ax = Axes(d, b, (1, n), ylim, logy=logy)
            yt = [10.0 ** e for e in range(int(math.ceil(math.log10(ylim[0]))), int(math.log10(ylim[1])) + 1, 2)] if logy else [0, .5, 1]
            ax.frame([1, n], yt, xlabel='eigen-direction index', ylabel=yl,
                     fmt_y=(lambda v: f'1e{int(round(math.log10(v)))}') if logy else (lambda v: f'{v:g}'))
            for e in range(min(int(k) + 1, len(ep))):
                a = min(1, k - e)
                if a > 0:
                    ax.line(np.arange(1, n + 1), Y[e], mix(viridis(e / max(1, len(ep) - 1)), a), 3)
        e = min(int(k), len(ep) - 1)
        tx(d, (1824, 300), f'epoch {int(ep[e])}', 30, INK, 'semibold', anchor='ra')
        footnote(d, 'Per-epoch curves from the run behind the paper figure; colour goes from early (purple) to late (yellow) epochs.')
        return im
    path = ROOT / 'assets/img/cifar10_dynamics.png'
    src = figure(path); sw, sh = src.size
    cuts = [0, round(sw * 1089 / 3296), round(sw * 2194 / 3296), sw]
    fw = 1728; fh = round(sh * fw / sw); y0 = 330
    full = figure(path, (fw, fh))
    caps = [('Alignment rises toward 1', 'Top eigenvectors of Σ become eigenvectors of N.'),
            ('More modes emerge', 'The spectrum of Σ gains significant directions.'),
            ('Objective tracks accuracy', 'Validation top-1 rises with −E (PEIRA).')]
    for i in range(3):
        t0 = .5 + 3 * i
        xa, xb = round(cuts[i] * fw / sw), round(cuts[i + 1] * fw / sw)
        def draw(d, L, o, i=i, xa=xa, xb=xb):
            L.paste(full.crop((xa, 0, xb, fh)), (96 + xa, y0 + o))
            tx(d, (96 + xa + 20, y0 + fh + 40 + o), caps[i][0], 28, INK, 'semibold')
            tx(d, (96 + xa + 20, y0 + fh + 82 + o), caps[i][1], 22, MUTED)
        im = appear(im, t, t0, draw, dur=.7)
    d = ImageDraw.Draw(im)
    footnote(d, 'Figure from the paper (one curve per 100 epochs). x axis: singular value index; right: accuracy and objective per epoch.')
    return im

RESULTS = [  # Table 1 of the paper (tab:in1k): mean ± sample std over 3 seeds.
    ('ImageNet-1K', 'ResNet-50, 100 epochs', (64, 70),
     [('PEIRA (k=1024)', 69.17, .06), ('VICReg', 68.81, .09), ('SIGReg', 66.26, .28)]),
    ('CIFAR-10', 'ResNet-18, 1000 epochs', (88, 93),
     [('PEIRA (k=1024)', 91.68, .18), ('VICReg', 90.92, .14), ('SIGReg', 92.34, .21)])]
def scene_results(t):
    im = base('results'); d = ImageDraw.Draw(im)
    tx(d, (98, 232), 'Linear-probe top-1 accuracy (%), controlled comparison from Table 1.', 30, MUTED)
    for gi, (name, sub, lim, rows) in enumerate(RESULTS):
        x0 = 96 + gi * 904
        tx(d, (x0, 310), name, 38, INK, 'semibold'); tx(d, (x0, 362), sub, 24, MUTED)
        bx0, bx1 = x0 + 250, x0 + 620
        best = max(v for _, v, _ in rows)
        for ri, (m, v, s) in enumerate(rows):
            y = 440 + ri * 120
            g = smooth((t - .8 - gi * 1.2 - ri * .25) / 1.4)
            col = ACCENT if m.startswith('PEIRA') else '#9aa3a8'
            tx(d, (x0, y + 22), m, 28, INK if m.startswith('PEIRA') else MUTED, 'semibold' if m.startswith('PEIRA') else 'medium', anchor='lm')
            d.rectangle((bx0, y, bx1, y + 44), fill='#f0f1ef')
            w = (v - lim[0]) / (lim[1] - lim[0]) * (bx1 - bx0) * g
            if w > 0:
                d.rectangle((bx0, y, bx0 + w, y + 44), fill=col)
            if g > .6:
                a = ease((g - .6) / .4)
                tx(d, (bx1 + 20, y + 22), f'{v:.2f}', 32, mix(INK, a), 'bold' if v == best else 'regular', anchor='lm')
                tx(d, (bx1 + 120, y + 26), f'± {s:.2f}', 20, mix(MUTED, a), anchor='lm')
        ax_y = 440 + 3 * 120 - 50
        for v in range(lim[0], lim[1] + 1, 2 if lim[1] - lim[0] > 5 else 1):
            xx = bx0 + (v - lim[0]) / (lim[1] - lim[0]) * (bx1 - bx0)
            d.line((xx, ax_y, xx, ax_y + 8), fill=FAINT, width=2); tx(d, (xx, ax_y + 14), f'{v}', 19, MUTED, anchor='ma')
        tx(d, (bx0, ax_y + 46), f'axis starts at {lim[0]}%', 19, MUTED)
    im = appear(im, t, 5.5, lambda d, L, o: tx(d, (96, 880 + o),
        'Best on ImageNet-1K; on CIFAR-10, SIGReg leads and PEIRA beats VICReg.', 30, INK, 'semibold'))
    d = ImageDraw.Draw(im)
    footnote(d, 'Mean ± std over 3 seeds, same augmentations, optimizer and probe. SIGReg uses a narrower projector. Source: Table 1.')
    return im

def scene_ending(t):
    im = base('ending'); d = ImageDraw.Draw(im)
    im = appear(im, t, .2, lambda d, L, o: (tx(d, (960, 170 + o), 'PEIRA', 96, ACCENT, 'bold', anchor='ma'),
        tx(d, (960, 300 + o), 'Learning Predictive Encoders through Inter-View Regressor Alignment', 34, MUTED, anchor='ma')))
    def pip(d, L, o):
        s = 'pip install peira-loss'; wd = tlen(s, 46, 'medium') + 90
        d.rounded_rectangle((960 - wd / 2, 400 + o, 960 + wd / 2, 492 + o), radius=18, fill='#1f2a30')
        tx(d, (960 - wd / 2 + 40, 446 + o), '$', 46, '#8fb6cf', 'medium', anchor='lm')
        tx(d, (960 - wd / 2 + 80, 446 + o), s, 46, '#ffffff', 'medium', anchor='lm')
    im = appear(im, t, .7, pip)
    links = [('Paper', 'arXiv 2605.17671'), ('Code', 'github.com/Basile-Terv/PEIRA'),
             ('Project page', 'basile-terv.github.io/peira-website')]
    for i, (k, v) in enumerate(links):
        im = appear(im, t, 1.2 + .3 * i, lambda d, L, o, i=i, k=k, v=v: (
            tx(d, (900, 560 + i * 62 + o), k, 30, MUTED, 'medium', anchor='ra'),
            tx(d, (930, 560 + i * 62 + o), v, 30, INK, 'semibold')))
    im = appear(im, t, 2.4, lambda d, L, o: (
        tx(d, (960, 830 + o), 'Michael Arbel*  ·  Basile Terver*  ·  Jean Ponce', 32, INK, anchor='ma'),
        tx(d, (960, 884 + o), '*Equal contribution  ·  NeurIPS 2026', 24, MUTED, anchor='ma')))
    return im

SCENES = {'question': scene_question, 'idea': scene_idea, 'guarantee': scene_guarantee,
          'lambda': scene_lambda, 'cifar': scene_cifar, 'results': scene_results, 'ending': scene_ending}

def soundtrack():
    """Calm synthesized pad and plucks (adapted from the H-JEPA renderer)."""
    sr = 48000; dur = DURATION; n = sr * dur; aud = np.zeros((n, 2), np.float32)
    def add(sig, start, pan=0):
        i = int(start * sr); end = min(n, i + len(sig)); sig = sig[:end - i]
        if i < n:
            aud[i:end, 0] += sig * np.sqrt((1 - pan) / 2); aud[i:end, 1] += sig * np.sqrt((1 + pan) / 2)
    def tone(hz, length, kind='pad'):
        tt = np.arange(int(length * sr)) / sr
        if kind == 'pad':
            env = np.minimum(tt / 1.6, 1) * np.minimum((length - tt) / 2.2, 1)
            return .055 * env * (np.sin(2 * np.pi * hz * tt) + .28 * np.sin(2 * np.pi * hz * 2.003 * tt))
        env = (1 - np.exp(-tt * 70)) * np.exp(-tt * 2.5)
        return .024 * env * (np.sin(2 * np.pi * hz * tt) + .23 * np.sin(2 * np.pi * hz * 2 * tt))
    chords = [[130.813, 196, 246.942, 329.628], [110, 164.814, 220, 261.626],
              [87.307, 130.813, 174.614, 220], [98, 146.832, 196, 246.942]]
    for i, start in enumerate(np.arange(0, dur, 7)):
        for j, hz in enumerate(chords[i % 4]):
            add(tone(hz, 9), start, (j - 1.5) / 4)
    for k, start in enumerate(np.arange(0, dur, .75)):
        chord = chords[int(start // 7) % 4]
        add(tone(chord[[0, 2, 1, 3, 2, 1, 3, 1][k % 8]] * 2, 2, 'pluck'), start, -.25 if k % 2 else .25)
    fade = np.minimum(np.arange(n) / sr / 3, 1) * np.minimum((dur - np.arange(n) / sr) / 4, 1)
    aud *= fade[:, None]; aud = np.tanh(aud) * .6
    with wave.open(str(OUT / 'soundtrack.wav'), 'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(sr); f.writeframes((aud * 32767).astype('<i2').tobytes())

def frame(name, t):
    im = SCENES[name](t)
    footer(im, STARTS[name] + t)
    return im

def render_scene(spec):
    name, dur = spec
    target = OUT / f'{name}.mp4'
    with open(OUT / f'{name}.log', 'w') as log:
        enc = subprocess.Popen([FF, '-y', '-v', 'warning', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                                '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                                '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)],
                               stdin=subprocess.PIPE, stderr=log)
        blank = base(name)
        for f in range(dur * FPS):
            t = f / FPS; im = frame(name, t)
            if t < .23:
                im = Image.blend(blank, im, ease(t / .23))
            enc.stdin.write(im.tobytes())
        enc.stdin.close(); code = enc.wait()
    if code:
        raise RuntimeError('Encoding failed: ' + name)
    print('Rendered', name, dur, 's', flush=True)

PREVIEW_T = {'question': 8.5, 'idea': 12.5, 'guarantee': 14, 'lambda': 5.5, 'cifar': 9.5,
             'results': 9, 'ending': 5}

if __name__ == '__main__':
    missing = [p for p in [FONTS / 'Inter-Regular.ttf', PRODUCTION / 'captions.srt'] if not p.is_file()]
    if CIFAR is None:
        missing += [p for p in [ROOT / 'assets/img/cifar10_dynamics.png'] if not p.is_file()]
    if missing:
        P.error('Missing inputs: ' + ', '.join(map(str, missing)))
    for name, title in TITLES.items():
        if tlen(title, 54, 'semibold') > W - 192:
            P.error('Title too wide: ' + title)
    OUT.mkdir(parents=True, exist_ok=True)
    print('toy data:', 'PENDING' if TOY is None else f'{A.toy_data} (scale {TOY["scale"]:g})',
          '| cifar data:', 'paper figure' if CIFAR is None else A.cifar_data, flush=True)
    if A.preview:
        sheet = Image.new('RGB', (960 * 2, 540 * 4), 'white')
        for i, (name, dur) in enumerate(SPECS):
            im = frame(name, PREVIEW_T[name]); im.save(OUT / f'preview_{name}.jpg', quality=93)
            sheet.paste(im.resize((960, 540), Image.Resampling.LANCZOS), ((i % 2) * 960, (i // 2) * 540))
        sheet.save(OUT / 'storyboard.jpg', quality=95); print('Preview complete', OUT / 'storyboard.jpg', flush=True)
    else:
        with Pool(min(A.jobs, len(SPECS))) as pool:
            pool.map(render_scene, SPECS)
        soundtrack()
        (OUT / 'concat.txt').write_text('\n'.join(f"file '{name}.mp4'" for name, _ in SPECS))
        subprocess.run([FF, '-y', '-v', 'warning', '-f', 'concat', '-safe', '0', '-i', str(OUT / 'concat.txt'),
                        '-i', str(OUT / 'soundtrack.wav'), '-c:v', 'copy', '-af', 'volume=6dB', '-c:a', 'aac',
                        '-b:a', '192k', '-t', str(DURATION), '-movflags', '+faststart',
                        '-metadata', 'title=PEIRA | Learning Predictive Encoders through Inter-View Regressor Alignment',
                        '-metadata', 'comment=Synthesized instrumental soundtrack.', str(OUT / 'peira_video.mp4')],
                       check=True)
        shutil.copyfile(PRODUCTION / 'captions.srt', OUT / 'peira_video.srt')
        print('FINAL', OUT / 'peira_video.mp4', flush=True)
