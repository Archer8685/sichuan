// sw.js — 離線快取
// 策略：App 殼層（HTML/JS/CSS/Leaflet/資料）可離線；高德底圖圖磚 cache-first，看過或預載過即離線可用。
const APP_CACHE = 'sichuan-app-v79';
const TILE_CACHE = 'sichuan-tiles-v1';
// 首次安裝先預快取頁面與地圖引擎（資料 data.js/trip.js 由執行時快取，因帶 ?v= 版本號）
const SHELL = ['./', 'map.html', 'itinerary.html', 'prep.html', 'guide.html', 'changelog.html', 'libs/leaflet.js', 'libs/leaflet.css'];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(APP_CACHE);
    // 逐一加入、容忍個別失敗（避免單一檔缺失導致整包安裝失敗）
    await Promise.allSettled(SHELL.map(u => c.add(new Request(u, { cache: 'reload' }))));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keep = [APP_CACHE, TILE_CACHE];
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => !keep.includes(k)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (_) { return; }

  // 高德底圖圖磚：cache-first（離線可用；圖磚不變動）
  if (url.hostname.includes('autonavi.com')) {
    e.respondWith((async () => {
      const c = await caches.open(TILE_CACHE);
      const hit = await c.match(req);
      if (hit) return hit;
      try { const res = await fetch(req); c.put(req, res.clone()); return res; }
      catch (_) { return hit || Response.error(); }
    })());
    return;
  }

  // 同源 App 檔案
  if (url.origin === location.origin) {
    // HTML 導覽：network-first（線上取最新、離線回退快取）
    if (req.mode === 'navigate') {
      e.respondWith((async () => {
        try {
          const res = await fetch(req);
          const c = await caches.open(APP_CACHE); c.put(req, res.clone());
          return res;
        } catch (_) {
          return (await caches.match(req, { ignoreSearch: true })) || (await caches.match('map.html')) || Response.error();
        }
      })());
      return;
    }
    // 其他資產（js/css/圖）：cache-first；帶 ?v= 的檔案版本改變即為新網址、會自動抓新版
    e.respondWith((async () => {
      const hit = await caches.match(req);
      if (hit) return hit;
      try { const res = await fetch(req); const c = await caches.open(APP_CACHE); c.put(req, res.clone()); return res; }
      catch (_) { return Response.error(); }
    })());
    return;
  }
  // 其他跨網域：直接走網路
});
