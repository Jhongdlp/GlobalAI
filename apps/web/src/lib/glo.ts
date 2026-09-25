import type { createCoach, Hat } from "./coach";

export type Coach = ReturnType<typeof createCoach>;

/** El sombrero que Glo gana con cada nivel MCER. */
export const hatFor = (level: string): Hat => (level === "C1" ? "grad" : level === "B1" || level === "B2" ? "bowler" : "party");

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const HELLOS = ["Hello!", "¡Hola!", "Bonjour!", "Ciao!", "Olá!", "Hallo!", "こんにちは", "Hej!", "Merhaba!", "안녕!"];
let helloIdx = 0;

/**
 * Escena de Glo compartida (login, dashboard…): carga Three.js en diferido, tipografía cinética,
 * ráfaga de "hola" al tocarlo y parallax sutil. Estilos en src/styles/glo.css.
 */
export function mountGlo(els: { canvas: HTMLCanvasElement; say: HTMLElement; sayEs: HTMLElement; scene: HTMLElement }) {
  let coach: Coach | undefined;

  function burst(e: MouseEvent) {
    coach?.say(0.8);
    if (reduced) return;
    const layer = document.createElement("div");
    const ring = document.createElement("span");
    ring.className = "hello-ring";
    ring.style.cssText = `left:${e.clientX}px;top:${e.clientY}px`;
    layer.append(ring);
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + (i - 2) * 0.55 + (Math.random() - 0.5) * 0.3;
      const d = 110 + Math.random() * 60;
      const w = document.createElement("span");
      w.className = "hello-pop";
      w.textContent = HELLOS[helloIdx++ % HELLOS.length];
      w.style.cssText = `left:${e.clientX}px;top:${e.clientY}px;--x:${Math.cos(a) * d}px;--y:${Math.sin(a) * d}px;--r:${(Math.random() - 0.5) * 30}deg;animation-delay:${i * 40}ms`;
      layer.append(w);
    }
    document.body.append(layer);
    setTimeout(() => layer.remove(), 1400);
  }

  // Parallax: el texto y la comilla se mueven un poco al contrario del puntero → profundidad.
  // Una escritura por frame como mucho: cada cambio de variable recalcula estilos de toda la escena.
  if (!reduced) {
    let px = 0, py = 0, queued = false;
    addEventListener(
      "pointermove",
      (e) => {
        px = (e.clientX / innerWidth) * 2 - 1;
        py = (e.clientY / innerHeight) * 2 - 1;
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => {
          queued = false;
          els.scene.style.setProperty("--px", px.toFixed(2));
          els.scene.style.setProperty("--py", py.toFixed(2));
        });
      },
      { passive: true },
    );
  }

  // Three.js se carga después: la página funciona desde el primer instante.
  // La entrada (glo-in) espera a Glo: si no, se anima un canvas vacío y Glo aparece de golpe al final.
  els.canvas.style.animationPlayState = "paused";
  const ready = import("./coach")
    .then(({ createCoach }) => {
      coach = createCoach(els.canvas);
      coach.onPoke(burst);
      requestAnimationFrame(() => (els.canvas.style.animationPlayState = "")); // tras el primer frame pintado
      return coach;
    })
    .catch(() => {
      els.canvas.remove(); // sin WebGL: queda la tipografía
      return undefined;
    });

  let last = "";
  return {
    get coach() {
      return coach;
    },
    /** Se resuelve cuando Glo ya está en pantalla (undefined si no hay WebGL). */
    ready,
    /** Tipografía cinética: cada palabra sube desde una máscara mientras Glo mueve la boca. *palabra* = coral. */
    speak(en: string, es: string) {
      if (en === last) return;
      last = en;
      els.say.replaceChildren();
      en.split(" ").forEach((word, i) => {
        const mask = document.createElement("span");
        const w = document.createElement("span");
        mask.className = "w";
        w.textContent = word.replaceAll("*", "");
        if (word.startsWith("*")) w.className = "hi";
        w.style.setProperty("--i", String(i));
        mask.append(w);
        els.say.append(mask, " ");
      });
      els.sayEs.textContent = es;
      els.sayEs.classList.remove("in");
      void els.sayEs.offsetWidth; // reinicia la animación
      els.sayEs.classList.add("in");
      coach?.say(0.5 + en.split(" ").length * 0.22);
    },
  };
}

let audioCtx: AudioContext | undefined;

/**
 * Volumen real de un <audio> (Web Audio) en cada frame → onLevel(0..1). Sirve para que Glo "diga" un audio.
 * El audio debe ser del mismo origen (o blob:), si no el analizador solo recibe silencio.
 * start() devuelve false si no hay Web Audio: quien llama decide un plan B (p. ej. coach.say()).
 */
export function audioLevel(audio: HTMLAudioElement, onLevel: (level: number) => void) {
  let raf = 0;
  let analyser: AnalyserNode | undefined;
  try {
    audioCtx ??= new AudioContext();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    audioCtx.createMediaElementSource(audio).connect(analyser);
    analyser.connect(audioCtx.destination);
  } catch {
    analyser = undefined;
  }
  const buf = new Uint8Array(512);
  const loop = () => {
    analyser!.getByteTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += ((v - 128) / 128) ** 2;
    onLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4.5));
    raf = requestAnimationFrame(loop);
  };
  return {
    start() {
      if (!analyser) return false;
      audioCtx!.resume();
      cancelAnimationFrame(raf);
      loop();
      return true;
    },
    stop() {
      cancelAnimationFrame(raf);
      onLevel(0);
    },
  };
}

/** Volumen del micrófono en cada frame → onLevel(0..1). Devuelve la función que lo detiene. */
export function micLevel(stream: MediaStream, onLevel: (v: number) => void) {
  try {
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Uint8Array(512);
    let raf = 0;
    const loop = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      onLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4.5));
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      cancelAnimationFrame(raf);
      onLevel(0);
      ctx.close();
    };
  } catch {
    return () => {};
  }
}
