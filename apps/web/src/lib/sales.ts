// Demo: número ficticio (no existe en WhatsApp), así ningún mensaje llega a nadie.
// ponytail: en producción, el WhatsApp comercial real desde config (uno por sede).
const SALES_WHATSAPP = "593000000000";

/** Link de WhatsApp con el mensaje ya escrito: el estudiante llega al asesor con su nivel y su curso. */
export function salesLink(level: string, course: string, score?: number) {
  const pct = score == null ? "" : ` (${Math.round(score)}%)`;
  const msg = `Hola Global, hice la evaluación de nivel: ${level}${pct}. Quiero información del curso ${course}.`;
  return `https://wa.me/${SALES_WHATSAPP}?text=${encodeURIComponent(msg)}`;
}
