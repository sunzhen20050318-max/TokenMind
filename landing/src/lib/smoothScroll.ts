import Lenis from 'lenis';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/**
 * Bootstrap Lenis-driven smooth scrolling and synchronize GSAP's ScrollTrigger
 * to the same RAF loop. Without this sync, scroll-driven animations would
 * fire on the native scroll position while Lenis interpolates the visual
 * position, leading to "leading" or "lagging" effects.
 *
 * Returns the Lenis instance so callers can stop/start the scroll lock when
 * a modal opens, etc. The script tag in BaseLayout.astro calls this once on
 * the client; further callers (per-page enhancements) can read the global.
 */
export function initSmoothScroll(): Lenis {
  const lenis = new Lenis({
    // lerp (linear interpolation factor 0–1) gives a constant per-frame
    // approach toward the target scroll, which feels more uniform than a
    // duration-based ease and pairs better with GSAP scrub:0.4 — both
    // smoothers compound predictably instead of fighting each other.
    lerp: 0.1,
    smoothWheel: true,
    touchMultiplier: 1.4,
  });

  // Drive Lenis from GSAP's ticker so both share one RAF loop and stay in
  // perfect sync. Without this you'll see ScrollTrigger updates one frame
  // out of phase with the visible scroll position.
  gsap.ticker.add((time) => {
    lenis.raf(time * 1000);
  });
  gsap.ticker.lagSmoothing(0);

  // Tell ScrollTrigger to refresh whenever Lenis tells us scroll changed —
  // belt-and-braces; ScrollTrigger normally refreshes on resize but it
  // can't tell when content above changes height after images load.
  lenis.on('scroll', () => {
    ScrollTrigger.update();
  });

  return lenis;
}
