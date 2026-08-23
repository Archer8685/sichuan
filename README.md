# 成都・重慶旅遊網站（2026/12/5–12/13）

純靜態網站，任何靜態空間（GitHub Pages / Netlify / Vercel / S3 / nginx）皆可部署，無後端、無資料庫。

## 檔案結構

```
index.html        入口（topnav + iframe 嵌入行程頁）
itinerary.html    五版本行程規劃（載入 data.js 自動附加店家詳情）
map.html          互動地圖（Leaflet + 高德圖磚）
data.js           ★ 唯一資料檔（PLACES / GUIDES / TOURS / T2S），由 build_data.py 產生
libs/             Leaflet 1.9.4 本地副本（已去 CDN 依賴）
data/*.json       原始研究資料（部署可不上傳，僅重建 data.js 用）
build_data.py     資料合併腳本：python build_data.py → 重新產生 data.js
audit/            高德地圖座標全量稽核結果與逐筆判定紀錄
apply_amap_audit.py 將稽核結果套用到 data/*.json；無法確認者會移除座標
compact_list.txt  rest_names.txt  中間產物（可不上傳）
.claude/          開發工具設定（不用上傳）
```

## 部署清單（最小集合）

`index.html`、`itinerary.html`、`map.html`、`data.js`、`trip.js`（最終行程路線資料）、`libs/`（整個資料夾）

## 對外相依（部署後仍需網路的部分）

1. **高德地圖圖磚** `webrd0{1-4}.is.autonavi.com`：HTTPS、免金鑰，個人使用穩定；但屬非官方端點、無 SLA。若日後失效，替代方案：
   - 申請高德開放平台金鑰改用官方 JS API
   - 或改 OpenStreetMap 圖磚（注意：資料座標為 GCJ-02，在 OSM/WGS-84 上會偏移 100–600 公尺，需加 gcj02→wgs84 轉換）
2. 攻略頁連結（知乎/攜程等）為外部網站。

其餘（Leaflet、字型、資料）皆已本地化，離線也能開啟版面。

## 版號與快取

`map.html`／`itinerary.html` 等頁面以 `data.js?v=N`／`trip.js?v=N` 載入以避開瀏覽器快取，
Service Worker（`sw.js`）的 `APP_CACHE = 'sichuan-app-vN'` 則決定 PWA 殼層是否重新預快取。
兩者**必須同號**——只改 `?v=N` 沒改 `APP_CACHE`，加到主畫面的使用者會一直看到舊版。

版號共有三種寫法、散在 7 個檔 23 處，**一律用腳本改，不要手改**：

```bash
python bump_version.py          # 全部 +1，並更新 SITE_UPDATED_AT
python bump_version.py --check  # 只檢查一致性
```

## 更新資料

修改或新增 `data/*.json` 後，跑完整串：

```bash
python build_data.py    # data/*.json → data.js（去重、評分合併、簡→繁、搜尋對照表）
python check_all.py     # 全域健檢：資料／座標／版號／行程邏輯／營業時間／跨檔殘留
python bump_version.py  # 同步 23 處版號
```

需 `pip install zhconv`。`check_all.py` 有問題會回傳 1，可直接掛 CI 或 commit hook；
它檢查什麼、以及各項為何存在，見 [`AGENTS.md`](AGENTS.md)。
