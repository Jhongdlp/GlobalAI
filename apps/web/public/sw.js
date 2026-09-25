// Sin internet: una navegación que falla muestra /offline; los assets con hash salen de la caché.
// ponytail: la caché nunca se purga; cambiar CACHE y borrar las viejas en "activate" si crece.
const CACHE = "glo-v1";

self.addEventListener("install", (e) =>
  e.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      const html = await (await fetch("/offline")).text();
      // Respuesta nueva: una redirección (/offline → /offline/) no puede servirse a una navegación.
      await cache.put("/offline", new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } }));
      await cache.addAll([...new Set(html.match(/\/_astro\/[\w.-]+/g))]);
      await self.skipWaiting();
    })(),
  ),
);

self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
  } else if (req.method === "GET" && /\/_astro\/|fonts\.(googleapis|gstatic)\.com/.test(req.url)) {
    e.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
            return res;
          }),
      ),
    );
  }
});
