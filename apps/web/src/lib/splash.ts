import type { Coach } from "./glo";

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const SPEED = reduced ? 100 : 0.7; // progreso mostrado por segundo: el llenado se lee aunque todo cargue al instante

/**
 * Pantalla de carga: Glo aparece en gris y se va llenando de color según el progreso real.
 * word: la palabra animada ("Loading", "Grading"…); null = no mostrar (mismas llamadas, sin efecto).
 * Devuelve progress(0..1), done() y cancel().
 * Estilos en src/styles/glo.css (.splash).
 */
export function splash(word: string | null, from = 0) {
  const reveal = () => document.documentElement.classList.remove("splashing"); // ver Base.astro
  if (!word) return reveal(), { progress() {}, done: async () => {}, cancel() {} };

  const el = document.createElement("div");
  el.className = "splash";
  el.setAttribute("role", "status");
  el.innerHTML = `<canvas aria-hidden="true"></canvas>
    <p class="splash-word" aria-hidden="true">${[...word].map((c, i) => `<span style="--i:${i}">${c === " " ? "&nbsp;" : c}</span>`).join("")}</p>
    <p class="splash-pct" aria-hidden="true">0%</p>
    <span class="sr-only">Cargando…</span>`;
  el.querySelector(".splash-word")!.setAttribute("lang", "en");
  document.body.append(el);
  reveal();
  const pct = el.querySelector<HTMLElement>(".splash-pct")!;
  let target = from; // progreso real (from: donde lo dejó la página anterior)
  let shown = from; // progreso mostrado: persigue al real a velocidad legible
  let coach: Coach | undefined;
  let finish: (() => void) | undefined;
  let started = false; // el llenado arranca cuando Glo ya se ve (o si no hay WebGL)
  let last = performance.now();
  const tick = (now: number) => {
    if (started) shown = Math.min(target, shown + ((now - last) / 1000) * SPEED);
    last = now;
    coach?.fill(shown);
    pct.textContent = `${Math.round(shown * 100)}%`;
    if (shown >= 1 && finish) return finish();
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);

  // Three.js llega en diferido: mientras tanto se ve la palabra; Glo aparece gris al estar listo.
  const ready = import("./coach")
    .then(({ createCoach }) => {
      coach = createCoach(el.querySelector("canvas")!);
      coach.setState("loading"); // mira arriba pensando, con los "…" sobre la cabeza
      coach.fill(shown);
      el.classList.add("has-glo");
    })
    .catch(() => {})
    .finally(() => (started = true));

  const progress = (p: number) => {
    target = Math.max(target, Math.min(1, p));
  };

  return {
    progress,
    /** Quita la pantalla al instante (p. ej. si falló el envío y el usuario debe seguir en la página). */
    cancel() {
      finish = () => {};
      target = shown = 1;
      coach?.destroy();
      el.remove();
    },
    /** Termina: llena del todo, Glo celebra y la pantalla se desvanece. */
    async done() {
      await ready;
      progress(1);
      await new Promise<void>((r) => (finish = r)); // espera a que el llenado llegue a 100%
      coach?.setState("success");
      await new Promise((r) => setTimeout(r, reduced ? 0 : 750));
      el.classList.add("out");
      await new Promise((r) => setTimeout(r, reduced ? 0 : 500));
      coach?.destroy();
      el.remove();
    },
  };
}

// Cuándo mostrarla: la primera visita de la sesión y al pasar de una página a otra que sigue cargando
// (login → dashboard, envío de la evaluación → resultados), con la misma palabra en ambas.
const store = <T,>(fn: () => T, fallback: T) => {
  try {
    return fn();
  } catch {
    return fallback; // sin sessionStorage (modo privado estricto): sin pantalla de carga
  }
};
export const firstVisit = () =>
  store(() => {
    const first = !sessionStorage.getItem("ga:seen");
    sessionStorage.setItem("ga:seen", "1");
    return first ? "Loading" : null;
  }, null);
export const handoff = {
  /** La página siguiente abrirá la pantalla con esta palabra, empezando en `from`. */
  mark: (word: string, from = 0) => store(() => sessionStorage.setItem("ga:splash", `${from}|${word}`), undefined),
  /** Para pasar directo a splash(...handoff.take()). */
  take: (): [string | null, number] =>
    store(() => {
      const v = sessionStorage.getItem("ga:splash");
      sessionStorage.removeItem("ga:splash");
      if (!v) return [null, 0];
      const [from, ...word] = v.split("|");
      return [word.join("|"), Number(from) || 0];
    }, [null, 0]),
};
