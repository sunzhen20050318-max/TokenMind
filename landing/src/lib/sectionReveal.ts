import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/**
 * Universal scroll-triggered entrance animations for non-Hero sections.
 *
 * Three reveal variants, opt in by adding the matching data attribute:
 *
 *   [data-reveal]            single element fades+rises into view
 *   [data-reveal-stagger]    direct children stagger in (good for grids)
 *   [data-reveal-pop]        children scale+fade in with light overshoot
 *                            (good for icon grids — feels more punchy)
 *
 * All variants use scrub:false (non-scrubbed) and `toggleActions:
 * "play none none reverse"` so the animation plays once on entry, then
 * reverses if the user scrolls back above the trigger. This avoids the
 * "stuck" feeling scrubbed reveals get on long pages.
 *
 * Idempotent: each element is marked with a data flag once bound so
 * Astro HMR doesn't double-bind.
 */
export function initSectionReveals(): void {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // -- single-element reveals --------------------------------------------
  document.querySelectorAll<HTMLElement>('[data-reveal]').forEach((el) => {
    if (el.dataset.revealBound === 'true') return;
    el.dataset.revealBound = 'true';

    if (reduced) {
      gsap.set(el, { opacity: 1, y: 0 });
      return;
    }

    gsap.fromTo(
      el,
      { opacity: 0, y: 32 },
      {
        opacity: 1,
        y: 0,
        duration: 0.9,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: el,
          start: 'top 88%',
          toggleActions: 'play none none reverse',
        },
      },
    );
  });

  // -- staggered child reveals (grids) -----------------------------------
  document
    .querySelectorAll<HTMLElement>('[data-reveal-stagger]')
    .forEach((container) => {
      if (container.dataset.revealBound === 'true') return;
      container.dataset.revealBound = 'true';

      const items = Array.from(container.children) as HTMLElement[];
      if (!items.length) return;

      if (reduced) {
        gsap.set(items, { opacity: 1, y: 0 });
        return;
      }

      gsap.fromTo(
        items,
        { opacity: 0, y: 28 },
        {
          opacity: 1,
          y: 0,
          duration: 0.7,
          ease: 'power3.out',
          stagger: 0.07,
          scrollTrigger: {
            trigger: container,
            start: 'top 82%',
            toggleActions: 'play none none reverse',
          },
        },
      );
    });

  // -- pop-in child reveals (icon grids) ---------------------------------
  document
    .querySelectorAll<HTMLElement>('[data-reveal-pop]')
    .forEach((container) => {
      if (container.dataset.revealBound === 'true') return;
      container.dataset.revealBound = 'true';

      const items = Array.from(container.children) as HTMLElement[];
      if (!items.length) return;

      if (reduced) {
        gsap.set(items, { opacity: 1, scale: 1 });
        return;
      }

      gsap.fromTo(
        items,
        { opacity: 0, scale: 0.78, y: 18 },
        {
          opacity: 1,
          scale: 1,
          y: 0,
          duration: 0.55,
          ease: 'back.out(1.7)',
          stagger: 0.05,
          scrollTrigger: {
            trigger: container,
            start: 'top 82%',
            toggleActions: 'play none none reverse',
          },
        },
      );
    });
}
