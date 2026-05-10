import gsap from 'gsap';

/**
 * Hero entrance choreography. Plays once on first paint:
 *
 *   1. Brand mark + small wordmark fade in together
 *   2. Wordmark "TokenMind" types in character-by-character
 *   3. Editorial headline reveals word-by-word
 *   4. Tagline + CTA buttons stagger up
 *   5. Scroll cue at the bottom fades in last
 *
 * The wordmark is split into per-character spans on the fly, the headline
 * into per-word spans, so layout is locked before the animation begins
 * (no reflow as text appears).
 */

const TYPEWRITER_CHAR_DURATION = 0.05;
const CARET_HOLD_BEFORE_FADE = 0.6;

export function playHeroIntro(): void {
  splitWordmark();
  splitHeadline();

  const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });

  tl.to('[data-hero-mark]', { opacity: 1, scale: 1, duration: 0.7 }, 0);
  tl.set('[data-hero-wordmark]', { opacity: 1 }, 0.15);

  tl.to(
    '[data-hero-wordmark] .hero-char',
    {
      opacity: 1,
      duration: TYPEWRITER_CHAR_DURATION,
      stagger: TYPEWRITER_CHAR_DURATION,
      ease: 'none',
    },
    0.2,
  );

  tl.to(
    '[data-hero-wordmark] .hero-caret',
    { opacity: 0, duration: 0.4, ease: 'power1.out' },
    `+=${CARET_HOLD_BEFORE_FADE}`,
  );

  tl.set('[data-hero-headline]', { opacity: 1 }, '<-=0.2');

  tl.to(
    '[data-hero-headline] .hero-word',
    {
      opacity: 1,
      y: 0,
      duration: 0.7,
      stagger: 0.06,
      ease: 'power3.out',
    },
    '<+=0.05',
  );

  tl.to(
    '[data-hero-tagline]',
    { opacity: 1, y: 0, duration: 0.8 },
    '-=0.4',
  )
    .to(
      '[data-hero-cta]',
      { opacity: 1, y: 0, duration: 0.7, stagger: 0.08 },
      '<+=0.15',
    )
    .to(
      '[data-hero-scroll-cue]',
      { opacity: 1, duration: 1.2, ease: 'power1.out' },
      '<+=0.3',
    );
}

function splitWordmark(): void {
  const root = document.querySelector<HTMLElement>('[data-hero-wordmark]');
  if (!root) return;
  if (root.dataset.split === 'true') return;

  const text = root.textContent?.trim() ?? '';
  root.textContent = '';

  for (const ch of text) {
    const span = document.createElement('span');
    span.className = 'hero-char';
    span.textContent = ch === ' ' ? ' ' : ch;
    span.style.opacity = '0';
    span.style.display = 'inline-block';
    root.appendChild(span);
  }

  const caret = document.createElement('span');
  caret.className = 'hero-caret';
  caret.textContent = '|';
  caret.setAttribute('aria-hidden', 'true');
  root.appendChild(caret);

  root.dataset.split = 'true';
}

/**
 * Split the headline into per-word spans for staggered entrance.
 *
 * Words are wrapped in inline-block spans (so transform/opacity work without
 * fighting line-box layout); whitespace is preserved as plain text nodes
 * between them so words don't fuse together. <br> and other element nodes
 * are passed through verbatim, so the responsive line break still fires.
 *
 * Idempotent — bails if already split.
 */
function splitHeadline(): void {
  const root = document.querySelector<HTMLElement>('[data-hero-headline]');
  if (!root) return;
  if (root.dataset.split === 'true') return;

  const out: Node[] = [];

  for (const child of Array.from(root.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      const text = child.textContent ?? '';
      // Splitting on the regex with capture group preserves the whitespace
      // runs as separate tokens, which we re-emit as raw text nodes.
      const tokens = text.split(/(\s+)/);
      for (const token of tokens) {
        if (token === '') continue;
        if (/^\s+$/.test(token)) {
          out.push(document.createTextNode(token));
          continue;
        }
        const span = document.createElement('span');
        span.className = 'hero-word';
        span.textContent = token;
        span.style.opacity = '0';
        span.style.display = 'inline-block';
        span.style.transform = 'translateY(18px)';
        out.push(span);
      }
    } else {
      out.push(child.cloneNode(true));
    }
  }

  root.textContent = '';
  for (const node of out) root.appendChild(node);
  root.dataset.split = 'true';
}
