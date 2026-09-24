import * as THREE from "three";

export type CoachState = "idle" | "email" | "password" | "peek" | "loading" | "error" | "success";

// Glo: un globo de diálogo con vida (hablar = aprender idiomas). Cel shading + contorno de tinta (como los bordes de la UI).
// Pose = números que se interpolan cada frame → todas las transiciones salen suaves "gratis".
// yaw/pitch/tilt: giro del cuerpo · gx/gy: pupilas · eyeL/eyeR: párpados (1 abierto)
// brow: cejas arriba/abajo · browAng: + preocupado, − enojado · smile: −1 triste … 1 feliz · open: boca "o" · grin: sonrisa abierta "D" · wag: mueve la colita
// l*/r*: posición de cada mano (flotantes, sin brazos)
type Pose = Record<
  "yaw" | "pitch" | "tilt" | "gx" | "gy" | "eyeL" | "eyeR" | "brow" | "browAng" | "smile" | "open" | "grin" | "wag" | "lx" | "ly" | "lz" | "rx" | "ry" | "rz",
  number
>;

const REST = { lx: -1.3, ly: -0.25, lz: 0.25, rx: 1.3, ry: -0.25, rz: 0.25 };
const COVER = { lx: -0.34, ly: 0.2, lz: 1.2, rx: 0.34, ry: 0.2, rz: 1.2 }; // tapa los ojos
const TYPE = { lx: -0.5, ly: -0.72, lz: 0.8, rx: 0.5, ry: -0.72, rz: 0.8 }; // "teclea" contigo
const CHEER = { lx: -1.3, ly: 0.8, lz: 0.2, rx: 1.3, ry: 0.8, rz: 0.2 };

const POSES: Record<CoachState, Pose> = {
  idle: { yaw: 0, pitch: 0, tilt: 0, gx: 0, gy: 0, eyeL: 1, eyeR: 1, brow: 0, browAng: 0, smile: 0.8, open: 0, grin: 0.45, wag: 0.1, ...REST },
  email: { yaw: 0.4, pitch: 0.15, tilt: 0.1, gx: 0, gy: -0.5, eyeL: 1, eyeR: 1, brow: 0.3, browAng: 0, smile: 0.9, open: 0, grin: 0.3, wag: 0.4, ...TYPE },
  password: { yaw: -0.18, pitch: -0.2, tilt: -0.12, gx: -1, gy: 0.3, eyeL: 0, eyeR: 0, brow: -0.2, browAng: 0.4, smile: 0.3, open: 0, grin: 0, wag: 0, ...COVER },
  peek: { yaw: 0.2, pitch: 0.05, tilt: 0.14, gx: 0.8, gy: -0.3, eyeL: 0, eyeR: 1, brow: 0.9, browAng: 0.2, smile: 0.2, open: 0.8, grin: 0, wag: 0, ...COVER, rx: 1.15, ry: -0.35, rz: 0.7 },
  loading: { yaw: 0, pitch: -0.1, tilt: 0, gx: 0, gy: 0.8, eyeL: 1, eyeR: 1, brow: 0.4, browAng: 0.1, smile: 0.1, open: 0.45, grin: 0, wag: 0, ...REST },
  error: { yaw: 0, pitch: 0.1, tilt: -0.08, gx: 0, gy: -0.2, eyeL: 1, eyeR: 1, brow: -0.1, browAng: 0.9, smile: -0.7, open: 0, grin: 0, wag: 0, ...REST, ly: -0.1, ry: -0.1 },
  success: { yaw: 0, pitch: -0.1, tilt: 0, gx: 0, gy: 0, eyeL: 1, eyeR: 1, brow: 0.8, browAng: 0, smile: 1, open: 0, grin: 1, wag: 1, ...CHEER },
};

const RED = "#ff4b3a"; // coral propio de Glo
const CREAM = "#fff4e0";
const SHAPE = new THREE.Vector3(1.12, 0.9, 0.88); // esfera → globo de diálogo "gordito"
const INK = "#1f1b16";
const BROW_ARC = 1.3;

const onSphere = (lat: number, lon: number, r = 1) => {
  const a = THREE.MathUtils.degToRad(lat), o = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(Math.cos(a) * Math.sin(o), Math.sin(a), Math.cos(a) * Math.cos(o)).multiplyScalar(r);
};

export function createCoach(canvas: HTMLCanvasElement) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 30);
  camera.position.set(0, 0.15, 6.0);
  scene.add(new THREE.AmbientLight("#fff", 1.4));
  const sun = new THREE.DirectionalLight("#fff", 2.2);
  sun.position.set(-2.5, 3.5, 4);
  scene.add(sun);
  const rim = new THREE.DirectionalLight("#ffd6a8", 2.4); // contraluz cálido: separa a Glo del fondo
  rim.position.set(3, 1.5, -4);
  scene.add(rim);

  // 3 tonos duros = look de caricatura.
  const ramp = new THREE.DataTexture(new Uint8Array([90, 170, 255]), 3, 1, THREE.RedFormat);
  ramp.minFilter = ramp.magFilter = THREE.NearestFilter;
  ramp.needsUpdate = true;
  const toon = (color: string) => new THREE.MeshToonMaterial({ color, gradientMap: ramp });
  const flat = (color: string) => new THREE.MeshBasicMaterial({ color });
  const outlineMat = new THREE.MeshBasicMaterial({ color: INK, side: THREE.BackSide });

  // Contorno de tinta: casco invertido (copia un poco más grande, caras traseras en negro).
  function part(geo: THREE.BufferGeometry, mat: THREE.Material, thick = 0.045) {
    const mesh = new THREE.Mesh(geo, mat);
    const hull = new THREE.Mesh(geo, outlineMat);
    hull.scale.setScalar(1 + thick);
    mesh.add(hull);
    return mesh;
  }
  // Pega un objeto a la superficie (esfera unitaria del grupo "face") mirando hacia afuera.
  function stick(obj: THREE.Object3D, lat: number, lon: number, r: number) {
    obj.position.copy(onSphere(lat, lon, r));
    obj.lookAt(obj.position.clone().multiplyScalar(2));
    return obj;
  }

  const root = new THREE.Group(); // salta
  scene.add(root);
  const body = new THREE.Group(); // gira, respira, se aplasta
  root.add(body);

  const redMat = toon(RED);
  const blob = part(new THREE.SphereGeometry(1, 64, 40), redMat, 0.04);
  blob.scale.copy(SHAPE);
  body.add(blob);
  // Colita del globo de diálogo… que es su cola de verdad: la mueve cuando está contento.
  const tail = new THREE.Group();
  tail.position.set(-0.45, -0.55, 0.1);
  tail.rotation.z = 2.55;
  const tailCone = part(new THREE.ConeGeometry(0.3, 0.7, 24), redMat, 0.06);
  tailCone.position.y = 0.35;
  tail.add(tailCone);
  body.add(tail);

  // Rasgo firma: un mechón con forma de comillas (“) que rebota con resorte.
  const quotes = new THREE.Group();
  quotes.position.set(0.05, 0.84, 0.18);
  const creamMat = toon(CREAM);
  for (const x of [-0.15, 0.15]) {
    const comma = new THREE.Group();
    comma.position.x = x;
    comma.add(part(new THREE.SphereGeometry(0.13, 20, 14), creamMat, 0.1));
    const flick = part(new THREE.ConeGeometry(0.1, 0.2, 16), creamMat, 0.12);
    flick.position.set(-0.06, 0.15, 0);
    flick.rotation.z = 0.55;
    comma.add(flick);
    quotes.add(comma);
  }
  body.add(quotes);
  // La cara vive en el mismo espacio aplastado que el cuerpo, así se pega a la superficie.
  const face = new THREE.Group();
  face.scale.copy(SHAPE);
  body.add(face);

  // Ojos: todo vive en el espacio del ojo (esfera unitaria aplastada) → pupilas ovaladas.
  // Sin párpados: cerrar = aplastar el ojo en Y (queda una rayita).
  const pupilMat = flat(INK);
  const eyes = [-1, 1].map((side) => {
    const ball = stick(new THREE.Group(), 9, 16.5 * side, 0.93);
    ball.scale.set(0.22, 0.27, 0.14);
    ball.add(part(new THREE.SphereGeometry(1, 28, 18), flat("#fff"), 0.1));
    const pupil = new THREE.Group();
    pupil.add(new THREE.Mesh(new THREE.CircleGeometry(0.66, 28), flat("#4a2a1a"))); // iris café cálido
    const core = new THREE.Mesh(new THREE.CircleGeometry(0.44, 24), pupilMat);
    core.position.z = 0.004;
    pupil.add(core);
    for (const [x, y, r] of [[0.2, 0.24, 0.22], [-0.2, -0.22, 0.09]]) {
      const shine = new THREE.Mesh(new THREE.CircleGeometry(r, 16), flat("#fff"));
      shine.position.set(x, y, 0.01);
      pupil.add(shine);
    }
    ball.add(pupil);
    return { ball, pupil, side };
  });

  const brows = [-1, 1].map((side) => {
    const g = stick(new THREE.Group(), 31, 17 * side, 1.01);
    const bar = new THREE.Mesh(new THREE.TorusGeometry(0.13, 0.036, 8, 16, BROW_ARC), pupilMat); // arco suave = amable
    bar.rotation.z = Math.PI / 2 - BROW_ARC / 2;
    bar.position.y = -0.1;
    g.add(bar);
    return { g, bar, side, base: g.position.clone() };
  });

  // Brillo de caricatura arriba a la izquierda: vende el volumen "de juguete".
  const gloss = stick(new THREE.Mesh(new THREE.CircleGeometry(0.16, 24), new THREE.MeshBasicMaterial({ color: "#fff", transparent: true, opacity: 0.55 })), 46, -42, 1.006);
  gloss.scale.set(1.4, 0.7, 1);
  gloss.rotateZ(0.5);
  face.add(gloss);
  for (const side of [-1, 1]) {
    const blush = stick(new THREE.Mesh(new THREE.CircleGeometry(0.13, 20), new THREE.MeshBasicMaterial({ color: "#ff9d8c", transparent: true, opacity: 0.9 })), -7, 35 * side, 1.006);
    blush.scale.y = 0.6;
    face.add(blush);
  }

  // Boca: UNA sola forma (dos curvas entre las comisuras) que se regenera → sonrisa, "D", "o" y tristeza
  // son la misma pieza y nunca se superponen.
  const mouth = stick(new THREE.Group(), -14, 0, 1.02);
  const mouthMesh = new THREE.Mesh(new THREE.BufferGeometry(), flat("#4a120e"));
  const tongue = new THREE.Mesh(new THREE.CircleGeometry(1, 20), flat("#ff8f86"));
  tongue.position.z = 0.002;
  mouth.add(mouthMesh, tongue);
  const lips = new THREE.Shape();
  function shapeMouth(smile: number, round: number, open: number) {
    const w = 0.17 - round * 0.09; // "o" = más estrecha
    const cy = smile * 0.05; // comisuras arriba al sonreír
    const top = -smile * 0.07 + round * 0.12;
    const bottom = top - 0.05 - open * 0.34;
    lips.curves.length = 0;
    lips.moveTo(-w, cy).quadraticCurveTo(0, top, w, cy).quadraticCurveTo(0, bottom, -w, cy);
    mouthMesh.geometry.dispose();
    mouthMesh.geometry = new THREE.ShapeGeometry(lips, 10); // ponytail: ~40 vértices por frame, barato
    const r = Math.max(0, open - 0.25) * 0.09;
    tongue.scale.set(r * 1.3, r, 1);
    tongue.position.y = (cy + bottom) / 2 - r * 0.2;
  }
  face.add(mouth, ...eyes.map((e) => e.ball), ...brows.map((b) => b.g));

  // Manos flotantes (sin brazos, estilo caricatura).
  const handGeo = new THREE.SphereGeometry(0.24, 24, 16);
  const thumbGeo = new THREE.SphereGeometry(0.09, 16, 12);
  const hands = [-1, 1].map((side) => {
    const h = part(handGeo, redMat);
    h.scale.set(1, 0.9, 0.8);
    const thumb = part(thumbGeo, redMat, 0.12); // pulgar: la bola pasa a leerse como manopla
    thumb.position.set(-side * 0.16, 0.13, 0.1);
    h.add(thumb);
    body.add(h);
    return h;
  });

  // "Escribiendo…": tres puntos que rebotan sobre la cabeza mientras carga.
  const dotMat = toon(CREAM);
  const dots = [-1, 0, 1].map((i) => {
    const d = part(new THREE.SphereGeometry(0.1, 16, 12), dotMat, 0.14);
    d.position.set(i * 0.3, 1.25, 0.3);
    d.scale.setScalar(0);
    root.add(d);
    return d;
  });

  const shadow = new THREE.Mesh(new THREE.CircleGeometry(1, 32), new THREE.MeshBasicMaterial({ color: "#000", transparent: true, opacity: 0.3 }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -1.35;
  scene.add(shadow);

  function resize() {
    const { clientWidth: w, clientHeight: h } = canvas;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  let state: CoachState = "idle";
  let target = POSES.idle;
  const cur: Pose = { ...POSES.idle };
  let caret = 0.5; // 0..1: dónde está el cursor en el correo → las pupilas lo siguen
  let talk = 0; // segundos que le quedan "hablando" (boca animada)
  let jump = 0, shake = 0, tap = 0, tapSide = 1, blink = 0, nextBlink = 2;
  let wave = reduced ? 0 : 2.2; // saluda al aparecer
  let pointerX = 0, pointerY = 0, t = 0;
  let qa = 0, qv = 0, prevY = 0, prevVy = 0; // resorte del mechón
  let last = performance.now();

  const onPointer = (e: PointerEvent) => {
    pointerX = (e.clientX / innerWidth) * 2 - 1;
    pointerY = (e.clientY / innerHeight) * 2 - 1;
  };
  addEventListener("pointermove", onPointer, { passive: true });

  function frame(now: number) {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    const k = reduced ? 1 : 1 - Math.exp(-dt * 8);
    for (const key in cur) cur[key as keyof Pose] += (target[key as keyof Pose] - cur[key as keyof Pose]) * k;

    if (!reduced) {
      t += dt;
      jump = Math.max(0, jump - dt);
      shake *= Math.exp(-dt * 5);
      tap *= Math.exp(-dt * 14);
      wave = Math.max(0, wave - dt);
      talk = Math.max(0, talk - dt);
      nextBlink -= dt;
      if (nextBlink <= 0) (blink = 1), (nextBlink = 2 + Math.random() * 3.5);
      blink = Math.max(0, blink - dt * 8);
    }

    const follow = state === "idle" || state === "error" || state === "success" ? 1 : 0;
    const loadingSpin = state === "loading" ? t * 5 : 0;
    const gx = state === "email" ? caret * 2 - 1 : state === "loading" ? Math.cos(loadingSpin) * 0.6 : cur.gx + pointerX * follow;
    const gy = state === "loading" ? 0.3 + Math.sin(loadingSpin) * 0.4 : cur.gy - pointerY * follow;

    body.rotation.set(
      cur.pitch + pointerY * 0.15 * follow + tap * 0.08,
      cur.yaw + pointerX * 0.3 * follow + Math.sin(t * 35) * shake * 0.35,
      cur.tilt + (state === "idle" ? Math.sin(t * 1.1) * 0.04 : 0),
    );
    const breathe = Math.sin(t * 2.2) * 0.018 - tap * 0.05;
    const hop = jump > 0 ? Math.abs(Math.sin(jump * Math.PI * 2.5)) * 0.35 * jump : 0;
    body.scale.set(1 - breathe * 0.6, 1 + breathe, 1 - breathe * 0.6);
    root.position.y = hop + Math.sin(t * 1.6) * 0.06; // flota
    shadow.scale.setScalar(0.85 - hop * 0.6);

    eyes.forEach(({ ball, pupil, side }, i) => {
      const open = (i ? cur.eyeR : cur.eyeL) * (1 - blink);
      ball.scale.y = 0.27 * Math.max(0.08, open);
      // −side*0.06: pupilas un poco hacia adentro → te mira a ti, no al vacío.
      const px = THREE.MathUtils.clamp(gx, -1, 1) * 0.28 - side * 0.06, py = THREE.MathUtils.clamp(gy, -1, 1) * 0.26;
      pupil.position.set(px, py, Math.sqrt(1 - px * px - py * py) + 0.01);
    });
    for (const b of brows) {
      b.g.position.copy(b.base).y += cur.brow * 0.07;
      b.bar.rotation.z = Math.PI / 2 - BROW_ARC / 2 - cur.browAng * 0.3 * b.side;
    }
    // Hablar: dos senos desfasados → aperturas irregulares, se lee como sílabas.
    const say = talk > 0 ? Math.abs(Math.sin(t * 17) * Math.sin(t * 6.1)) * 0.8 * Math.min(talk * 4, 1) : 0;
    shapeMouth(cur.smile, cur.open, Math.max(cur.open, cur.grin, say));

    // Colita que se mueve + mechón con resorte (reacciona a saltos, teclas y sacudidas).
    tail.rotation.z = 2.55 + Math.sin(t * 15) * 0.28 * cur.wag;
    const vy = (root.position.y - prevY) / Math.max(dt, 1e-3);
    qv += (prevVy - vy) * 0.5 + (-90 * qa - 7 * qv) * dt + shake * Math.sin(t * 35) * 0.3;
    qa += qv * dt;
    prevY = root.position.y;
    prevVy = vy;
    quotes.rotation.set(qa * 0.5, 0, 0.12 + qa);

    // Manos: pose + tecleo alternado + saludo + celebrar.
    const [L, R] = hands;
    const cheer = state === "success" ? Math.sin(t * 14) * 0.1 : 0;
    const idleBob = Math.sin(t * 2.2 + 1) * 0.04;
    L.position.set(cur.lx, cur.ly + idleBob + (tapSide < 0 ? tap * 0.18 : 0) + cheer, cur.lz);
    R.position.set(cur.rx, cur.ry + idleBob + (tapSide > 0 ? tap * 0.18 : 0) - cheer, cur.rz);
    if (wave > 0 && state === "idle") {
      const w = Math.min(wave, 1);
      R.position.x += (1.05 - R.position.x) * w;
      R.position.y += (0.75 + Math.sin(t * 13) * 0.12 - R.position.y) * w;
      R.position.z += Math.cos(t * 13) * 0.08 * w;
    }

    const showDots = cur.open > 0.3 && state === "loading" ? 1 : 0;
    dots.forEach((d, i) => {
      d.scale.setScalar(THREE.MathUtils.lerp(d.scale.x, showDots, k));
      d.position.y = 1.25 + Math.max(0, Math.sin(t * 7 - i * 0.9)) * 0.14;
    });

    renderer.render(scene, camera);
    raf = requestAnimationFrame(frame);
  }
  let raf = requestAnimationFrame(frame);

  return {
    setState(next: CoachState) {
      if (next === "error" && !reduced) shake = 1;
      if (next === "success" && !reduced) jump = 1.2;
      state = next;
      target = POSES[next];
    },
    /** Cada tecla: pequeño rebote y una mano "teclea". */
    pulse() {
      tap = 1;
      tapSide = -tapSide;
      qv += reduced ? 0 : 1.2;
    },
    /** Mueve la boca como si hablara (p. ej. mientras aparece su mensaje; luego, con la voz del profesor). */
    say(seconds: number) {
      if (!reduced) talk = seconds;
    },
    /** Posición del cursor en el campo de correo (0 inicio … 1 final). */
    gaze(x: number) {
      caret = THREE.MathUtils.clamp(x, 0, 1);
    },
    destroy() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      removeEventListener("pointermove", onPointer);
      renderer.dispose();
    },
  };
}
