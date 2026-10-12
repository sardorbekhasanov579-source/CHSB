"""Do'kon ilovasi (PWA) uchun: manifest, service worker va ikonka (kutubxonasiz chiziladi)."""
import math
import struct
import zlib
from functools import lru_cache

MANIFEST = {
    "name": "Do'kon ilovasi",
    "short_name": "Do'kon",
    "description": "Distribyutordan buyurtma bering, qoldiq va hisob-kitobni kuzating",
    "lang": "uz",
    "start_url": "/ilova",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0B3D2E",
    "theme_color": "#0B3D2E",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}

SERVICE_WORKER = """
const CACHE = 'ilova-v1';
const SHELL = ['/ilova', '/manifest.webmanifest', '/icon-192.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  if (u.pathname === '/ilova') {
    // Sahifa: avval internetdan, bo'lmasa keshdan
    e.respondWith(fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request)));
  } else if (SHELL.includes(u.pathname)) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
  // API so'rovlari (buyurtma, qoldiq, to'lov) hech qachon keshlanmaydi
});
"""


def _rrect(px, py, cx, cy, hx, hy, r):
    qx, qy = abs(px - cx) - hx + r, abs(py - cy) - hy + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _seg(px, py, ax, ay, bx, by):
    """Nuqtadan kesmagacha masofa."""
    vx, vy, wx, wy = bx - ax, by - ay, px - ax, py - ay
    t = min(max((wx * vx + wy * vy) / (vx * vx + vy * vy), 0), 1)
    return math.hypot(wx - vx * t, wy - vy * t)


@lru_cache(maxsize=8)
def icon_png(size: int) -> bytes:
    """Yashil fon ustida oq xarid xaltasi va ichida belgi (tasdiqlangan buyurtma)."""
    c1, c2 = (11, 61, 46), (21, 122, 91)
    white, green = (255, 255, 255), (21, 122, 91)
    rows = []
    for y in range(size):
        row = bytearray([0])
        py = (y + 0.5) / size
        for x in range(size):
            px = (x + 0.5) / size
            col = _mix(c1, c2, (px + py) / 2)
            # xalta tanasi
            d = _rrect(px, py, 0.5, 0.60, 0.25, 0.20, 0.05) * size
            col = _mix(col, white, min(max(0.5 - d, 0), 1))
            # sopi (keng yarim halqa)
            ring = abs(math.hypot(px - 0.5, py - 0.40) - 0.12) - 0.018
            d = max(ring, py - 0.40) * size
            col = _mix(col, white, min(max(0.5 - d, 0), 1))
            # ichidagi belgi
            d = (min(_seg(px, py, 0.40, 0.60, 0.47, 0.67), _seg(px, py, 0.47, 0.67, 0.61, 0.52)) - 0.032) * size
            col = _mix(col, green, min(max(0.5 - d, 0), 1))
            row += bytes(int(v) for v in col)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
