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
        if "伴手礼" in cat or "食品店" in cat: cat = "午晚餐"  # 食品/滷味鋪歸餐飲（可被清真篩選找到），非商場
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

# ── 顯示層簡→繁轉換 ──
# 網頁以繁體中文呈現：所有「顯示用」字串轉為繁體（zh-tw）。
# 但 city / type / category / halal 是程式內部比對用的 key（如 p.city==="重庆"、
# CATS["景点"]），必須保留簡體原值；搜尋與行程站點比對均先經 t2s() 正規化，
# 因此名稱轉繁後所有匹配邏輯照常運作。
_S2T_SKIP_KEYS = {"city", "type", "category", "halal"}

# zhconv 誤轉修正：地名的「里」不是「裡面」的裡；姓氏范、店名于塗保持原字；
# 臺一律用台（台灣通行寫法：電台巷、觀景台）。
_S2T_FIXES = [
    ("錦裡", "錦里"), ("太古裡", "太古里"), ("下浩裡", "下浩里"), ("祥和裡", "祥和里"),
    ("公裡", "公里"), ("裡程", "里程"), ("萬裡", "萬里"), ("五裡", "五里"), ("十裡", "十里"),
    ("翡翠裡", "翡翠里"), ("天都裡", "天都里"), ("唐杜裡", "唐杜里"), ("愛裡耶", "愛里耶"),
    ("裡弄", "里弄"), ("太古里東裡", "太古里東里"),
    ("範嬢嬢", "范嬢嬢"), ("於塗", "于塗"), ("臺", "台"),
]

def _apply_fixes(s):
    for a, b in _S2T_FIXES:
        s = s.replace(a, b)
    return s

def to_traditional(obj, key=None):
    try:
        from zhconv import convert
    except ImportError:
        return obj
    if isinstance(obj, dict):
        return {k: (v if k in _S2T_SKIP_KEYS else to_traditional(v, k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_traditional(x, key) for x in obj]
    if isinstance(obj, str):
        from zhconv import convert
        return _apply_fixes(convert(obj, "zh-tw"))
    return obj

deduped = to_traditional(deduped)
guides = to_traditional(guides)
tours = to_traditional(tours)

# ── T2S 搜尋對照表（資料轉繁「之後」建置）──
# 逐字用 zh-cn 反向轉換（繁→簡），無詞組對齊問題：
# 涵蓋最終資料中出現的所有繁體字，搜尋時 query 與 haystack 都經
# t2s() 正規化為簡體再比對，因此簡體/繁體輸入皆可命中。
final_payload = json.dumps(deduped, ensure_ascii=False) + json.dumps(guides, ensure_ascii=False) + json.dumps(tours, ensure_ascii=False)
t2s_map = build_t2s(payload)  # 先取單字級簡→繁反查＋手動修正表
try:
    from zhconv import convert as _conv
    # 字元集合：最終繁體資料 ∪ 原簡體資料的 zh-tw 轉換（涵蓋使用者可能輸入、
    # 但被修正表改掉的字，如 臺）
    char_pool = set(final_payload) | set(_conv(payload, "zh-tw"))
    for ch in char_pool:
        if not "一" <= ch <= "鿿":
            continue
        simp = _conv(ch, "zh-cn")
        if simp != ch and len(simp) == 1:
            t2s_map[ch] = simp
except ImportError:
    pass

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
