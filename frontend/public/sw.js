/* YouFeed Service Worker — Web Push handler (Phase 1.2.E).
 *
 * Responsabilità:
 * - intercettare l'evento `push` e mostrare una notifica nativa
 * - su `notificationclick` aprire/focalizzare la SPA al link giusto
 *
 * Il payload del push è JSON: { title, body, link, tag? }. Il backend
 * `app/workers/push.py` produce esattamente questo shape.
 */

self.addEventListener("install", (event) => {
  // Attiva subito il nuovo SW senza aspettare il vecchio
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Prendi controllo immediato dei client (tab) aperti
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (e) {
    payload = { title: "YouFeed", body: event.data ? event.data.text() : "" };
  }

  const title = payload.title || "YouFeed";
  const options = {
    body: payload.body || "",
    icon: "/static/img/android-chrome-192x192.png",
    // badge: monocromatica per la status bar Android — non ancora prodotta.
    // Senza, Android usa l'icona di default del browser (cerchio).
    tag: payload.tag || undefined,
    data: { link: payload.link || "/me/feed" },
    renotify: !!payload.tag,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = (event.notification.data && event.notification.data.link) || "/me/feed";

  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      // Se c'è già un tab YouFeed aperto, portalo in focus e navigaci
      for (const client of allClients) {
        const url = new URL(client.url);
        if (url.origin === self.location.origin) {
          await client.focus();
          if ("navigate" in client) {
            try {
              return await client.navigate(link);
            } catch (e) {
              // fallback sotto
            }
          }
        }
      }
      // Altrimenti apri un nuovo tab
      if (self.clients.openWindow) {
        return self.clients.openWindow(link);
      }
    })(),
  );
});
