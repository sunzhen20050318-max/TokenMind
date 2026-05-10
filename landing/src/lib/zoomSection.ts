import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/**
 * Product showcase choreography. One continuous scrub-true timeline
 * driven by a single ScrollTrigger spans the whole section. Pinning is
 * handled by browser-native `position: sticky` on the inner container
 * (not GSAP pin), which avoids the two stutter points that pin
 * engagement / release used to introduce.
 *
 * Section is 300vh tall. ScrollTrigger maps `top bottom → bottom bottom`
 * (= 300vh of scroll) to timeline progress 0 → 1:
 *
 *   progress 0.00 → 0.33  entry zoom: chatui scales 0.58 → 1.0 as the
 *                         section scrolls into view (sticky not yet
 *                         engaged — element is in normal flow)
 *   progress 0.33         sticky engages (section.top hits viewport.top)
 *                         — no animation discontinuity, the timeline
 *                         simply keeps scrubbing
 *   progress 0.33 → 0.65  chatui shrinks AND translates upward off
 *                         viewport (scale 1 → 0.5, y 0 → -65vh)
 *   progress 0.45 → 0.80  panel A enters from the LEFT (overlaps the
 *                         tail of frame exit so motion is continuous)
 *   progress 0.65 → 1.00  panel B enters from the RIGHT (overlaps
 *                         panel A's tail; eases out through the end so
 *                         motion fills the full timeline — no static
 *                         hold zone at the tail)
 *   progress 1.00         sticky disengages naturally; panels then
 *                         scroll up with the rest of the page
 *
 * Continuous overlapping motion means every wheel tick produces visible
 * change — there are no scroll ranges where nothing is animating.
 *
 * Idempotent across HMR — bails out if a previous binding is still alive.
 */
export function initZoomSection(): void {
  const trigger = document.querySelector<HTMLElement>('[data-zoom-section]');
  const frame = document.querySelector<HTMLElement>('[data-zoom-frame]');
  const featLeft = document.querySelector<HTMLElement>('[data-feature-left]');
  const featRight = document.querySelector<HTMLElement>('[data-feature-right]');
  if (!trigger || !frame || !featLeft || !featRight) return;
  if (trigger.dataset.zoomBound === 'true') return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) {
    // Skip choreography. Render the resting state: chatui partially out,
    // both panels visible in their final stacked positions.
    gsap.set(frame, { scale: 0.5, y: '-65vh', borderRadius: '14px' });
    gsap.set(featLeft, { xPercent: 0, opacity: 1 });
    gsap.set(featRight, { xPercent: 0, opacity: 1 });
    trigger.dataset.zoomBound = 'true';
    return;
  }

  // Initial off-stage positions. xPercent ±120 keeps the panels safely
  // outside the viewport even on extra-wide monitors.
  gsap.set(featLeft, { xPercent: -120, opacity: 0 });
  gsap.set(featRight, { xPercent: 120, opacity: 0 });

  // Single timeline, single ScrollTrigger. Sticky on the inner container
  // handles the visual pinning — no GSAP pin.
  //
  // scrub:0.4 (NOT true) adds a 0.4s catch-up filter on top of the raw
  // scroll position. With `scrub: true`, the animation snaps to the
  // exact scroll position every frame; combined with Lenis interpolation
  // this can produce 1–2-frame micro-jitter and amplifies the brief
  // compositor-layer recalc that sticky engagement triggers. The 0.4s
  // smoothing absorbs both, giving a perceptibly silkier ride at the
  // cost of an imperceptible animation lag.
  const tl = gsap.timeline({
    defaults: { ease: 'power2.inOut' },
    scrollTrigger: {
      trigger,
      start: 'top bottom',
      end: 'bottom bottom',
      scrub: 0.4,
      invalidateOnRefresh: true,
    },
  });

  tl
    // Entry zoom: chatui scales 0.58 → 1.0 as the section scrolls into
    // view. Linear ease so the zoom feels mechanically tied to the
    // scroll position.
    .fromTo(
      frame,
      { scale: 0.58, y: 0, borderRadius: '24px' },
      {
        scale: 1,
        borderRadius: '14px',
        duration: 0.33,
        ease: 'none',
      },
      0,
    )
    // Frame exit: shrinks AND slides upward off-viewport. ease-in lets
    // the exit accelerate as panel A starts arriving, so they feel
    // dynamically linked.
    .to(
      frame,
      { scale: 0.5, y: '-65vh', duration: 0.32, ease: 'power2.in' },
      0.33,
    )
    // Panel A enters from the left, overlapping the back half of frame
    // exit (0.45 → 0.65 both move) and continuing solo through 0.80.
    .to(
      featLeft,
      { xPercent: 0, opacity: 1, duration: 0.35, ease: 'power3.out' },
      0.45,
    )
    // Panel B enters from the right, starting while A is still finishing
    // (0.65 → 0.80 both move) and easing out through the end of the
    // timeline. Filling the tail eliminates any static hold zone — B is
    // still subtly settling when the section exits.
    .to(
      featRight,
      { xPercent: 0, opacity: 1, duration: 0.35, ease: 'power3.out' },
      0.65,
    );

  trigger.dataset.zoomBound = 'true';
}
