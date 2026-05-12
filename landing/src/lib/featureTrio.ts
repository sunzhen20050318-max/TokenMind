import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/**
 * Wire the three-pillar accordion section (FeatureTrio.astro).
 *
 * Two responsibilities:
 *
 * 1. Entrance animation. Trigger when the section scrolls into view.
 *    Center card drops down from above, side cards rise from below,
 *    they snap into a row (md+ only — mobile uses a simple fade).
 *
 * 2. Interaction. Hover on desktop / tap on coarse pointers sets a
 *    `data-state` attribute on each card:
 *      - "rest":   no card is active (default)
 *      - "active": this card is the focused one (expanded)
 *      - "strip":  a sibling is active (this card is squeezed)
 *    All the visual changes are driven by CSS in FeatureTrio.astro.
 *
 * Idempotent: skips re-binding if already wired.
 */
export function initFeatureTrio(): void {
  const list = document.querySelector<HTMLElement>('[data-trio-list]');
  if (!list || list.dataset.trioBound === 'true') return;
  list.dataset.trioBound = 'true';

  const cards = Array.from(
    list.querySelectorAll<HTMLElement>('[data-trio-card]'),
  );
  if (!cards.length) return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const coarse = window.matchMedia('(pointer: coarse)').matches;

  // -- interaction --------------------------------------------------------
  // Both `data-active` (on the list) and `data-state` (on each card) are
  // set together. The container attribute drives the animated grid
  // template columns; the per-card attribute drives the inner content
  // swap (horizontal ↔ vertical, items reveal). Keeping them in lockstep
  // means CSS can read whichever is cheaper.
  function setActive(key: string | null): void {
    if (!key) {
      list!.removeAttribute('data-active');
      for (const card of cards) card.dataset.state = 'rest';
      return;
    }
    list!.setAttribute('data-active', key);
    for (const card of cards) {
      card.dataset.state = card.dataset.trioCard === key ? 'active' : 'strip';
    }
  }

  for (const card of cards) {
    const key = card.dataset.trioCard ?? '';

    if (!coarse) {
      card.addEventListener('mouseenter', () => setActive(key));
      card.addEventListener('focusin', () => setActive(key));
    }

    // Touch / click toggles. On a fine pointer this lets users "lock" a
    // card open by clicking, then click elsewhere or the same card to
    // release. On coarse pointers it's the only activation path.
    card.addEventListener('click', () => {
      if (card.dataset.state === 'active') {
        setActive(null);
      } else {
        setActive(key);
      }
    });
  }

  if (!coarse) {
    list.addEventListener('mouseleave', () => setActive(null));
  }

  // Dismiss when clicking outside the trio (touch UX so users can close
  // an open card without finding the same tap-target).
  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Node)) return;
    if (list.contains(event.target)) return;
    setActive(null);
  });

  // -- entrance animation -------------------------------------------------
  // Mobile (< 768px): cards are stacked, so a simple stagger reveal is
  // enough. Desktop: middle drops from above, sides rise from below.
  if (reduced) {
    gsap.set(cards, { opacity: 1, y: 0 });
    return;
  }

  const mm = gsap.matchMedia();

  mm.add('(min-width: 768px)', () => {
    // DOM order: [tools(left), channels(center), memory(right)].
    const [leftCard, centerCard, rightCard] = cards;

    gsap.set(leftCard, { opacity: 0, y: 80 });
    gsap.set(centerCard, { opacity: 0, y: -80 });
    gsap.set(rightCard, { opacity: 0, y: 80 });

    // Scrub the entrance against scroll position. The trio animates
    // through its travel range over the 50% of viewport directly after
    // the trio's top crosses the viewport bottom — i.e., as the user is
    // still scrolling away from ZoomSection's exit, they're scrubbing
    // the trio into position. Continuous motion across the section
    // handoff with no animation playing off-screen.
    const tl = gsap.timeline({
      defaults: { duration: 1, ease: 'power3.out' },
      scrollTrigger: {
        trigger: list,
        start: 'top bottom',
        end: 'top 50%',
        scrub: 0.4,
        invalidateOnRefresh: true,
      },
    });

    // Center hits first, sides snap in just behind with a tiny stagger.
    tl.to(centerCard, { opacity: 1, y: 0 }, 0)
      .to(leftCard, { opacity: 1, y: 0 }, 0.1)
      .to(rightCard, { opacity: 1, y: 0 }, 0.1);
  });

  mm.add('(max-width: 767px)', () => {
    gsap.fromTo(
      cards,
      { opacity: 0, y: 28 },
      {
        opacity: 1,
        y: 0,
        duration: 0.6,
        ease: 'power3.out',
        stagger: 0.08,
        scrollTrigger: {
          trigger: list,
          start: 'top 82%',
          toggleActions: 'play none none reverse',
        },
      },
    );
  });
}
