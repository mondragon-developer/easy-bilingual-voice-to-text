// The smallest service worker that lets the page install as an app on a
// phone. It caches nothing on purpose: the page is tiny, and a stale copy
// after an update would be worse than a fresh fetch from the computer.
self.addEventListener("fetch", () => {});
