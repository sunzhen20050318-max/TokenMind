import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/**
 * Product showcase choreography. One continuous scrub timeline driven
 * by a single ScrollTrigger spans the whole section, from entry zoom
 * through horizontal panel exit. Pinning is handled by browser-native
 * `position: sticky` on the inner container (not GSAP pin), which
 * removes the two stutter points that pin engagement / release used
 * to introduce.
 *
 * Section is 400vh tall. ScrollTrigger maps `top bottom → bottom bottom`
 * (= 400vh of scroll) to timeline progress 0 → 1:
 *
 *   0.00 → 0.20  entry zoom: chatui scales 0.58 → 1.0
 *   0.25         sticky engages (section.top hits viewport.top)
 *   0.20 → 0.40  chatui shrinks AND translates upward off-viewport
 *   0.25 → 0.55  panels A AND B enter SIMULTANEOUSLY — A from the
 *                LEFT (rightward) and B from the RIGHT (leftward).
 *                They start at 0.25 (just as chatui begins shrinking)
 *                so the user sees chatui sliding upward AND the side
 *                panels sliding inward in the same frames — the two
 *                motions overlap by 15% of timeline (~60vh of scroll).
 *   0.55         CRITICAL POINT — both panels are at center together.
 *                Exit begins immediately, no hold.
 *   0.55 → 1.00  both panels exit SIMULTANEOUSLY, each continuing
 *                in the direction it entered with: A continues right
 *                (xPercent 0 → +150), B continues left (0 → -150).
 *                Same direction throughout — never reverses.
 *
 * There is no temporal crossover (no panel exits while the other is
 * still entering). Both entrances finish before either exit begins.
 * The vertical separation of A (top half) and B (bottom half) means
 * they never spatially collide either, even as they sweep past 0.
 *
 * Between 0.50 and 0.65, panel A sits at center while B is still
 * arriving — that's fine, the page is animating (B is moving), so the
 * scroll still produces visible motion every tick. The pain point the
 * user identified was the dead zone AFTER both had arrived; that zone
 * no longer exists.
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
  // scroll position. Combined with Lenis interpolation this gives a
  // perceptibly silkier ride at the cost of an imperceptible animation
  // lag — and crucially smooths the brief compositor-layer recalc that
  // sticky engagement triggers.
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
    // ── Entrance ──────────────────────────────────────────────────────
    // chatui scales up as the section scrolls into view. Linear ease so
    // the zoom feels mechanically tied to scroll position.
    .fromTo(
      frame,
      { scale: 0.58, y: 0, borderRadius: '24px' },
      { scale: 1, borderRadius: '14px', duration: 0.20, ease: 'none' },
      0,
    )
    // chatui shrinks and translates upward off-viewport.
    // Linear ease (none) — preserves non-zero velocity at the seam
    // with the zoom-in segment above. With `power2.in` the exit
    // started from velocity zero, which read as a brief pause at
    // maximum size; linear keeps the motion continuous through 0.20.
    .to(
      frame,
      { scale: 0.5, y: '-65vh', duration: 0.20, ease: 'none' },
      0.20,
    )
    // Both panels enter SIMULTANEOUSLY — start at 0.25 (overlapping
    // most of chatui's exit at 0.20-0.40) and arrive at center at
    // 0.55. The 0.25-0.40 window has chatui sliding up AND panels
    // sliding in at the same time — that's the cross-cut the user
    // asked for. Linear ease keeps velocity non-zero at the seam.
    .to(
      featLeft,
      { xPercent: 0, opacity: 1, duration: 0.30, ease: 'none' },
      0.25,
    )
    .to(
      featRight,
      { xPercent: 0, opacity: 1, duration: 0.30, ease: 'none' },
      0.25,
    )
    // ── Exit ──────────────────────────────────────────────────────────
    // Critical point is 0.55 — both panels are at xPercent 0 with
    // non-zero velocity. The exits run 0.55 → 1.00, each panel
    // continuing in its entry direction past 0:
    //
    //   - A continues RIGHTWARD past 0 to xPercent +150 (off-viewport)
    //   - B continues LEFTWARD past 0 to xPercent -150 (off-viewport)
    //
    // Linear ease preserves velocity continuity through 0.55. Speed
    // shifts slightly (entry +400 → exit +333) but never goes to zero,
    // so there's no perceived pause at the seam. Panels are vertically
    // stacked (A top half, B bottom half) so they don't collide as
    // they sweep past 0 in opposite directions.
    .to(
      featLeft,
      { xPercent: 150, opacity: 0, duration: 0.45, ease: 'none' },
      0.55,
    )
    .to(
      featRight,
      { xPercent: -150, opacity: 0, duration: 0.45, ease: 'none' },
      0.55,
    );

  trigger.dataset.zoomBound = 'true';
}
