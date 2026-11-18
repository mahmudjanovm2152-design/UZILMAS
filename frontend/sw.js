// Uzilmas service worker: sahifalarni keshlaydi — hamshira internetsiz ham ilovani oçadi.
const CACHE = "uzilmas-v2";
const SHELL = ["/nurse", "/app", "/static/i18n-ru.js", "/static/uzilmas.css", "/static/common.js", "/static/logo-mark.png", "/manifest.webmanifest"];
self.addEventListener("install", e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;   // API — tarmoq orqali
  e.respondWith(fetch(e.request).then(r => {
    const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r;
  }).catch(() => caches.match(e.request)));
});
