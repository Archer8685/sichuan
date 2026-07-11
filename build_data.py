# -*- coding: utf-8 -*-
"""合併 data/*.json → data.js（map.html 使用）"""
import json, glob, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
# 餐廳檔優先於景點檔（同名地點如交通茶館，保留含菜色/人均的餐廳版本）
files = sorted(glob.glob(os.path.join(BASE, "data", "*.json")),
               key=lambda f: (0 if "food" in os.path.basename(f) else 1, f))
places, guides = [], []

def norm_city(f, item):
    c = item.get("city", "")
    if c in ("成都", "重庆"): return c
    if "chengdu" in f: return "成都"
    if "chongqing" in f: return "重庆"
    return c or "?"

def norm_halal(v):
    if v in (True, "true", "True", "清真"): return True
    if v in ("友善", "friendly", "清真友善"): return "友善"
    return False

def _norm_name(s):
    return re.sub(r"[（(].*?[)）]", "", s or "").replace("·", "").replace(" ", "").strip()

tours = []
ratings = {}
for f in files:
    name = os.path.basename(f)
    try:
        with open(f, encoding="utf-8") as fh:
            txt = fh.read()
        data = json.loads(txt)
    except Exception as e:
        print(f"[WARN] {name}: {e}")
        continue
    if not isinstance(data, list):
        data = data.get("items") or data.get("data") or []
    if name.startswith("guides"):
        guides.extend(data)
        print(f"{name}: {len(data)} guides")
        continue
    if name.startswith("tours"):
        tours.extend(data)
        print(f"{name}: {len(data)} tours")
        continue
    if name.startswith("ratings"):
        for r in data:
            if r.get("rating"):
                ratings[_norm_name(r["name"])] = (r["rating"], r.get("rating_source", ""))
        print(f"{name}: {len(data)} ratings")
        continue
    for it in data:
        it["city"] = norm_city(name, it)
        if "halal" in it: it["halal"] = norm_halal(it["halal"])
        # rating 統一為字串 "4.6/5"
        r = it.get("rating")
        if isinstance(r, (int, float)): it["rating"] = f"{r}/5"
        # 統一 category/type
        cat = it.get("type") or it.get("category") or ""
        cat = cat.replace("景點", "景点").replace("甜點", "甜点").replace("飲料", "饮料")
        if "伴手礼" in cat or "食品店" in cat: cat = "商场"
        if cat in ("景点", "商圈", "商场", "夜市"): it["type"] = cat; it.pop("category", None)
        else: it["category"] = cat; it.pop("type", None)
        # 座標轉 float
        for k in ("lat", "lng"):
            try: it[k] = float(it[k])
            except (TypeError, ValueError, KeyError): it[k] = None
        places.append(it)
    print(f"{name}: {len(data)} places")

# 去重（同城市同名取第一筆）
seen, deduped = set(), []
for p in places:
    key = (p["city"], _norm_name(p.get("name", "")))
    if key in seen: continue
    seen.add(key); deduped.append(p)

# 套用評分（名稱正規化後精確→包含式匹配）
if ratings:
    hit = 0
    for p in deduped:
        if p.get("rating"): hit += 1; continue
        n = _norm_name(p["name"])
        m = ratings.get(n)
        if not m:
            for rn, rv in ratings.items():
                if rn and (rn in n or n in rn): m = rv; break
        if m:
            p["rating"], p["rating_source"] = m[0], m[1]; hit += 1
    print(f"評分已套用 {hit} 間")

# 繁→簡字元對照表（供地圖搜尋支援繁體輸入）
def build_t2s(payload_text):
    try:
        from zhconv import convert
    except ImportError:
        print("[WARN] zhconv 未安裝，跳過 T2S")
        return {}
    t2s = {"麵": "面", "裡": "里", "遊": "游", "隻": "只", "乾": "干",
           "後": "后", "髮": "发", "於": "于", "臺": "台", "嚐": "尝"}
    for ch in set(payload_text):
        if not "一" <= ch <= "鿿":
            continue
        for variant in (convert(ch, "zh-tw"), convert(ch, "zh-hk")):
            if variant != ch and len(variant) == 1:
                t2s[variant] = ch
    return t2s

payload = json.dumps(deduped, ensure_ascii=False) + json.dumps(guides, ensure_ascii=False) + json.dumps(tours, ensure_ascii=False)
t2s_map = build_t2s(payload)

out = os.path.join(BASE, "data.js")
with open(out, "w", encoding="utf-8") as fh:
    fh.write("const PLACES = ")
    json.dump(deduped, fh, ensure_ascii=False, indent=1)
    fh.write(";\nconst GUIDES = ")
    json.dump(guides, fh, ensure_ascii=False, indent=1)
    fh.write(";\nconst TOURS = ")
    json.dump(tours, fh, ensure_ascii=False, indent=1)
    fh.write(";\nconst T2S = ")
    json.dump(t2s_map, fh, ensure_ascii=False)
    fh.write(";\n")

from collections import Counter
c1 = Counter((p["city"], p.get("type") or p.get("category")) for p in deduped)
print("\n=== 統計 ===")
for k, v in sorted(c1.items()): print(k, v)
print(f"總地點: {len(deduped)}（去重前 {len(places)}）, 攻略: {len(guides)}")
missing = [p["name"] for p in deduped if not p.get("lat")]
if missing: print(f"缺座標 {len(missing)}: {missing[:20]}")
