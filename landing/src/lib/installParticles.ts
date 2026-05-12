/**
 * Install-section particle field.
 *
 * Renders a uniform grid of white dots on the section's full-bleed
 * canvas. As the user moves the cursor toward the left or right half
 * of the section, the closest particles peel away from their home
 * cells and assemble into a `{` `}` pair of braces that wraps the
 * corresponding download button. When the cursor leaves the zone (or
 * the section), the particles spring back to their home grid.
 *
 * The brace shape is sampled from the actual `{` and `}` glyphs of a
 * monospace font rendered on an offscreen canvas — this gives a
 * proper typographic brace, not a hand-drawn approximation.
 *
 * Skipped under prefers-reduced-motion. On coarse-pointer devices the
 * grid renders but the brace formation never triggers (no cursor).
 */

interface Particle {
  homeX: number;
  homeY: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  baseAlpha: number;
  radius: number;
  /** Per-particle phase for the breathing oscillation around the brace
   *  target. Random init so particles don't all bob in unison. */
  phase: number;
}

interface Point {
  x: number;
  y: number;
}

// Tighter grid spacing → roughly 2× the number of particles compared to
// the previous setting. Combined with the smaller per-particle radius
// below, the field reads as fine dust instead of conspicuous dots.
const SPACING = 26;
const JITTER = 3;
// Spring constants are deliberately symmetric (home == target) so
// outbound (gathering) and inbound (returning to home) feel the same
// pace — both very slow drifts, not snaps.
const HOME_SPRING_K = 0.0075;
const TARGET_SPRING_K = 0.0075;
const DAMPING = 0.92;
const BRACE_VERTICAL_PADDING = 100; // px the brace extends above and below the card
const BRACE_OFFSET = 90;            // horizontal gap between brace and card edge
const BRACE_MIN_HEIGHT = 480;       // floor for very short cards
const ZONE_DEADBAND = 80;          // px around the section's centerline
                                   // where neither side is active — keeps
                                   // the formation from flipping nervously
                                   // when the cursor sits dead-centre

// Once a particle is in the brace formation, we orbit its target by a
// small offset using a sine wave. Per-particle phase makes the orbit
// asynchronous so the brace looks alive instead of rigid.
const BRACE_BREATH_AMP = 3.2;      // px of oscillation around the target
const BRACE_BREATH_FREQ = 0.0012;  // angular frequency (radians per ms)

/**
 * Sample `{` or `}` outline by rendering the glyph onto an offscreen
 * canvas and walking its pixels at a fixed stride. Returns a list of
 * (x, y) points that, taken together, trace the brace shape centred
 * at (cx, cy).
 */
function getBracePoints(
  char: '{' | '}',
  cx: number,
  cy: number,
  h: number,
): Point[] {
  const size = Math.ceil(h * 1.4);
  const off = document.createElement('canvas');
  off.width = size;
  off.height = size;
  const c = off.getContext('2d');
  if (!c) return [];
  // Medium-weight monospace + an explicit stroke pass. Pure `fillText`
  // at weight 200 looked correct on macOS (SF Mono / ui-monospace has
  // real thin weights), but on Windows the fallback (Consolas /
  // Courier New) renders ultra-thin verticals — the brace's spine ends
  // up only 1px wide, so at the sampling stride below only a single
  // column of pixels is captured and the formation degrades to one
  // particle per row on the vertical stem. Drawing both fill AND
  // stroke with an explicit lineWidth guarantees a minimum thickness
  // regardless of font, normalizing the result across platforms.
  c.font = `500 ${h}px ui-monospace, "JetBrains Mono", "Source Code Pro", monospace`;
  c.fillStyle = '#fff';
  c.strokeStyle = '#fff';
  c.lineWidth = Math.max(2.5, h * 0.045);
  c.lineJoin = 'round';
  c.lineCap = 'round';
  c.textBaseline = 'middle';
  c.textAlign = 'center';
  c.fillText(char, size / 2, size / 2);
  c.strokeText(char, size / 2, size / 2);

  const data = c.getImageData(0, 0, size, size).data;
  const points: Point[] = [];
  // Stride controls how dense the brace is. Larger stride = fewer
  // sampled points = fewer particles pulled into the formation = more
  // particles left dotting the background. Tuned so the brace reads as
  // a clean tracing instead of a solid block, and the surrounding
  // field stays visibly populated.
  const stride = Math.max(11, Math.round(h / 28));
  for (let py = 0; py < size; py += stride) {
    for (let px = 0; px < size; px += stride) {
      const i = (py * size + px) * 4;
      // Threshold lowered from 100 → 60 so antialiased edges of the
      // stroked glyph are captured. Combined with the stroke pass
      // above, this widens the brace's apparent footprint by ~1 stride
      // step on either side, ensuring 2–3 columns of particles in the
      // vertical stem instead of 1.
      if (data[i + 3] > 60) {
        points.push({
          x: cx + (px - size / 2),
          y: cy + (py - size / 2),
        });
      }
    }
  }
  return points;
}

export function initInstallParticles(): () => void {
  const section = document.querySelector<HTMLElement>(
    '[data-install-section]',
  );
  const canvas = section?.querySelector<HTMLCanvasElement>(
    '[data-install-canvas]',
  );
  if (!section || !canvas) return () => {};

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) return () => {};

  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return () => {};

  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const coarse = window.matchMedia('(pointer: coarse)').matches;

  let width = 0;
  let height = 0;
  const particles: Particle[] = [];
  let mouseX = -10000;
  let mouseInside = false;
  let activeZone: 'left' | 'right' | null = null;
  // Map of particle index → target point it's currently springing to.
  // Particles not in the map spring to their home cell.
  const assignments = new Map<number, Point>();
  let rafId = 0;
  let lastFrame = performance.now();

  function resize(): void {
    const rect = section!.getBoundingClientRect();
    width = rect.width;
    height = rect.height;
    canvas!.width = width * dpr;
    canvas!.height = height * dpr;
    canvas!.style.width = `${width}px`;
    canvas!.style.height = `${height}px`;
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    seed();
    if (activeZone) updateAssignments(activeZone);
  }

  function seed(): void {
    particles.length = 0;
    const cols = Math.ceil(width / SPACING) + 1;
    const rows = Math.ceil(height / SPACING) + 1;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const homeX =
          c * SPACING - SPACING / 2 + (Math.random() - 0.5) * JITTER;
        const homeY =
          r * SPACING - SPACING / 2 + (Math.random() - 0.5) * JITTER;
        particles.push({
          homeX,
          homeY,
          x: homeX,
          y: homeY,
          vx: 0,
          vy: 0,
          baseAlpha: 0.32 + Math.random() * 0.18,
          radius: 0.7 + Math.random() * 0.55,
          phase: Math.random() * Math.PI * 2,
        });
      }
    }
  }

  function getColumnBox(
    side: 'left' | 'right',
  ): { left: number; right: number; cy: number; h: number } | null {
    const col = section!.querySelector<HTMLElement>(
      `[data-install-col="${side}"]`,
    );
    if (!col) return null;
    const sectionRect = section!.getBoundingClientRect();
    const r = col.getBoundingClientRect();
    // Visual midpoint, not geometric. The card stacks small-icon →
    // large-headline → hint → button, so the optical centre of mass is
    // ~15% below the rectangle's geometric centre. Using 0.65 of the
    // column height keeps the brace visually wrapped around the bulk
    // of the card (headline + button) instead of riding too high.
    return {
      left: r.left - sectionRect.left,
      right: r.right - sectionRect.left,
      cy: r.top - sectionRect.top + r.height * 0.62,
      h: r.height,
    };
  }

  function updateAssignments(zone: 'left' | 'right'): void {
    assignments.clear();
    const box = getColumnBox(zone);
    if (!box) return;

    // Brace wraps the whole column, not just the button — that's the
    // "huge bracket on each side of the content" look from the
    // reference image. Height = column height plus vertical padding,
    // floored so small viewports still get a generous shape.
    const braceHeight = Math.max(
      BRACE_MIN_HEIGHT,
      box.h + BRACE_VERTICAL_PADDING * 2,
    );
    const leftBraceCx = box.left - BRACE_OFFSET;
    const rightBraceCx = box.right + BRACE_OFFSET;
    const points: Point[] = [
      ...getBracePoints('{', leftBraceCx, box.cy, braceHeight),
      ...getBracePoints('}', rightBraceCx, box.cy, braceHeight),
    ];

    // Greedy nearest-neighbour: for each target point, claim the
    // nearest particle that hasn't been claimed yet. O(N×M) but N is
    // small (a few hundred particles) and M is bounded (~200 points)
    // and we only do this on zone change.
    const taken = new Set<number>();
    for (const point of points) {
      let nearest = -1;
      let bestDist = Infinity;
      for (let i = 0; i < particles.length; i++) {
        if (taken.has(i)) continue;
        const dx = particles[i].x - point.x;
        const dy = particles[i].y - point.y;
        const d = dx * dx + dy * dy;
        if (d < bestDist) {
          bestDist = d;
          nearest = i;
        }
      }
      if (nearest >= 0) {
        taken.add(nearest);
        assignments.set(nearest, point);
      }
    }
  }

  function determineZone(mx: number): 'left' | 'right' | null {
    if (!mouseInside || coarse) return null;
    const center = width / 2;
    if (mx < center - ZONE_DEADBAND) return 'left';
    if (mx > center + ZONE_DEADBAND) return 'right';
    return null;
  }

  function onPointerMove(e: PointerEvent): void {
    const rect = section!.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    mouseInside =
      e.clientX >= rect.left &&
      e.clientX < rect.right &&
      e.clientY >= rect.top &&
      e.clientY < rect.bottom;

    const newZone = determineZone(mouseX);
    if (newZone !== activeZone) {
      activeZone = newZone;
      if (newZone) {
        updateAssignments(newZone);
      } else {
        assignments.clear();
      }
    }
    void my;
  }

  function onPointerLeave(): void {
    mouseInside = false;
    if (activeZone) {
      activeZone = null;
      assignments.clear();
    }
  }

  function frame(now: number): void {
    const dt = Math.min(48, now - lastFrame);
    lastFrame = now;
    const tick = dt / 16;

    ctx!.clearRect(0, 0, width, height);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      const target = assignments.get(i);

      if (target) {
        // Living-shape effect: spring toward an OSCILLATING target.
        // Each particle has its own phase, so the brace shape stays
        // intact overall while individual points slowly orbit their
        // anchor — gives the formation a soft breathing motion instead
        // of a rigid still.
        const tx =
          target.x + Math.sin(now * BRACE_BREATH_FREQ + p.phase) * BRACE_BREATH_AMP;
        const ty =
          target.y +
          Math.cos(now * BRACE_BREATH_FREQ * 1.3 + p.phase * 1.7) *
            BRACE_BREATH_AMP;
        p.vx += (tx - p.x) * TARGET_SPRING_K;
        p.vy += (ty - p.y) * TARGET_SPRING_K;
      } else {
        p.vx += (p.homeX - p.x) * HOME_SPRING_K;
        p.vy += (p.homeY - p.y) * HOME_SPRING_K;
      }

      p.vx *= DAMPING;
      p.vy *= DAMPING;
      p.x += p.vx * tick;
      p.y += p.vy * tick;

      // Brace-bound particles glow brighter and slightly larger so the
      // formation reads as a discrete shape against the resting field.
      const alpha = target ? 0.95 : p.baseAlpha;
      const radius = target ? p.radius * 1.35 : p.radius;

      ctx!.fillStyle = `rgba(255, 255, 255, ${alpha})`;
      ctx!.beginPath();
      ctx!.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx!.fill();
    }

    rafId = requestAnimationFrame(frame);
  }

  resize();
  const ro = new ResizeObserver(() => resize());
  ro.observe(section);
  window.addEventListener('resize', resize);
  section.addEventListener('pointermove', onPointerMove, { passive: true });
  section.addEventListener('pointerleave', onPointerLeave);
  rafId = requestAnimationFrame(frame);

  return () => {
    cancelAnimationFrame(rafId);
    ro.disconnect();
    window.removeEventListener('resize', resize);
    section.removeEventListener('pointermove', onPointerMove);
    section.removeEventListener('pointerleave', onPointerLeave);
  };
}
