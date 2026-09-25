import { audioLevel, type mountGlo } from "./glo";

/**
 * Escenario de voz de Glo (resultados y dashboard): la página se atenúa, el lienzo vuela (FLIP) al
 * centro y crece, anillos con el volumen real, subtítulos aproximados y controles.
 * Pistas en secuencia; una pista con `card` hace que Glo gire y presente esa tarjeta (se clona).
 * Estilos en src/styles/glo.css (.spotlight). Lo que se marque con [data-stage-hide] no se clona visible.
 */
export type Track = { audio: HTMLAudioElement; text: string; card?: HTMLElement; intro?: [string, string] };
type Glo = ReturnType<typeof mountGlo>;

const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"></path></svg>';
const PAUSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"></rect><rect x="14" y="5" width="4" height="14" rx="1"></rect></svg>';
const CLOSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>';
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Vuelo FLIP del lienzo de Glo hasta el anillo del escenario y de regreso. */
function flier(glo: Glo, canvas: HTMLCanvasElement) {
  let flight: Animation | null = null;
  let at = "none"; // transform actual del lienzo
  let home: DOMRect; // posición del lienzo en la página, sin transformar
  return {
    get away() {
      return at !== "none";
    },
    /** Antes de abrir: mide desde dónde sale (cancela un regreso a medias). */
    reset() {
      flight?.cancel();
      at = "none";
      home = canvas.getBoundingClientRect();
    },
    // Con arco y giro a mitad de camino en el primer vuelo.
    fly(to: string, mid?: string) {
      flight?.cancel();
      const frames = mid ? [{ transform: at }, { transform: mid }, { transform: to }] : [{ transform: at }, { transform: to }];
      flight = canvas.animate(frames, { duration: reduced ? 0 : 800, easing: "cubic-bezier(0.34, 1.2, 0.64, 1)", fill: "forwards" });
      at = to;
      return flight.finished.catch(() => {});
    },
    toRing(layer: HTMLElement) {
      const r = layer.querySelector(".sp-ring")!.getBoundingClientRect();
      const sc = r.width / home.width;
      const dx = r.left + r.width / 2 - (home.left + home.width / 2);
      const dy = r.top + r.height / 2 - (home.top + home.height / 2);
      glo.coach?.sharpness(Math.max(sc, 1));
      return { to: `translate(${dx}px, ${dy}px) scale(${sc})`, mid: `translate(${dx / 2}px, ${dy / 2 - 60}px) scale(${(1 + sc) / 2}) rotate(-8deg)` };
    },
    /** Regreso a la página; al aterrizar, Glo vuelve a su tamaño (si no se reabrió en el aire). */
    land(stillClosed: () => boolean) {
      this.fly("none").then(() => {
        if (!stillClosed()) return;
        flight?.cancel();
        canvas.classList.remove("center-stage");
        glo.coach?.sharpness(1);
        glo.coach?.setState("idle");
      });
    },
  };
}

export function createStage(glo: Glo, canvas: HTMLCanvasElement, tracks: Track[], onClose?: () => void) {
  const cues = tracks.map(({ text }) => {
    const t = text.replace(/\s+/g, " ").trim();
    const sentences = t.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [t];
    return { sentences, ends: sentences.map((_, i) => sentences.slice(0, i + 1).join("").length / t.length) };
  });
  let idx = 0; // pista que suena
  let layer: HTMLElement | null = null;
  let trigger: HTMLElement | null = null; // botón que abrió el escenario (aria-pressed, foco al cerrar)
  const f = flier(glo, canvas);
  const audio = () => tracks[idx].audio;
  const setAmp = (v: number) => {
    glo.coach?.voice(v);
    layer?.style.setProperty("--amp", v.toFixed(3));
  };
  const lips = tracks.map((t) => audioLevel(t.audio, setAmp));

  // Glo se hace a un lado y presenta la tarjeta (acto 2).
  function showCard(card: HTMLElement) {
    if (!layer || layer.classList.contains("act2")) return false;
    const clone = card.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
    clone.removeAttribute("id");
    clone.hidden = false;
    clone.classList.add("sp-rec");
    layer.querySelector(".sp-caption")!.before(clone);
    layer.classList.add("act2");
    glo.coach?.setState("present");
    return true;
  }

  function play(i: number, delay: number) {
    idx = i;
    const t = tracks[i];
    t.audio.currentTime = 0;
    if (t.card && showCard(t.card) && f.away) f.fly(f.toRing(layer!).to);
    if (t.intro) glo.speak(...t.intro);
    layer?.querySelector<HTMLElement>(".sp-track span")?.style.setProperty("width", "0");
    setTimeout(() => layer && idx === i && t.audio.play(), reduced ? 0 : delay);
  }

  function open(from: number, button: HTMLElement) {
    if (layer) return;
    trigger = button;
    layer = document.createElement("div");
    layer.className = "spotlight";
    layer.innerHTML = `<div class="sp-ring" aria-hidden="true"></div>
      <p class="sp-caption" aria-live="off"></p>
      <div class="sp-ui">
        <button type="button" class="sp-toggle" aria-label="Pausar">${PAUSE}</button>
        <div class="sp-track" aria-hidden="true"><span></span></div>
        <button type="button" class="sp-close" aria-label="Cerrar">${CLOSE}</button>
      </div>`;
    document.body.append(layer);
    layer.addEventListener("click", (e) => e.target === layer && close());
    layer.querySelector(".sp-close")!.addEventListener("click", close);
    layer.querySelector(".sp-toggle")!.addEventListener("click", () => (audio().paused ? audio().play() : audio().pause()));
    addEventListener("keydown", onKey);
    requestAnimationFrame(() => layer?.classList.add("on"));

    f.reset(); // por si se reabre durante el vuelo de regreso
    canvas.classList.add("center-stage");
    glo.coach?.setState("idle");
    play(from, 750); // si la pista trae tarjeta, se muestra antes de medir el anillo
    const { to, mid } = f.toRing(layer);
    f.fly(to, mid);
    trigger.setAttribute("aria-pressed", "true");
  }

  function close() {
    if (!layer) return;
    audio().pause();
    const l = layer;
    layer = null;
    l.classList.remove("on");
    removeEventListener("keydown", onKey);
    f.land(() => !layer); // si se reabrió mientras volvía, sigue en escena
    setTimeout(() => l.remove(), 500);
    trigger?.setAttribute("aria-pressed", "false");
    trigger?.focus();
    onClose?.();
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") close();
    if (e.key === " " && layer && !(e.target instanceof HTMLAnchorElement)) {
      e.preventDefault();
      audio().paused ? audio().play() : audio().pause();
    }
  };

  tracks.forEach((t, i) => {
    const a = t.audio;
    a.addEventListener("play", () => {
      if (!lips[i].start()) glo.coach?.say(a.duration || 10);
      const b = layer?.querySelector(".sp-toggle");
      if (b) (b.innerHTML = PAUSE), b.setAttribute("aria-label", "Pausar");
    });
    a.addEventListener("pause", () => {
      lips[i].stop();
      glo.coach?.say(0);
      const b = layer?.querySelector(".sp-toggle");
      if (b) (b.innerHTML = PLAY), b.setAttribute("aria-label", "Reproducir");
    });
    a.addEventListener("timeupdate", () => {
      if (!layer || !a.duration || idx !== i) return;
      const k = a.currentTime / a.duration;
      layer.querySelector<HTMLElement>(".sp-track span")!.style.width = `${k * 100}%`;
      const { sentences, ends } = cues[i];
      const cap = layer.querySelector<HTMLElement>(".sp-caption")!;
      const n = ends.findIndex((e) => e >= k);
      const line = sentences[n < 0 ? sentences.length - 1 : n].trim();
      if (cap.textContent !== line) {
        cap.textContent = line;
        cap.classList.remove("in");
        void cap.offsetWidth;
        cap.classList.add("in");
      }
    });
    // Fin de pista: sigue la próxima sin corte; al final, si hay tarjeta el escenario se queda
    // con ella y su botón (momento de decidir); si no, Glo se despide y cierra.
    a.addEventListener("ended", () => {
      if (!layer || idx !== i) return;
      if (tracks[i + 1]) return play(i + 1, 900);
      glo.coach?.setState("success");
      glo.speak("You've *got* this!", "¡Tú puedes!");
      const cta = layer.querySelector<HTMLElement>(".sp-rec a");
      if (cta) cta.focus();
      else setTimeout(close, reduced ? 0 : 900);
    });
  });

  return {
    open,
    close,
    get isOpen() {
      return !!layer;
    },
  };
}

/**
 * Escenario interactivo (práctica de pronunciación): mismo velo y vuelo, pero Glo se queda a un lado
 * y a su derecha va `panel`, el elemento real (no una copia), que vuelve a su sitio al cerrar.
 * Glo habla con subtítulos (caption) y los anillos siguen el volumen que se le pase (amp).
 */
export function createPanelStage(glo: Glo, canvas: HTMLCanvasElement, panel: HTMLElement, onClose?: () => void) {
  let layer: HTMLElement | null = null;
  let trigger: HTMLElement | null = null;
  const f = flier(glo, canvas);
  const home = { parent: panel.parentElement!, next: panel.nextSibling };
  const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();

  function open(button: HTMLElement) {
    if (layer) return;
    trigger = button;
    layer = document.createElement("div");
    layer.className = "spotlight act2 sp-live";
    layer.setAttribute("role", "dialog");
    layer.setAttribute("aria-modal", "true");
    layer.setAttribute("aria-label", "Práctica de pronunciación con Glo");
    layer.innerHTML = '<div class="sp-ring" aria-hidden="true"></div><p class="sp-caption" aria-live="polite"></p>';
    panel.classList.add("sp-rec");
    panel.hidden = false;
    layer.append(panel);
    document.body.append(layer);
    addEventListener("keydown", onKey);
    requestAnimationFrame(() => layer?.classList.add("on"));
    f.reset();
    canvas.classList.add("center-stage");
    const { to, mid } = f.toRing(layer);
    f.fly(to, mid);
  }

  function close() {
    if (!layer) return;
    const l = layer;
    layer = null;
    l.classList.remove("on");
    removeEventListener("keydown", onKey);
    f.land(() => !layer);
    setTimeout(() => {
      if (!layer) {
        // de vuelta a su sitio (oculto) si no se reabrió mientras se desvanecía
        panel.hidden = true;
        panel.classList.remove("sp-rec");
        home.parent.insertBefore(panel, home.next);
      }
      l.remove();
    }, 450);
    trigger?.focus();
    onClose?.();
  }

  return {
    open,
    close,
    get isOpen() {
      return !!layer;
    },
    amp(v: number) {
      layer?.style.setProperty("--amp", v.toFixed(3));
    },
    /** Lo que Glo dice, como subtítulo: *palabra* resaltada y, debajo, la traducción. */
    caption(en: string, es = "") {
      const cap = layer?.querySelector<HTMLElement>(".sp-caption");
      if (!cap) return;
      const hi = (t: string) => t.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`).replace(/\*([^*]+)\*/g, "<em>$1</em>");
      cap.innerHTML = hi(en) + (es ? `<small>${hi(es)}</small>` : "");
      cap.classList.remove("in");
      void cap.offsetWidth; // reinicia la animación
      cap.classList.add("in");
    },
  };
}
