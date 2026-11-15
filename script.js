const progress = document.querySelector('.reading-progress');
document.querySelectorAll('.peira-animation iframe').forEach(animationFrame => {
  let frameObserver;
  let visibleInViewport = false;
  const notifyVisibility = () => {
    animationFrame.contentWindow?.postMessage({
      type: 'peira-animation-visibility',
      visible: visibleInViewport && !document.hidden,
    }, location.origin);
  };
  const visibilityObserver = new IntersectionObserver(([entry]) => {
    visibleInViewport = entry.isIntersecting && entry.intersectionRect.width > 0 && entry.intersectionRect.height > 0;
    notifyVisibility();
  });
  visibilityObserver.observe(animationFrame);
  document.addEventListener('visibilitychange', notifyVisibility);
  const fitAnimationFrame = () => {
    const content = animationFrame.contentDocument?.querySelector('main');
    if (!content) return;
    frameObserver?.disconnect();
    const fit = () => { animationFrame.style.height = `${Math.ceil(content.getBoundingClientRect().height)}px`; };
    frameObserver = new ResizeObserver(fit);
    frameObserver.observe(content);
    fit();
  };
  animationFrame.addEventListener('load', () => {
    fitAnimationFrame();
    notifyVisibility();
  });
  fitAnimationFrame();
});
const tocLinks = [...document.querySelectorAll('.side-toc a')];
const sections = tocLinks.map(link => document.querySelector(link.hash)).filter(Boolean);
let scheduled = false;

function updateReadingPosition() {
  if (!progress || !sections.length) return;
  const scrollable = document.documentElement.scrollHeight - window.innerHeight;
  const fraction = scrollable > 0 ? Math.min(1, Math.max(0, window.scrollY / scrollable)) : 0;
  progress.style.transform = `scaleX(${fraction})`;
  let active = sections[0];
  for (const section of sections) {
    if (section.getBoundingClientRect().top <= 130) active = section;
  }
  if (fraction >= 0.995) active = sections[sections.length - 1];
  for (const link of tocLinks) {
    if (link.hash === `#${active.id}`) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  }
  scheduled = false;
}
function scheduleUpdate() {
  if (!scheduled) {
    scheduled = true;
    requestAnimationFrame(updateReadingPosition);
  }
}
window.addEventListener('scroll', scheduleUpdate, { passive: true });
window.addEventListener('resize', scheduleUpdate);
window.addEventListener('load', scheduleUpdate);
updateReadingPosition();

document.querySelectorAll('.mobile-toc a').forEach(link => {
  link.addEventListener('click', () => { document.querySelector('.mobile-toc').open = false; });
});
const copyButton = document.querySelector('.copy-button');
const copyStatus = document.querySelector('.copy-status');
if (copyButton) copyButton.hidden = false;
copyButton?.addEventListener('click', async () => {
  const citation = document.querySelector('#citation');
  try {
    await navigator.clipboard.writeText(citation.textContent);
    copyButton.textContent = 'Copied!';
    copyStatus.textContent = 'Citation copied to clipboard.';
    setTimeout(() => { copyButton.textContent = 'Copy'; }, 2200);
  } catch {
    const range = document.createRange();
    range.selectNodeContents(citation);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    copyStatus.textContent = 'Citation selected. Press Ctrl+C or ⌘C to copy.';
  }
});
