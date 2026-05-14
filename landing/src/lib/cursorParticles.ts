/**
 * Particle field that lays a uniform grid of dots across the viewport.
 * Every particle has a fixed "home" position (its grid cell). Two forces
 * drive each particle every frame:
 *
 *   1. A spring back to its home — keeps the field uniform at rest.
 *   2. Cursor repulsion within MOUSE_RADIUS — pushes particles outward
 *      from the cursor so a soft "well" follows the mouse.
 *
 * When the cursor leaves a region, the spring snaps the particles back to
 * their home grid. There's no flow field, no ring formation, no global
 * drift — the field is otherwise still, which is exactly what the brief
 * asked for ("均匀铺满 → 鼠标推开 → 鼠标移走后回到原位").
 *
 * Constraints:
 *   - On coarse-pointer devices we still render the grid, but the cursor
 *     repulsion term turns off (no mouse to react to).
 */

interface Particle {
  homeX: number;
  homeY: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Per-particle baseline alpha jitter, so the grid doesn't look mechanical. */
  baseAlpha: number;
  /** Per-particle baseline radius jitter, same reason. */
  radius: number;
}

const SPACING = 56;            // px between grid cells
const JITTER = 6;              // random offset on home position
const HOME_SPRING_K = 0.05;    // how hard the spring snaps a particle home
const DAMPING = 0.84;          // velocity decay per frame
const MOUSE_RADIUS = 150;
// Squared falloff so the push is strongest right at the cursor and tapers
// gracefully out to MOUSE_RADIUS — feels like a pressure bubble, not a
// hard collider.
const MOUSE_FORCE = 2.6;

export function initCursorParticles(canvas: HTMLCanvasElement): () => void {
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return () => {};

  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const coarse = window.matchMedia('(pointer: coarse)').matches;

  let width = 0;
  let height = 0;
  const particles: Particle[] = [];
  let mouseX = -10000;
  let mouseY = -10000;
  let mouseInside = false;
  let rafId = 0;
  let lastFrame = performance.now();

  function resize(): void {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    seed();
  }

  function seed(): void {
    particles.length = 0;
    // Half-step inset so the grid doesn't hug the edges.
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
          baseAlpha: 0.16 + Math.random() * 0.1,
          radius: 1.0 + Math.random() * 0.7,
        });
      }
    }
  }

  function onPointerMove(e: PointerEvent): void {
    mouseX = e.clientX;
    mouseY = e.clientY;
    mouseInside = true;
  }

  function onPointerLeave(): void {
    mouseInside = false;
  }

  function frame(now: number): void {
    const dt = Math.min(48, now - lastFrame);
    lastFrame = now;
    const tick = dt / 16; // normalize to "60fps frame units"

    ctx!.clearRect(0, 0, width, height);
    ctx!.globalCompositeOperation = 'multiply';

    const useCursor = mouseInside && !coarse;

    for (const p of particles) {
      // Cursor repulsion (only inside the radius, only when cursor present).
      if (useCursor) {
        const dx = p.x - mouseX;
        const dy = p.y - mouseY;
        const distSq = dx * dx + dy * dy;
        if (distSq < MOUSE_RADIUS * MOUSE_RADIUS && distSq > 1) {
          const dist = Math.sqrt(distSq);
          const norm = (MOUSE_RADIUS - dist) / MOUSE_RADIUS;
          const push = norm * norm * MOUSE_FORCE;
          p.vx += (dx / dist) * push;
          p.vy += (dy / dist) * push;
        }
      }

      // Spring back home — Hooke's law, force proportional to displacement.
      p.vx += (p.homeX - p.x) * HOME_SPRING_K;
      p.vy += (p.homeY - p.y) * HOME_SPRING_K;

      p.vx *= DAMPING;
      p.vy *= DAMPING;
      p.x += p.vx * tick;
      p.y += p.vy * tick;

      // Render: the more displaced from home, the brighter — gives the
      // mouse-pushed band a subtle highlight against the at-rest field.
      const ddx = p.x - p.homeX;
      const ddy = p.y - p.homeY;
      const displacement = Math.sqrt(ddx * ddx + ddy * ddy);
      const alpha = p.baseAlpha + Math.min(0.4, displacement * 0.013);

      ctx!.fillStyle = `rgba(10, 10, 10, ${alpha})`;
      ctx!.beginPath();
      ctx!.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx!.fill();
    }

    rafId = requestAnimationFrame(frame);
  }

  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('pointermove', onPointerMove, { passive: true });
  window.addEventListener('pointerleave', onPointerLeave);
  rafId = requestAnimationFrame(frame);

  return () => {
    cancelAnimationFrame(rafId);
    window.removeEventListener('resize', resize);
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerleave', onPointerLeave);
  };
}
