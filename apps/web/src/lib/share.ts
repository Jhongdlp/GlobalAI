/**
 * Imagen para compartir el nivel (historia 9:16 o post 4:5), dibujada en un <canvas> 2D con el mismo
 * lenguaje de la app: papel con grano, Lexend, tinta + coral, Glo con su sombrero. Sin librerías.
 * Idea: el nivel es identidad ("Soy B1"), el % solo si suma, y cierra con un reto para quien lo ve.
 */

export type Format = "story" | "post";
export type ShareCard = {
  level: string; // "A2", "Pre-A1"
  levelName: string; // "Elementary"
  score: number;
  best: { name: string; pct: number } | null;
  glo: HTMLCanvasElement | null; // foto de Glo (coach.snapshot)
};

const LEVELS = ["Pre-A1", "A1", "A2", "B1", "B2", "C1"];
const W = 1080;
// Coordenadas verticales por formato (px del lienzo).
const LAYOUT = {
  story: { h: 1920, glo: 600, gloY: 200, kicker: 900, code: 1250, codeSize: 380, path: 1370, power: 1600, cta: 1690 },
  post: { h: 1350, glo: 400, gloY: 120, kicker: 600, code: 870, codeSize: 290, path: 970, power: 0, cta: 1110 },
};

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function loadImage(src: string) {
  return new Promise<HTMLImageElement | null>((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

function wavy(ctx: CanvasRenderingContext2D, x0: number, x1: number, y: number, amp: number, len: number) {
  ctx.beginPath();
  for (let x = x0; x <= x1; x += 2) ctx.lineTo(x, y + Math.sin(((x - x0) / len) * Math.PI * 2) * amp);
  ctx.stroke();
}

export async function renderCard(fmt: Format, d: ShareCard): Promise<Blob> {
  const L = LAYOUT[fmt];
  const c = { bg: css("--bg"), ink: css("--ink"), muted: css("--muted"), line: css("--line"), accent: css("--accent"), glo: css("--glo"), surface: css("--surface") };
  await Promise.all(["400", "600", "700"].map((w) => document.fonts.load(`${w} 40px Lexend`)));
  const grainUrl = getComputedStyle(document.body, "::after").backgroundImage.match(/url\("?(.+?)"?\)$/)?.[1];
  const [grain, mark] = await Promise.all([grainUrl ? loadImage(grainUrl) : null, loadImage("/favicon.svg")]);

  const cv = document.createElement("canvas");
  cv.width = W;
  cv.height = L.h;
  const ctx = cv.getContext("2d")!;
  const font = (w: number, px: number) => (ctx.font = `${w} ${px}px Lexend, sans-serif`);
  const spacing = (em: number, px: number) => "letterSpacing" in ctx && (ctx.letterSpacing = `${em * px}px`);
  const M = 80; // margen

  // Papel + grano (la misma textura SVG de la página, a la misma opacidad).
  ctx.fillStyle = c.bg;
  ctx.fillRect(0, 0, W, L.h);
  if (grain) {
    ctx.globalAlpha = 0.3;
    ctx.fillStyle = ctx.createPattern(grain, "repeat")!;
    ctx.fillRect(0, 0, W, L.h);
    ctx.globalAlpha = 1;
  }

  // Comilla gigante de fondo: el detalle tipográfico de la marca (Glo es un globo de diálogo).
  font(700, L.h * 0.5);
  ctx.fillStyle = c.glo;
  ctx.globalAlpha = 0.07;
  ctx.textAlign = "right";
  ctx.fillText("”", W + 30, L.h * 0.5);
  ctx.globalAlpha = 1;

  // Marca
  ctx.textAlign = "left";
  if (mark) ctx.drawImage(mark, M, 70, 60, 60);
  font(600, 38);
  spacing(-0.02, 38);
  ctx.fillStyle = c.ink;
  ctx.fillText("Global AI", M + 76, 113);
  font(400, 28);
  spacing(0, 28);
  ctx.fillStyle = c.muted;
  ctx.textAlign = "right";
  ctx.fillText("English Placement · MCER", W - M, 111);

  // Glo con su sombrero
  if (d.glo) ctx.drawImage(d.glo, (W - L.glo) / 2, L.gloY, L.glo, L.glo);

  // "My English level is" + nivel gigante con subrayado ondulado coral (como en la app).
  ctx.textAlign = "left";
  ctx.fillStyle = c.ink;
  font(600, 56);
  spacing(-0.02, 56);
  ctx.fillText("My English level is", M, L.kicker);
  font(400, 34);
  spacing(0, 34);
  ctx.fillStyle = c.muted;
  ctx.fillText("Mi nivel de inglés es", M, L.kicker + 54);

  font(700, L.codeSize);
  spacing(-0.06, L.codeSize);
  ctx.fillStyle = c.ink;
  ctx.fillText(d.level, M - L.codeSize * 0.04, L.code);
  const codeW = ctx.measureText(d.level).width;
  ctx.strokeStyle = c.glo;
  ctx.lineWidth = L.codeSize * 0.022;
  ctx.lineCap = "round";
  wavy(ctx, M, M + codeW - L.codeSize * 0.08, L.code + L.codeSize * 0.09, L.codeSize * 0.022, L.codeSize * 0.1);

  font(600, 52);
  spacing(-0.02, 52);
  ctx.fillText(d.levelName, M + codeW + 10, L.code - L.codeSize * 0.42);
  if (d.score >= 60) {
    font(400, 38);
    spacing(0, 38);
    ctx.fillStyle = c.muted;
    ctx.fillText(`${d.score}% en la evaluación`, M + codeW + 10, L.code - L.codeSize * 0.42 + 58);
  }

  // Camino MCER: alcanzados en tinta, el actual en coral.
  const idx = LEVELS.indexOf(d.level);
  const step = (W - 2 * M) / LEVELS.length;
  ctx.strokeStyle = c.line;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(M + step / 2, L.path);
  ctx.lineTo(W - M - step / 2, L.path);
  ctx.stroke();
  ctx.textAlign = "center";
  LEVELS.forEach((lv, i) => {
    const x = M + step * (i + 0.5);
    const cur = i === idx;
    ctx.beginPath();
    ctx.arc(x, L.path, cur ? 18 : 12, 0, Math.PI * 2);
    ctx.fillStyle = cur ? c.glo : i < idx ? c.ink : c.bg;
    ctx.fill();
    ctx.lineWidth = 4;
    ctx.strokeStyle = cur ? c.glo : i < idx ? c.ink : c.line;
    ctx.stroke();
    font(cur ? 700 : 400, 28);
    ctx.fillStyle = cur ? c.ink : c.muted;
    ctx.fillText(lv, x, L.path + 62);
  });

  // Superpoder: solo lo mejor, en positivo (nadie comparte su 0%).
  if (L.power && d.best && d.best.pct > 0) {
    ctx.textAlign = "left";
    font(400, 32);
    ctx.fillStyle = c.muted;
    ctx.fillText("Mi superpoder", M, L.power - 52);
    font(700, 56);
    spacing(-0.02, 56);
    ctx.fillStyle = c.ink;
    ctx.fillText(d.best.name, M, L.power + 6);
    const bw = ctx.measureText(d.best.name).width;
    font(600, 40);
    spacing(0, 40);
    ctx.fillStyle = c.glo;
    ctx.fillText(`${Math.round(d.best.pct)}%`, M + bw + 22, L.power + 4);
  }

  // Reto: el bloque azul de "siguiente paso", ahora para quien ve la historia.
  const ch = L.h - M - L.cta;
  ctx.fillStyle = c.accent;
  ctx.beginPath();
  ctx.roundRect(M, L.cta, W - 2 * M, ch, 36);
  ctx.fill();
  ctx.save();
  ctx.clip();
  ctx.textAlign = "right";
  font(700, ch * 1.1);
  ctx.fillStyle = "rgb(255 255 255 / 0.12)";
  ctx.fillText("?", W - M + 10, L.cta + ch * 1.02);
  ctx.restore();
  ctx.textAlign = "left";
  ctx.fillStyle = c.surface;
  font(700, 54);
  spacing(-0.02, 54);
  ctx.fillText("¿Y tú, qué nivel tienes?", M + 48, L.cta + ch / 2 - 6);
  font(400, 32);
  spacing(0, 32);
  ctx.globalAlpha = 0.85;
  ctx.fillText(`Descúbrelo con Glo en ${location.host}`, M + 48, L.cta + ch / 2 + 48);
  ctx.globalAlpha = 1;

  return new Promise((resolve, reject) => cv.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob"))), "image/png"));
}
