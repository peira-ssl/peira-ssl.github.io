# PEIRA project website

Static project page for the NeurIPS 2026 paper
**PEIRA: Learning Predictive Encoders through Inter-View Regressor Alignment**
(Michael Arbel\*, Basile Terver\*, Jean Ponce; \* equal contribution).

Plain HTML, CSS and JavaScript with no build step:

- `index.html`, `styles.css`, `script.js`: the page.
- `assets/img/`: figures from the paper and the social card.
- `assets/anim/`: five self-contained step-by-step SVG animations, embedded as iframes
  (`?embed=1` shows only the animation card; open a file without it to see it standalone).
- `video-production/`: renderer for a promotional video. The page does not load it.

Math is rendered with KaTeX 0.16.11 from jsDelivr (with integrity hashes); fonts come
from Google Fonts.

## Preview locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

Serve over HTTP rather than opening `index.html` as a file: the page sizes and pauses the
animation iframes through same-origin access, which browsers block on `file://`.

## Publish with GitHub Pages

1. Push to a repository named `peira-ssl.github.io` in the `peira-ssl` GitHub organization (the site is then served at the root, https://peira-ssl.github.io/).
2. In the repository, open Settings > Pages.
3. Under "Build and deployment", set Source to "Deploy from a branch", pick `main` and `/ (root)`, then Save.

The `.nojekyll` file makes Pages serve the files as they are. The canonical, `og:url` and
social image URLs in `index.html` assume `https://peira-ssl.github.io/`;
update them if the page moves to another URL or a custom domain.

## Related links

- Paper: https://arxiv.org/abs/2605.17671
- Code: https://github.com/Basile-Terv/PEIRA
- Loss package: https://github.com/MichaelArbel/peira-loss (`pip install peira-loss`)
- Checkpoints: https://huggingface.co/peira-ssl/PEIRA
