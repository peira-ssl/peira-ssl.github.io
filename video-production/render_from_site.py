#!/usr/bin/env python3
"""Render the PEIRA promotional video from the website's step-by-step animations.

The five animations (assets/anim/*.html) are captured frame by frame with headless
Chromium: requestAnimationFrame is disabled, the page's `elapsed` clock is set for each
frame, and CSS transitions/animations are paused and seeked to the same clock, so every
frame is deterministic. Opening, results and end card are drawn with Pillow in the
website's palette (styles.css). Output: output/peira_video.mp4 (+ .srt, storyboard.jpg).

    python video-production/render_from_site.py --preview   # stills + storyboard only
    python video-production/render_from_site.py             # full render (compute node)

Needs Pillow, numpy, imageio-ffmpeg and playwright (with Chromium installed).
"""
import argparse, contextlib, functools, html, http.server, json, pathlib, re, shutil, subprocess, threading, wave
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE.parent
FONTS = HERE / 'fonts'
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
XFADE = .3  # crossfade between scenes, seconds

# Website chart (styles.css :root).
BG = '#fbf9f6'; SURFACE = '#ffffff'; INK = '#1d1d1b'; MUTED = '#5e5955'; BRAND = '#e53516'
ACCENT = '#c42b10'; SOFT = '#fcefe9'; BORDER = '#e7e2dc'; SLATE = '#3d5a73'
TRACK = '#f1ede8'; GREY_BAR = '#b8b0a8'; FAINT = '#cfc8c1'

ANIMS = ['question', 'idea', 'guarantee', 'lambda', 'cifar']
CHAPTERS = {'question': '01 / The question', 'idea': '02 / The idea', 'guarantee': '03 / The guarantee',
            'lambda': '04 / The role of λ', 'cifar': '05 / Real images', 'results': '06 / Results'}
CARD_BOX = (96, 124, 1824, 1058)  # area the animation card is fitted into (px)
MAX_VIEW_W, MIN_VIEW_W, TARGET_SCALE = 1152, 760, 1.5  # CSS viewport width range; px per CSS px
GREEK = pathlib.Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')

_fonts = {}
def font(size, weight='regular'):
    name = {'regular': 'InriaSans-Regular', 'bold': 'InriaSans-Bold', 'serif': 'InriaSerif-Bold'}[weight]
    if (size, name) not in _fonts:
        _fonts[size, name] = ImageFont.truetype(str(FONTS / f'{name}.ttf'), size)
    return _fonts[size, name]

def tx(d, xy, s, size=34, color=INK, weight='regular', anchor=None):
    d.text(xy, s, font=font(size, weight), fill=color, anchor=anchor)

def tlen(s, size, weight='regular'):
    return font(size, weight).getlength(s)

def ease(t):
    return 1 - (1 - max(0, min(1, t))) ** 3

def smooth(t):
    t = max(0, min(1, t)); return t * t * (3 - 2 * t)

def mix(c, a, bg=BG):
    rgb = lambda h: [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(round(y + (x - y) * a) for x, y in zip(rgb(c), rgb(bg)))

def appear(im, t, t0, draw, dur=.5, rise=16):
    """Fade an element in from t0 while it rises into place."""
    a = ease((t - t0) / dur)
    if a <= 0:
        return im
    layer = im.copy(); draw(ImageDraw.Draw(layer), layer, round(rise * (1 - a)))
    return layer if a >= 1 else Image.blend(im, layer, a)

def header(name):
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
    if name in CHAPTERS:
        tx(d, (96, 42), 'PEIRA', 36, INK, 'serif')
        label = CHAPTERS[name].upper().replace('Λ', 'λ')
        if 'λ' in label and not GREEK.is_file():
            label = label.replace('λ', 'LAMBDA')
        if 'λ' in label:  # Inria Sans has no Greek glyphs; draw λ with DejaVu Sans Bold
            head, tail = label.split('λ')
            greek = ImageFont.truetype(str(GREEK), 22)
            x = 1824 - tlen(tail, 22, 'bold') - greek.getlength('λ') - tlen(head, 22, 'bold')
            tx(d, (x, 54), head, 22, MUTED, 'bold', anchor='la'); x += tlen(head, 22, 'bold')
            d.text((x, 54), 'λ', font=greek, fill=MUTED, anchor='la'); x += greek.getlength('λ')
            tx(d, (x, 54), tail, 22, MUTED, 'bold', anchor='la')
        else:
            tx(d, (1824, 54), label, 22, MUTED, 'bold', anchor='ra')
        d.line((96, 100, 1824, 100), fill=BORDER, width=2)
    return im

# ---------------------------------------------------------------- Pillow scenes
def scene_opening(t):
    im = header('opening')
    return appear(im, t, .15, lambda d, L, o: (
        tx(d, (960, 360 + o), 'PEIRA', 190, ACCENT, 'serif', anchor='ma'),
        tx(d, (960, 610 + o), 'Learning Predictive Encoders through Inter-View Regressor Alignment',
           42, MUTED, anchor='ma')), dur=.8, rise=20)

RESULTS = [  # Table 1 of the paper (tab:in1k): mean ± sample std over 3 seeds.
    ('ImageNet-1K', 'ResNet-50, 100 epochs', (64, 70),
     [('PEIRA (k=1024)', 69.17, .06), ('VICReg', 68.81, .09), ('SIGReg', 66.26, .28)]),
    ('CIFAR-10', 'ResNet-18, 1000 epochs', (88, 93),
     [('PEIRA (k=1024)', 91.68, .18), ('VICReg', 90.92, .14), ('SIGReg', 92.34, .21)])]
def scene_results(t):
    im = header('results'); d = ImageDraw.Draw(im)
    tx(d, (96, 145), 'Competitive linear-probe accuracy', 58, INK, 'serif')
    tx(d, (98, 232), 'Linear-probe top-1 accuracy (%), controlled comparison from Table 1.', 30, MUTED)
    for gi, (name, sub, lim, rows) in enumerate(RESULTS):
        x0 = 96 + gi * 904
        tx(d, (x0, 310), name, 40, INK, 'serif'); tx(d, (x0, 362), sub, 25, MUTED)
        bx0, bx1 = x0 + 250, x0 + 620
        best = max(v for _, v, _ in rows)
        for ri, (m, v, s) in enumerate(rows):
            y = 440 + ri * 120
            g = smooth((t - .8 - gi * 1.2 - ri * .25) / 1.4)
            peira = m.startswith('PEIRA')
            tx(d, (x0, y + 22), m, 29, INK if peira else MUTED, 'bold' if peira else 'regular', anchor='lm')
            d.rectangle((bx0, y, bx1, y + 44), fill=TRACK)
            w = (v - lim[0]) / (lim[1] - lim[0]) * (bx1 - bx0) * g
            if w > 0:
                d.rectangle((bx0, y, bx0 + w, y + 44), fill=ACCENT if peira else GREY_BAR)
            if g > .6:
                a = ease((g - .6) / .4)
                tx(d, (bx1 + 20, y + 22), f'{v:.2f}', 33, mix(INK, a), 'bold' if v == best else 'regular', anchor='lm')
                tx(d, (bx1 + 120, y + 26), f'± {s:.2f}', 21, mix(MUTED, a), anchor='lm')
        ax_y = 440 + 3 * 120 - 50
        for v in range(lim[0], lim[1] + 1, 2 if lim[1] - lim[0] > 5 else 1):
            xx = bx0 + (v - lim[0]) / (lim[1] - lim[0]) * (bx1 - bx0)
            d.line((xx, ax_y, xx, ax_y + 8), fill=FAINT, width=2); tx(d, (xx, ax_y + 14), f'{v}', 20, MUTED, anchor='ma')
        tx(d, (bx0, ax_y + 46), f'axis starts at {lim[0]}%', 20, MUTED)
    im = appear(im, t, 5.5, lambda d, L, o: tx(d, (96, 880 + o),
        'Best on ImageNet-1K; on CIFAR-10, SIGReg leads and PEIRA beats VICReg.', 32, INK, 'bold'))
    tx(ImageDraw.Draw(im), (96, 1018), 'Mean ± std over 3 seeds, same augmentations, pretraining budget and probe. '
       'SIGReg uses a narrower projector. Source: Table 1.', 23, MUTED)
    return im

def scene_ending(t):
    im = header('ending')
    im = appear(im, t, .2, lambda d, L, o: (tx(d, (960, 150 + o), 'PEIRA', 120, ACCENT, 'serif', anchor='ma'),
        tx(d, (960, 300 + o), 'Learning Predictive Encoders through Inter-View Regressor Alignment', 36, MUTED, anchor='ma')))
    def pip(d, L, o):
        s = 'pip install peira-loss'; wd = tlen(s, 46, 'bold') + 90
        d.rounded_rectangle((960 - wd / 2, 400 + o, 960 + wd / 2, 492 + o), radius=18, fill=INK)
        tx(d, (960 - wd / 2 + 40, 446 + o), '$', 46, '#f39a85', 'bold', anchor='lm')
        tx(d, (960 - wd / 2 + 80, 446 + o), s, 46, SURFACE, 'bold', anchor='lm')
    im = appear(im, t, .7, pip)
    links = [('Project page', 'peira-ssl.github.io'), ('Paper', 'arXiv:2605.17671'),
             ('Code', 'github.com/Basile-Terv/PEIRA')]
    for i, (k, v) in enumerate(links):
        im = appear(im, t, 1.2 + .3 * i, lambda d, L, o, i=i, k=k, v=v: (
            tx(d, (900, 560 + i * 62 + o), k, 32, MUTED, anchor='ra'),
            tx(d, (930, 560 + i * 62 + o), v, 32, INK, 'bold')))
    im = appear(im, t, 2.4, lambda d, L, o: (
        tx(d, (960, 830 + o), 'Michael Arbel*  ·  Basile Terver*  ·  Jean Ponce', 34, INK, anchor='ma'),
        tx(d, (960, 884 + o), '*Equal contribution  ·  NeurIPS 2026', 25, MUTED, anchor='ma')))
    return im

PIL_SCENES = {'opening': (scene_opening, 3.0), 'results': (scene_results, 9.0), 'ending': (scene_ending, 6.0)}

# ---------------------------------------------------------------- browser capture
SEEK_JS = """t => {
  elapsed = t; playing = true; render();
  for (const a of document.getAnimations()) {
    if (a.__t0 === undefined) a.__t0 = t;
    a.pause(); a.currentTime = (t - a.__t0) * 1000;
  }
  const s = document.querySelector('#step-description');
  return [duration, s ? s.innerHTML.trim() : ''];
}"""
INIT_JS = 'window.requestAnimationFrame = () => 0;'
STYLE = 'html, body { background: #fbf9f6 !important; } * { caret-color: transparent !important; } .controls { display: none !important; }'

@contextlib.contextmanager
def serve_site():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(SITE))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{srv.server_address[1]}'
    finally:
        srv.shutdown()

def open_page(browser, url, scale, view_w):
    page = browser.new_page(viewport={'width': view_w, 'height': 1000}, device_scale_factor=scale)
    page.add_init_script(INIT_JS)
    page.goto(url, wait_until='networkidle')
    page.add_style_tag(content=STYLE)
    page.evaluate('document.fonts.ready.then(() => new Promise(r => setTimeout(r, 400)))')
    page.mouse.move(0, 0)
    return page

def capture(args):
    """Capture one animation; returns (name, duration, [(t, caption)], frame count)."""
    name, base_url, out_dir, times, shots = args
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    url = f'{base_url}/assets/anim/{name}.html?embed=1'
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # Card height is ~affine in viewport width (the SVG scales, the HTML chrome does not):
        # pick the widest viewport whose card fits CARD_BOX at TARGET_SCALE, so text stays large.
        def card_size(w):
            probe = open_page(browser, url, 1, w)
            box = probe.locator('#animation').bounding_box(); probe.close()
            return box['width'], box['height']
        bw, bh = CARD_BOX[2] - CARD_BOX[0], CARD_BOX[3] - CARD_BOX[1]
        (w1, h1), (w0, h0) = card_size(MAX_VIEW_W), card_size(MIN_VIEW_W)
        slope = (h1 - h0) / (w1 - w0)
        view_w = int(min(MAX_VIEW_W, max(MIN_VIEW_W, MIN_VIEW_W + (bh / TARGET_SCALE - h0) / slope)))
        cw, ch = card_size(view_w)
        scale = min(bw / cw, bh / ch)
        page = open_page(browser, url, scale, view_w)
        card = page.locator('#animation')
        dur = page.evaluate(SEEK_JS, 0)[0]
        if times is None:
            times = [i / FPS for i in range(int(round(dur * FPS)))]
        cues, last = [], None
        for i, t in enumerate(times):
            _, cap = page.evaluate(SEEK_JS, min(t, dur - .01))
            if cap != last:
                cues.append((t, cap)); last = cap
            if shots:
                card.screenshot(path=str(out_dir / f'{i:05d}.png'), animations='allow', caret='hide')
        browser.close()
    print(f'captured {name}: {len(times)} frames, {dur:.2f} s, view {view_w}px, scale {scale:.3f}', flush=True)
    return name, dur, cues, len(times)

def anim_frame(frames_dir, n, t):
    """Composite captured frame at local time t (held on the last frame past the end)."""
    i = max(0, min(n - 1, int(round(t * FPS))))
    card = Image.open(frames_dir / f'{i:05d}.png').convert('RGB')
    return card

def place(name, card):
    im = header(name)
    x = (CARD_BOX[0] + CARD_BOX[2] - card.width) // 2
    y = CARD_BOX[1] + (CARD_BOX[3] - CARD_BOX[1] - card.height) // 2
    im.paste(card, (x, y))
    return im

# ---------------------------------------------------------------- audio, captions
def soundtrack(path, dur):
    """Calm synthesized pad and plucks (from render.py)."""
    sr = 48000; n = int(sr * dur); aud = np.zeros((n, 2), np.float32)
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
    ts = np.arange(n) / sr
    aud *= (np.minimum(ts / 3, 1) * np.minimum((dur - ts) / 4, 1))[:, None]; aud = np.tanh(aud) * .6
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(sr); f.writeframes((aud * 32767).astype('<i2').tobytes())

SUP_SRC, SUP_DST = '0123456789+-−=()ni/', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱᐟ'
SUB_SRC, SUB_DST = '0123456789+-=()i', '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ᵢ'
def _script(inner, src, dst, mark):
    inner = re.sub(r'<[^>]+>', '', inner)
    if all(c in src for c in inner):
        return inner.translate(str.maketrans(src, dst))
    return mark + (inner if len(inner) == 1 else f'({inner})')

def html_text(s):
    """Caption HTML -> plain text, keeping <sup>/<sub> readable (Unicode where it exists)."""
    s = re.sub(r'<sup[^>]*>(.*?)</sup>', lambda m: _script(m.group(1), SUP_SRC, SUP_DST, '^'), s)
    s = re.sub(r'<sub[^>]*>(.*?)</sub>', lambda m: _script(m.group(1), SUB_SRC, SUB_DST, '_'), s)
    return html.unescape(re.sub(r'<[^>]+>', '', s))

def short(s, limit=150):
    s = re.sub(r'\s+', ' ', html_text(s)).strip()
    if len(s) > limit:  # drop asides first
        s = re.sub(r'\s*\([^()]{12,}\)', '', s)
    if len(s) <= limit:
        return s
    sentences = re.split(r'(?<=[.;])\s+', s)
    out = sentences[0]
    for nxt in sentences[1:]:
        if len(out) + 1 + len(nxt) > limit:
            break
        out += ' ' + nxt
    if len(out) > limit:  # cut a long single sentence at its last clause boundary
        cut = max(out.rfind(', ', 0, limit), out.rfind(': ', 0, limit))
        out = out[:cut].rstrip(',:') + '.' if cut > 40 else out
    return out

def srt_time(t):
    ms = int(round(t * 1000)); return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'

def write_captions(out, caps, starts, total):
    cues = [(starts['opening'], starts['question'] + XFADE, 'PEIRA: Learning Predictive Encoders through '
             'Inter-View Regressor Alignment')]
    for n in ANIMS:
        dur, steps, _ = caps[n]
        bounds = [s for s, _ in steps] + [dur]
        for (s, cap), e in zip(steps, bounds[1:]):
            cues.append((starts[n] + s + (XFADE if s == 0 else 0), starts[n] + e, short(cap)))
    cues.append((starts['results'] + XFADE, starts['ending'],
                 'Linear-probe accuracy (Table 1): best on ImageNet-1K; on CIFAR-10, SIGReg leads and PEIRA beats VICReg.'))
    cues.append((starts['ending'] + XFADE, total, 'peira-ssl.github.io · arXiv:2605.17671 · pip install peira-loss'))
    srt = '\n'.join(f'{i}\n{srt_time(s)} --> {srt_time(e)}\n{c}\n' for i, (s, e, c) in enumerate(cues, 1))
    (HERE / 'captions.srt').write_text(srt); (out / 'peira_video.srt').write_text(srt)
    (out / 'timeline.json').write_text(json.dumps({n: round(v, 2) for n, v in starts.items()}))

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=pathlib.Path, default=HERE / 'output')
    ap.add_argument('--preview', action='store_true', help='Stills + storyboard only (no video).')
    ap.add_argument('--jobs', type=int, default=5)
    ap.add_argument('--srt-only', action='store_true', help='Rebuild captions/timeline only (no screenshots).')
    a = ap.parse_args()
    out = a.out.resolve(); frames = out / 'frames'; out.mkdir(parents=True, exist_ok=True)

    with serve_site() as url:
        jobs = [(n, url, frames / n, None, not a.srt_only) for n in ANIMS]
        if a.preview:  # one still per animation late in its timeline (frame 1; frame 0 primes transitions)
            jobs = [(n, url, frames / n, [t - 1, t], True) for n, t in zip(ANIMS, [14.5, 13.5, 14, 13, 12.5])]
        with Pool(min(a.jobs, len(jobs))) as pool:
            caps = {n: (dur, cues, cnt) for n, dur, cues, cnt in pool.map(capture, jobs)}

    order = ['opening'] + ANIMS + ['results', 'ending']
    durs = {n: PIL_SCENES[n][1] if n in PIL_SCENES else caps[n][0] for n in order}
    starts, t0 = {}, 0.0
    for n in order:
        starts[n] = t0; t0 += durs[n] - XFADE
    total = t0 + XFADE

    def scene_frame(n, t):
        if n in PIL_SCENES:
            return PIL_SCENES[n][0](t)
        return place(n, anim_frame(frames / n, caps[n][2], t))

    if a.preview:
        sheet = Image.new('RGB', (960 * 2, 540 * 4), 'white')
        for i, n in enumerate(order):
            im = scene_frame(n, 1 / FPS if n in ANIMS else durs[n] - .5)
            im.save(out / f'preview_{n}.jpg', quality=93)
            sheet.paste(im.resize((960, 540), Image.Resampling.LANCZOS), ((i % 2) * 960, (i // 2) * 540))
        sheet.save(out / 'storyboard.jpg', quality=93)
        print('preview', out / 'storyboard.jpg', json.dumps({n: round(d, 2) for n, d in durs.items()}))
        return

    if a.srt_only:
        write_captions(out, caps, starts, total)
        return

    nframes = int(round(total * FPS))
    enc = subprocess.Popen([FF, '-y', '-v', 'warning', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                            '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17',
                            '-pix_fmt', 'yuv420p', str(out / 'video_only.mp4')], stdin=subprocess.PIPE)
    sheet = Image.new('RGB', (960 * 2, 540 * 4), 'white')
    story_t = {n: starts[n] + (durs[n] - .6 if n not in ANIMS else durs[n] * .8) for n in order}
    for f in range(nframes):
        T = f / FPS
        cur = max((n for n in order if starts[n] <= T), key=lambda n: starts[n])
        im = scene_frame(cur, T - starts[cur])
        k = order.index(cur)
        if k > 0 and T - starts[cur] < XFADE:
            prev = order[k - 1]
            im = Image.blend(scene_frame(prev, T - starts[prev]), im, smooth((T - starts[cur]) / XFADE))
        if T < .25:
            im = Image.blend(Image.new('RGB', (W, H), BG), im, ease(T / .25))
        ImageDraw.Draw(im).rectangle((0, 1075, round(W * T / total), 1079), fill=BRAND)
        for i, n in enumerate(order):
            if f == int(round(story_t[n] * FPS)):
                sheet.paste(im.resize((960, 540), Image.Resampling.LANCZOS), ((i % 2) * 960, (i // 2) * 540))
        enc.stdin.write(im.tobytes())
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError('encoding failed')
    sheet.save(out / 'storyboard.jpg', quality=93)

    soundtrack(out / 'soundtrack.wav', total)
    subprocess.run([FF, '-y', '-v', 'warning', '-i', str(out / 'video_only.mp4'), '-i', str(out / 'soundtrack.wav'),
                    '-c:v', 'copy', '-af', 'volume=6dB', '-c:a', 'aac', '-b:a', '192k', '-t', f'{total:.3f}',
                    '-movflags', '+faststart',
                    '-metadata', 'title=PEIRA | Learning Predictive Encoders through Inter-View Regressor Alignment',
                    '-metadata', 'comment=Synthesized instrumental soundtrack.', str(out / 'peira_video.mp4')],
                   check=True)

    write_captions(out, caps, starts, total)
    print('FINAL', out / 'peira_video.mp4', f'{total:.2f} s', json.dumps(
        {n: [round(starts[n], 2), round(durs[n], 2)] for n in order}), flush=True)

if __name__ == '__main__':
    main()
