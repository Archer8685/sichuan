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

## 快取提醒

`map.html`／`itinerary.html` 以 `data.js?v=N`／`trip.js?v=N` 帶版本號載入，是為了避免瀏覽器快取舊檔案。
每次修改 `data.js` 或 `trip.js` 內容後，記得把兩個 HTML 檔裡對應的 `?v=N` 數字 +1，
否則使用者（含 GitHub Pages CDN）可能繼續看到舊版本。

## 更新資料

修改或新增 `data/*.json` 後執行 `python build_data.py`（需 `pip install zhconv`），
會重新產生 `data.js`（含去重、評分合併、繁→簡搜尋對照表）。
