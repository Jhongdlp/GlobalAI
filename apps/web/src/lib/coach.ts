import * as THREE from "three";

export type Hat = "grad" | "bowler" | "party";

export type CoachState = "idle" | "email" | "password" | "peek" | "loading" | "error" | "success" | "present" | "listen";

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
  // Presenta algo a su derecha (p. ej. tu progreso en el dashboard): gira, señala con la mano y mira hacia allá.
  present: { yaw: 0.45, pitch: 0.05, tilt: 0.08, gx: 0.7, gy: -0.1, eyeL: 1, eyeR: 1, brow: 0.5, browAng: 0, smile: 0.9, open: 0, grin: 0.4, wag: 0.3, ...REST, rx: 1.25, ry: 0.35, rz: 0.55 },
  // Te escucha: ladea la cabeza hacia la mano que hace de "oreja", cejas arriba, boca cerrada y tranquila.
  listen: { yaw: -0.15, pitch: 0.05, tilt: -0.2, gx: -0.35, gy: 0.25, eyeL: 1, eyeR: 1, brow: 0.6, browAng: 0.15, smile: 0.5, open: 0, grin: 0, wag: 0.15, ...REST, rx: 1.15, ry: 0.3, rz: 0.15 },
  success: { yaw: 0, pitch: -0.1, tilt: 0, gx: 0, gy: 0, eyeL: 0, eyeR: 0, brow: 0.8, browAng: 0, smile: 1, open: 0, grin: 1, wag: 1, ...CHEER },
};

const RED = "#ff4b3a"; // coral propio de Glo
const CREAM = "#fff4e0";
const SHAPE = new THREE.Vector3(1.12, 0.9, 0.88); // esfera → globo de diálogo "gordito"
const INK = "#1f1b16";
const BROW_ARC = 1.3;
const NOPE = 1.3; // duración del "no, no" de error (s)

const onSphere = (lat: number, lon: number, r = 1) => {
  const a = THREE.MathUtils.degToRad(lat), o = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(Math.cos(a) * Math.sin(o), Math.sin(a), Math.cos(a) * Math.cos(o)).multiplyScalar(r);
};

export function createCoach(canvas: HTMLCanvasElement) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // En pantallas HiDPI el MSAA sobra (los píxeles ya son finos) y 1.5x basta para un personaje plano.
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: devicePixelRatio < 1.5, alpha: true, powerPreference: "low-power" });
  const baseRatio = Math.min(devicePixelRatio, 1.5);
  renderer.setPixelRatio(baseRatio);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 30);
  camera.position.set(0, 0.25, 6.4); // hueco arriba para los sombreros
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

  // Sombreros que Glo gana según tu nivel (se ponen con wear()). Van sobre la cabeza y tapan el mechón.
  const inkMat = toon(INK);
  const HATS: Record<Hat, () => THREE.Object3D> = {
    // C1: birrete de graduación con borla coral que se balancea.
    grad() {
      const g = new THREE.Group();
      g.add(part(new THREE.CylinderGeometry(0.36, 0.42, 0.22, 32), inkMat, 0.05));
      const board = part(new THREE.BoxGeometry(0.95, 0.05, 0.95), inkMat, 0.05);
      board.position.y = 0.13;
      board.rotation.y = Math.PI / 4;
      g.add(board);
      const button = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), redMat);
      button.position.y = 0.17;
      const tassel = new THREE.Group(); // cuelga del botón hacia una esquina
      tassel.position.y = 0.17;
      const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.62, 6), redMat);
      cord.position.set(0.3, -0.02, 0.1);
      cord.rotation.z = Math.PI / 2 - 0.1;
      const drop = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.07, 0.26, 12), redMat);
      drop.position.set(0.6, -0.16, 0.1);
      tassel.add(cord, drop);
      tassel.name = "swing";
      g.add(button, tassel);
      return g;
    },
    // B1–B2: bombín británico ("very British") con cinta coral.
    bowler() {
      const g = new THREE.Group();
      const brim = part(new THREE.CylinderGeometry(0.62, 0.62, 0.05, 40), inkMat, 0.04);
      brim.scale.z = 0.85;
      const dome = part(new THREE.SphereGeometry(0.42, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), inkMat, 0.04);
      dome.scale.y = 1.05;
      const band = new THREE.Mesh(new THREE.CylinderGeometry(0.425, 0.425, 0.09, 32, 1, true), redMat);
      band.position.y = 0.06;
      g.add(brim, dome, band);
      return g;
    },
    // Pre-A1–A2: gorro de fiesta: celebramos que empezaste.
    party() {
      const g = new THREE.Group();
      const cone = part(new THREE.ConeGeometry(0.3, 0.62, 32), toon("#2b44c7"), 0.06);
      cone.position.y = 0.28;
      const pom = part(new THREE.SphereGeometry(0.1, 16, 12), creamMat, 0.12);
      pom.position.y = 0.62;
      g.add(cone, pom);
      return g;
    },
  };
  const hatSlot = new THREE.Group();
  hatSlot.position.set(0.04, 0.82, 0.02);
  body.add(hatSlot);
  let hatY = 0, hatV = 0; // resorte de la caída del sombrero
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
    // Ojo cerrado = una línea curva de tinta (‿ tranquilo · ^ feliz), no un ojo aplastado.
    const lash = stick(new THREE.Group(), 8, 16.5 * side, 0.99);
    const arc = new THREE.Mesh(new THREE.TorusGeometry(0.13, 0.03, 8, 20, Math.PI), pupilMat);
    lash.add(arc);
    face.add(lash);
    return { ball, pupil, side, arc };
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
  let mouthKey = "";
  function shapeMouth(smile: number, round: number, open: number) {
    const key = `${smile.toFixed(3)},${round.toFixed(3)},${open.toFixed(3)}`;
    if (key === mouthKey) return; // en reposo la boca no cambia: no regenerar ni subir geometría
    mouthKey = key;
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

  const shadow = new THREE.Mesh(new THREE.CircleGeometry(1, 32), new THREE.MeshBasicMaterial({ color: "#000", transparent: true, opacity: 0.16 }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -1.35;
  scene.add(shadow);

  // "Llenado" de color (pantalla de carga): cada píxel se ve gris o a color según su altura en el mundo
  // respecto a uFill, con una ondita en el borde, como un líquido que sube. uFill alto = todo a color.
  const fillU = { uFill: { value: 10 }, uTime: { value: 0 } };
  let fillTarget = 10;
  function patch(root: THREE.Object3D) {
    root.traverse((o) => {
      if (!(o instanceof THREE.Mesh) || o === shadow) return;
      const m = o.material as THREE.Material;
      if (m.userData.fill) return;
      m.userData.fill = true;
      m.onBeforeCompile = (sh) => {
        Object.assign(sh.uniforms, fillU);
        sh.vertexShader = "varying vec2 vFill;\n" + sh.vertexShader.replace(
          "#include <project_vertex>",
          "#include <project_vertex>\n  vFill = (modelMatrix * vec4(transformed, 1.0)).xy;",
        );
        sh.fragmentShader = "uniform float uFill;\nuniform float uTime;\nvarying vec2 vFill;\n" + sh.fragmentShader.replace(
          "#include <dithering_fragment>",
          `#include <dithering_fragment>
  float lum = dot(gl_FragColor.rgb, vec3(0.299, 0.587, 0.114));
  float edge = uFill + sin(vFill.x * 7.0 + uTime * 3.0) * 0.045;
  gl_FragColor.rgb = mix(vec3(0.2 + lum * 0.7), gl_FragColor.rgb, step(vFill.y, edge));`,
        );
      };
    });
  }
  patch(scene);

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
  let voiceT = 0, voiceV = 0; // volumen real de un audio (0..1) → boca y manos sincronizadas
  let jump = 0, nope = 0, tap = 0, tapSide = 1, blink = 0, nextBlink = 2;
  let wave = reduced ? 0 : 2.2; // saluda al aparecer
  let pointerX = 0, pointerY = 0, t = 0;
  let qa = 0, qv = 0, prevY = 0, prevVy = 0; // resorte del mechón
  let giggle = 0, spin = 1; // al tocarlo: risita + giro (spin 0→1)
  let last = performance.now();

  const onPointer = (e: PointerEvent) => {
    pointerX = (e.clientX / innerWidth) * 2 - 1;
    pointerY = (e.clientY / innerHeight) * 2 - 1;
  };
  addEventListener("pointermove", onPointer, { passive: true });

  // Tocar a Glo: raycast solo contra el cuerpo, así el lienzo vacío no reacciona.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const hits = (e: PointerEvent | MouseEvent) => {
    const r = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    return ray.intersectObjects([blob, tail, ...hands], false).length > 0;
  };
  const pokeListeners: ((e: MouseEvent) => void)[] = [];
  let hoverAt = 0;
  const onHover = (e: PointerEvent) => {
    if (e.timeStamp - hoverAt < 100) return; // raycast a ~10 Hz basta para el cursor
    hoverAt = e.timeStamp;
    canvas.style.cursor = hits(e) ? "pointer" : "";
  };
  const onClick = (e: MouseEvent) => {
    if (!hits(e)) return;
    giggle = 1.3;
    if (!reduced) (spin = 0), (jump = Math.max(jump, 0.7)), (qv += 3);
    for (const cb of pokeListeners) cb(e);
  };
  canvas.addEventListener("pointermove", onHover, { passive: true });
  canvas.addEventListener("click", onClick);

  function frame(now: number) {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    const k = reduced ? 1 : 1 - Math.exp(-dt * 8);
    for (const key in cur) cur[key as keyof Pose] += (target[key as keyof Pose] - cur[key as keyof Pose]) * k;

    if (!reduced) {
      t += dt;
      jump = Math.max(0, jump - dt);
      spin = Math.min(1, spin + dt / 0.9);
      nope = Math.max(0, nope - dt);
      tap *= Math.exp(-dt * 14);
      wave = Math.max(0, wave - dt);
      talk = Math.max(0, talk - dt);
      nextBlink -= dt;
      if (nextBlink <= 0) (blink = 1), (nextBlink = 2 + Math.random() * 3.5);
      blink = Math.max(0, blink - dt * 8);
    }

    // Error: "no, no" con la cabeza y los ojos cerrados (~2.5 vaivenes lentos que se apagan al final).
    const nopeAmt = Math.min(nope / 0.35, 1);
    const shake = Math.sin((NOPE - nope) * 13) * nopeAmt;
    const follow = state === "idle" || state === "error" || state === "success" ? 1 : 0;
    const loadingSpin = state === "loading" ? t * 5 : 0;
    const gx = state === "email" ? caret * 2 - 1 : state === "loading" ? Math.cos(loadingSpin) * 0.6 : cur.gx + pointerX * follow;
    const gy = state === "loading" ? 0.3 + Math.sin(loadingSpin) * 0.4 : cur.gy - pointerY * follow;

    fillU.uTime.value = t;
    fillU.uFill.value += (fillTarget - fillU.uFill.value) * (reduced ? 1 : 1 - Math.exp(-dt * 3));
    giggle = Math.max(0, giggle - dt);
    const g = Math.min(giggle * 3, 1); // 1 mientras se ríe, baja suave al final
    const c1 = 1.7, e = spin - 1; // easeOutBack: gira una vuelta y se pasa un poquito
    const twirl = spin < 1 ? Math.PI * 2 * (1 + (c1 + 1) * e ** 3 + c1 * e ** 2) : 0;
    // Escuchando: tu voz no mueve su boca; asiente al ritmo ("ajá, ajá") y la colita se anima.
    const listening = state === "listen";
    const nod = listening ? Math.max(0, Math.sin(t * 7)) * Math.min(voiceV * 3, 1) * 0.16 : 0;
    body.rotation.set(
      cur.pitch + pointerY * 0.15 * follow + tap * 0.08 + nod,
      cur.yaw + twirl + pointerX * 0.3 * follow + shake * 0.45,
      cur.tilt + (state === "idle" ? Math.sin(t * 1.1) * 0.04 : 0),
    );
    const breathe = Math.sin(t * 2.2) * 0.018 - tap * 0.05;
    const hop = jump > 0 ? Math.abs(Math.sin(jump * Math.PI * 2.5)) * 0.35 * jump : 0;
    body.scale.set(1 - breathe * 0.6, 1 + breathe, 1 - breathe * 0.6);
    root.position.y = hop + Math.sin(t * 1.6) * 0.06; // flota
    shadow.scale.setScalar(0.85 - hop * 0.6);

    eyes.forEach(({ ball, pupil, side, arc }, i) => {
      const open = (i ? cur.eyeR : cur.eyeL) * (1 - blink);
      const o = Math.min(open, 1 - g, 1 - nopeAmt); // risita u "no, no": cierra los ojos
      // Hasta 0.5 el ojo se entorna un poco; por debajo cambia a la línea curva.
      ball.visible = o > 0.5;
      ball.scale.y = 0.27 * (0.75 + 0.25 * o);
      arc.visible = !ball.visible;
      const happy = g > 0 || state === "success";
      arc.rotation.z = happy ? 0 : Math.PI; // ∩ = ^ feliz · ∪ = ‿ tranquilo
      arc.position.y = happy ? -0.06 : 0.04;
      arc.scale.set(1, happy ? 0.9 : 0.55, 1);
      // −side*0.06: pupilas un poco hacia adentro → te mira a ti, no al vacío.
      const px = THREE.MathUtils.clamp(gx, -1, 1) * 0.28 - side * 0.06, py = THREE.MathUtils.clamp(gy, -1, 1) * 0.26;
      pupil.position.set(px, py, Math.sqrt(1 - px * px - py * py) + 0.01);
    });
    for (const b of brows) {
      b.g.position.copy(b.base).y += cur.brow * 0.07;
      b.bar.rotation.z = Math.PI / 2 - BROW_ARC / 2 - cur.browAng * 0.3 * b.side;
    }
    // Hablar: dos senos desfasados → aperturas irregulares, se lee como sílabas.
    // Abre rápido y cierra lento: los microsilencios entre palabras no cortan el "habla".
    voiceV += (voiceT - voiceV) * (reduced ? 1 : voiceT > voiceV ? 0.5 : 0.06);
    // Boca "de dibujo animado": sílabas que abren y cierran a ritmo de habla. Con audio real, el volumen
    // solo decide CUÁNDO habla (en los silencios cierra la boca); no se sincroniza palabra por palabra.
    const syllables = Math.abs(Math.sin(t * 17) * Math.sin(t * 6.1));
    const speaking = listening ? 0 : Math.max(Math.min(voiceV * 4, 1), talk > 0 ? Math.min(talk * 4, 1) : 0);
    const say = speaking * (0.25 + syllables * 0.65);
    shapeMouth(Math.max(cur.smile, g), cur.open * (1 - g), Math.max(cur.open, cur.grin, say, g * 0.9));

    // Colita que se mueve + mechón con resorte (reacciona a saltos, teclas y sacudidas).
    tail.rotation.z = 2.55 + Math.sin(t * 15) * 0.28 * (cur.wag + (listening ? voiceV : 0));
    const vy = (root.position.y - prevY) / Math.max(dt, 1e-3);
    qv += (prevVy - vy) * 0.5 + (-90 * qa - 7 * qv) * dt + shake * 0.25;
    qa += qv * dt;
    prevY = root.position.y;
    prevVy = vy;
    quotes.rotation.set(qa * 0.5, 0, 0.12 + qa);
    if (hatSlot.children.length) {
      hatV += (-140 * hatY - 10 * hatV) * dt; // cae desde arriba y rebota al posarse
      hatY += hatV * dt;
      hatSlot.position.y = 0.82 + hatY;
      hatSlot.rotation.set(qa * 0.3, 0, -0.14 + qa * 0.6);
      const swing = hatSlot.getObjectByName("swing");
      if (swing) swing.rotation.set(0, 0, qa * 1.5 + Math.sin(t * 1.3) * 0.05);
    }

    // Manos: pose + tecleo alternado + saludo + celebrar.
    const [L, R] = hands;
    const cheer = state === "success" ? Math.sin(t * 14) * 0.1 : 0;
    const idleBob = Math.sin(t * 2.2 + 1) * 0.04;
    const gesture = listening ? 0 : voiceV * 0.22; // al hablar con voz real, las manos acompañan
    L.position.set(cur.lx, cur.ly + idleBob + (tapSide < 0 ? tap * 0.18 : 0) + cheer + gesture * Math.sin(t * 5), cur.lz);
    R.position.set(cur.rx, cur.ry + idleBob + (tapSide > 0 ? tap * 0.18 : 0) - cheer + gesture * Math.sin(t * 5 + 2), cur.rz);
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
    raf = visible ? requestAnimationFrame(frame) : 0;
  }
  let raf = requestAnimationFrame(frame);
  // Fuera de pantalla (scroll en móvil, panel tapado) no se renderiza nada.
  let visible = true;
  const io = new IntersectionObserver(([e]) => {
    visible = e.isIntersecting;
    if (visible && !raf) (last = performance.now()), (raf = requestAnimationFrame(frame));
  });
  io.observe(canvas);

  return {
    setState(next: CoachState) {
      if (next === "error" && !reduced) nope = NOPE;
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
    /** Volumen de un audio real (0..1) cada frame: Glo "dice" ese audio. 0 para soltarlo. */
    voice(level: number) {
      voiceT = THREE.MathUtils.clamp(level, 0, 1);
    },
    say(seconds: number) {
      if (!reduced) talk = seconds;
    },
    /** Se llama cuando alguien toca a Glo (con el evento del clic, para efectos en la página). */
    onPoke(cb: (e: MouseEvent) => void) {
      pokeListeners.push(cb);
    },
    /** Posición del cursor en el campo de correo (0 inicio … 1 final). */
    gaze(x: number) {
      caret = THREE.MathUtils.clamp(x, 0, 1);
    },
    /** Más resolución cuando el lienzo se agranda con transform (p. ej. Glo al centro): k = factor de escala. */
    sharpness(k: number) {
      renderer.setPixelRatio(Math.min(baseRatio * Math.max(1, k), 3));
      resize();
    },
    /** Color de Glo de 0 (gris) a 1 (a todo color), subiendo desde abajo como un líquido. */
    fill(p: number) {
      const y = -1.3 + THREE.MathUtils.clamp(p, 0, 1) * 2.9;
      if (fillU.uFill.value > 5) fillU.uFill.value = -1.3; // primera vez: empieza vacío
      fillTarget = p >= 1 ? 10 : y;
      if (p < 1) fillU.uFill.value = y; // quien llama ya suaviza el progreso
    },
    /** Foto de Glo tal como está ahora (pose y sombrero) a `size` px, para la imagen de compartir.
     *  Se copia en el mismo turno del render: sin preserveDrawingBuffer el búfer ya se habría limpiado. */
    snapshot(size: number) {
      const out = document.createElement("canvas");
      out.width = out.height = size;
      const prev = renderer.getPixelRatio();
      renderer.setPixelRatio(size / (canvas.clientWidth || size));
      resize();
      renderer.render(scene, camera);
      out.getContext("2d")!.drawImage(canvas, 0, 0, size, size);
      renderer.setPixelRatio(prev);
      resize();
      return out;
    },
    /** Pone (o quita con null) un sombrero: cae sobre la cabeza con rebote. */
    wear(hat: Hat | null) {
      hatSlot.clear();
      quotes.visible = !hat;
      if (!hat) return;
      hatSlot.add(HATS[hat]());
      patch(hatSlot);
      hatY = reduced ? 0 : 1.6;
      hatV = 0;
      qv += reduced ? 0 : 2;
    },
    destroy() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      removeEventListener("pointermove", onPointer);
      canvas.removeEventListener("pointermove", onHover);
      canvas.removeEventListener("click", onClick);
      renderer.dispose();
      renderer.forceContextLoss(); // libera el contexto WebGL (la pantalla de carga crea el suyo)
    },
  };
}
