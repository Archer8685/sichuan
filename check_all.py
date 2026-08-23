#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一鍵健檢：資料、座標、版號、行程邏輯全部檢查一遍。

    python check_all.py                  # 有問題回傳 1，可直接掛 CI／commit hook
    python check_all.py --save-baseline  # 重設「刻意壓縮停留時間」的基準線

檢查項目
  1. data/*.json 合法、去重後名稱不重複
  2. 每個地點都有座標，且落在四川＋重慶 bbox 內（擋掉配到外省的座標）
  3. data.js 與 data/*.json 同步（忘記跑 build_data.py 會被抓到）
  4. 版號 23 處一致（忘記跑 bump_version.py 會被抓到）
  5. trip.js 語法與行程邏輯：9 天、日期↔星期符合 2026 年曆、每天時間遞增、
     站點與備選都能在 data.js 找到、住宿連續性、遺珠榜 names 參照
  6. 每站停留時間 ≥ 該地點建議 duration（扣掉移動時間；包車日略過）
  7. 抵達／離開時間 vs data 記載的營業時間（中國沒有 Places API，改用離線比對；
     包車日略過，時間由司導掌握）
  8. 站點 note 不得寫成修改歷程
  9. 備選清單不得留著 note 已點名「不要去」的店
 10. 遺珠榜 BACKUPS 不得留修改歷程或指向已移除站點的交叉引用
 11. prep.html／guide.html 不得殘留已換掉的站點，且現行決策字面鎖要在
"""
import datetime
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

# 四川＋重慶（含都江堰、樂山、大足）；比行政區界寬一點，只用來擋「配到別的省」
BBOX = (28.0, 102.0, 32.5, 110.5)
ERR, WARN = [], []

# data/ 裡不是「地點」的檔案
NON_PLACE_PREFIX = ("guides", "tours", "ratings", "_")


def err(m):
    ERR.append(m)
    print("❌", m)


def warn(m):
    WARN.append(m)
    print("⚠️ ", m)


def ok(m):
    print("✅", m)


# ── 1–2. data/*.json ────────────────────────────────────────────────

def load_data_dir():
    places = []
    for f in sorted(glob.glob(os.path.join("data", "*.json"))):
        base = os.path.basename(f)
        if base.startswith(NON_PLACE_PREFIX):
            continue
        try:
            items = json.load(io.open(f, encoding="utf-8"))
        except Exception as e:
            err(f"{f} 不是合法 JSON：{e}")
            continue
        if not isinstance(items, list):
            items = items.get("items") or items.get("data") or []
        for it in items:
            it["_src"] = base
        places += items
    return places


def check_data(places):
    ok(f"data/*.json 合法，{len(places)} 筆原始地點")

    # 中國這邊有些點（清真寺、街區、武隆景區）在高德查不到穩定 POI，
    # 現況是刻意留白。只要沒被行程用到就不算錯（行程用到的另外在
    # check_trip 裡當 ERR 擋），這裡只提醒數量。
    no_coord = [p["name"] for p in places if p.get("lat") in (None, "")]
    if no_coord:
        warn(f"{len(no_coord)} 個地點沒有座標（地圖上不會出現）：{no_coord[:5]}")

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    outside = []
    for p in places:
        la, ln = num(p.get("lat")), num(p.get("lng"))
        if la is None or ln is None:
            continue
        if not (BBOX[0] <= la <= BBOX[2] and BBOX[1] <= ln <= BBOX[3]):
            outside.append((p["name"], la, ln))
    if outside:
        err(f"{len(outside)} 個座標落在四川＋重慶範圍外：{outside[:3]}")
    if not no_coord and not outside:
        ok("所有地點都有座標且落在四川＋重慶範圍內")

    md = [p["name"] for p in places if "**" in json.dumps(p, ensure_ascii=False)]
    if md:
        warn(f"{len(md)} 個地點的文字含 markdown `**`，"
             f"頁面用 innerHTML 輸出會顯示成星號：{md[:3]}")


# ── 3. data.js 同步 ─────────────────────────────────────────────────

def load_data_js():
    raw = io.open("data.js", encoding="utf-8").read()
    out = {}
    for key, nxt in (("PLACES", "GUIDES"), ("GUIDES", "TOURS"), ("TOURS", "T2S")):
        head = "const %s = " % key
        i = raw.index(head) + len(head)
        j = raw.index(";\nconst %s = " % nxt)
        out[key] = json.loads(raw[i:j])
        raw = raw[j + 2:]
    return out


def check_data_js():
    """把 build_data.py 在暫存目錄重跑一次，比對輸出是否與現有 data.js 相同。

    這個專案的 build 會做去重、評分合併與簡→繁轉換，無法用「欄位對欄位」比對，
    直接重跑最可靠（輸出是確定性的：檔案排序固定、字集用 sorted）。"""
    if not os.path.exists("data.js"):
        err("data.js 不存在——跑 python build_data.py")
        return
    tmp = tempfile.mkdtemp(prefix="sichuan_build_")
    try:
        shutil.copy("build_data.py", tmp)
        shutil.copytree("data", os.path.join(tmp, "data"))
        r = subprocess.run([sys.executable, "build_data.py"], cwd=tmp,
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            err("build_data.py 執行失敗：" + (r.stderr or "").strip()[:200])
            return
        fresh = io.open(os.path.join(tmp, "data.js"), encoding="utf-8").read()
        cur = io.open("data.js", encoding="utf-8").read()
        if fresh != cur:
            err("data.js 與 data/*.json 不同步——跑 python build_data.py")
        else:
            ok("data.js 與 data/*.json 同步")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 4. 版號 ─────────────────────────────────────────────────────────

def check_version():
    if not os.path.exists("bump_version.py"):
        warn("找不到 bump_version.py，跳過版號檢查")
        return
    r = subprocess.run([sys.executable, "bump_version.py", "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    last = lines[-1] if lines else "(無輸出)"
    if r.returncode != 0:
        err("版號不一致——跑 python bump_version.py（" + last.strip() + "）")
    else:
        ok(last.strip().lstrip("✅ "))


# ── 5. trip.js ──────────────────────────────────────────────────────

NODE = shutil.which("node.exe" if os.name == "nt" else "node")

# trip.js 尾端有 document.querySelectorAll(...)，Node 沒有 DOM，取值前必須先切掉。
DUMP_JS = r"""
const fs=require('fs');
const src=fs.readFileSync('trip.js','utf8').replace(/document\.querySelectorAll[\s\S]*$/,'');
const m=new Function(src+'; return {TRIP,BACKUPS,SITE_VERSION};')();
const stops=[];
m.TRIP.forEach(function(d){d.stops.forEach(function(s,i){stops.push({
  day:d.d, date:d.date, wd:d.wd, city:d.city, t:s.t, name:s.name,
  kind:s.kind||'', label:s.label||'', note:s.note||'', go:s.go||'',
  alt:s.alt||[], idx:i, last:i===d.stops.length-1
})})});
const backupNames=[];const backupItems=[];
m.BACKUPS.forEach(function(g){(g.items||[]).forEach(function(it){
  if(it&&it.names)it.names.forEach(function(n){backupNames.push(n)});
  backupItems.push({g:g.g, text:(typeof it==='string')?it:(it.text||'')});
})});
console.log(JSON.stringify({
  days:m.TRIP.map(function(d){return {d:d.d,date:d.date,wd:d.wd,city:d.city,
    n:d.stops.length}}),
  stops:stops, backupNames:backupNames, backupItems:backupItems,
  version:m.SITE_VERSION
}));
"""


def dump_trip():
    if not NODE:
        warn("找不到 node，跳過 trip.js 語法與行程邏輯檢查")
        return None
    r = subprocess.run([NODE, "--check", "trip.js"], capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        err("trip.js 語法錯誤：" + (r.stderr or "").strip().splitlines()[0])
        return None
    ok("trip.js 語法正確")
    r = subprocess.run([NODE, "-e", DUMP_JS], capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        err("trip.js 取值失敗：" + (r.stderr or "").strip()[:200])
        return None
    return json.loads(r.stdout)


WD = ["日", "一", "二", "三", "四", "五", "六"]

# 刻意不入庫的站點／備選：D6 包車日的自由用餐，由司導帶或現場挑，
# 沒有固定 POI。新增到這裡之前先確認不是打錯字或忘了跑 build_data.py。
KNOWN_OFF_DATA = {
    "午餐（都江堰當地美食·自由用餐）",
    "古城南街清真川菜（南街51號）",
    "西部牛仔清真餐廳（迎賓大道）",
}


def _mins(t):
    a, b = t.split(":")
    return int(a) * 60 + int(b)


def check_trip(trip, placenames):
    """placenames: {名稱: data.js 該筆} — 順便檢查行程用到的站點有沒有座標。"""
    bad = 0
    days = trip["days"]
    if len(days) != 9:
        err("天數 %d，應為 9" % len(days))
        bad += 1
    for i, d in enumerate(days):
        if d["d"] != i + 1:
            err("第 %d 天 d=%s" % (i + 1, d["d"]))
            bad += 1
        m, dd = (int(x) for x in d["date"].split("/"))
        real = WD[(datetime.date(2026, m, dd).weekday() + 1) % 7]
        if real != d["wd"]:
            err("%s 星期應為 %s，寫的是 %s" % (d["date"], real, d["wd"]))
            bad += 1
        if (m, dd) != (12, 4 + d["d"]):
            err("%s 與 Day %s 不對應（應為 12/%d）" % (d["date"], d["d"], 4 + d["d"]))
            bad += 1
        if not d["n"]:
            err("D%s 沒有站點" % d["d"])
            bad += 1

    byday = {}
    for s in trip["stops"]:
        byday.setdefault(s["day"], []).append(s)
    for day, ss in byday.items():
        for a, b in zip(ss, ss[1:]):
            if _mins(b["t"]) < _mins(a["t"]):
                err("D%s 時間逆行：%s → %s %s" % (day, a["t"], b["t"], b["name"]))
                bad += 1

    for s in trip["stops"]:
        for name, what in [(s["name"], "站點")] + [(a, "備選") for a in s["alt"]]:
            if name in KNOWN_OFF_DATA:
                continue
            if name not in placenames:
                err("D%s %s不在 data.js：%s" % (s["day"], what, name))
                bad += 1
            elif placenames[name].get("lat") in (None, ""):
                err("D%s %s沒有座標，地圖行程模式會斷線：%s"
                    % (s["day"], what, name))
                bad += 1
    for n in trip["backupNames"]:
        if n not in placenames:
            err("遺珠榜 names 參照不在 data.js：%s" % n)
            bad += 1

    # 每站都要有 go（最後一站除外），否則地圖行程模式接不起來
    for s in trip["stops"]:
        if not s["last"] and not s["go"]:
            warn("D%s %s %s 缺 go（往下一站的交通）" % (s["day"], s["t"], s["name"]))

    # 住宿連續性：8 晚
    night = []
    for d in sorted(byday):
        hotels = [s["name"] for s in byday[d] if s["kind"] == "hotel"]
        night.append(hotels[-1] if hotels else None)
    for i, h in enumerate(night[:8]):
        if not h:
            err("D%d 找不到當晚住宿" % (i + 1))
            bad += 1
    stay = Counter(h for h in night[:8] if h)
    changes = sum(1 for i in range(1, 8) if night[i] != night[i - 1])
    print("    住宿晚數 %s，換宿 %d 次" % (dict(stay), changes))
    if sum(stay.values()) != 8:
        err("住宿晚數合計不是 8 晚")
        bad += 1
    if not bad:
        ok("行程邏輯正確（9 天、日期↔星期、時間遞增、站點名稱、住宿連續性）")


# ── 6. 停留時間 ─────────────────────────────────────────────────────

def travel_cost(go):
    """從 go 文字估移動時間。
    「或／則」代表替代方案（打車 8 分 or 步行 20 分）→ 取最小的；
    同一方案內的多段（渡輪 20 分＋步行 8 分）才相加。"""
    if not go:
        return 0
    costs = []
    for alt in re.split(r"[，,；;]?\s*(?:或|則)\s*", go):
        n = [int(x) for x in re.findall(r"(\d+)\s*分", alt)]
        if n:
            costs.append(sum(n))
    return min(costs) if costs else 0


# 沒有 duration 欄位時的保底門檻（分鐘）——只抓明顯不合理的
FALLBACK_MIN = {"spot": 25, "meal": 40, "shop": 20}

# 刻意短停、不需要告警的站（打卡點、採買、順路茶飲）
SHORT_OK = {
    "鐘書閣（都江堰融創茂店）", "仰天窩大熊貓廣場",
    "紅旗連鎖（總府路店／總府分場）", "茶百道（重慶觀音橋陽光世紀店）",
}

# 包車／跟團日：整天由司導帶，實際離園與集合時間現場調整，
# 停留時間與營業時間比對都沒有意義（例：D6 都江堰景區 17:30 閉園，
# 但幾點出園是司導視當日進度決定的）。這裡整天略過那兩項檢查。
TOUR_DAYS = {6}

BASELINE_PATH = os.path.join("audit", "stay_baseline.json")


def load_baseline():
    if os.path.exists(BASELINE_PATH):
        try:
            return json.load(io.open(BASELINE_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {}


def need_minutes(place, kind):
    """這個地點「該待多久」。優先用 data 的 duration（例 '1.5-2小時'、'45分鐘'）
    ——取區間下限；沒有 duration 才退回站別保底門檻。"""
    raw = (place or {}).get("duration") or ""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[–~-]\s*\d+(?:\.\d+)?\s*)?"
                  r"(小時|小时|分鐘|分钟|分)", raw)
    if m:
        v = float(m.group(1))
        return int(v * 60) if m.group(2) in ("小時", "小时") else int(v)
    return FALLBACK_MIN.get(kind, 0)


def check_stay_duration(stops, byname):
    """站點實際停留（到下一站的間隔扣掉移動時間）是否足夠。

    門檻 = min(該地點建議 duration, 已核可基準線)。
    這樣既能擋「改了某一站把後面那站擠爆」的回歸，
    又不會對本來就刻意壓縮的站每次嘮叨。
    要重設基準線：python check_all.py --save-baseline"""
    base = load_baseline()
    save = "--save-baseline" in sys.argv
    newbase, bad = {}, 0
    for cur, nxt in zip(stops, stops[1:]):
        if cur["last"] or cur["kind"] in ("hotel", "move", ""):
            continue
        if cur["day"] in TOUR_DAYS:
            continue
        stay = _mins(nxt["t"]) - _mins(cur["t"]) - travel_cost(cur["go"])
        key = "%s|%s" % (cur["date"], cur["name"])
        newbase[key] = stay
        if cur["name"] in SHORT_OK:
            continue
        need = need_minutes(byname.get(cur["name"]), cur["kind"])
        if not need:
            continue
        limit = min(need, base.get(key, need))
        if stay < limit:
            extra = "" if limit == need else "（已核可基準 %d 分）" % limit
            warn("%s(%s) %s %s 實際只停 %d 分，建議 %d 分%s"
                 % (cur["date"], cur["wd"], cur["t"], cur["name"], stay, need, extra))
            bad += 1
    if save:
        os.makedirs("audit", exist_ok=True)
        json.dump(newbase, io.open(BASELINE_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, sort_keys=True)
        ok("已寫入停留基準線 %s（%d 站）" % (BASELINE_PATH, len(newbase)))
    elif not bad:
        ok("每站停留時間符合建議／已核可基準（已扣除移動時間、略過包車日 D%s）"
           % "/D".join(str(d) for d in sorted(TOUR_DAYS)))


# ── 7. 營業時間 ─────────────────────────────────────────────────────

ALLDAY = re.compile(r"全天|24\s*小時|24\s*小时|全年無休|不定")
RANGE = re.compile(r"(\d{1,2})[:：](\d{2})\s*[-–~－至到]\s*(?:次日)?(\d{1,2})[:：](\d{2})")


def hour_ranges(text):
    """把 hours 字串解析成 [(開, 關)] 分鐘區間；跨午夜的關門時間 +24h。"""
    out = []
    for h1, m1, h2, m2 in RANGE.findall(text or ""):
        a = int(h1) * 60 + int(m1)
        b = int(h2) * 60 + int(m2)
        if b <= a:
            b += 24 * 60
        out.append((a, b))
    return out


def check_hours(stops, byname):
    """抵達時間是否落在 data 記載的營業時間內。

    中國這邊沒有 Google Places 那種可程式查詢的權威來源
    （高德／大眾點評沒有公開免金鑰 API，網路上也難查到穩定的營業時間），
    所以改成「離線比對 data/*.json 已經記下來的 hours」。
    它擋不掉「hours 本身就抄錯」，但擋得掉「排的時間跟自己記的營業時間打架」
    ——這正是改行程時最常出的錯。hours 的可信度請在資料裡標示來源等級。"""
    bad = 0
    nohours = []
    for i, s in enumerate(stops):
        if s["kind"] in ("hotel", "move", "") or s["day"] in TOUR_DAYS:
            continue
        p = byname.get(s["name"])
        if not p:
            continue
        h = p.get("hours") or ""
        if not h or ALLDAY.search(h):
            continue
        rs = hour_ranges(h)
        if not rs:
            nohours.append(s["name"])
            continue
        arrive = _mins(s["t"])
        inside = [r for r in rs if r[0] <= arrive <= r[1]
                  or r[0] <= arrive + 24 * 60 <= r[1]]
        if not inside:
            err("%s(%s) %s %s 抵達時不在營業時段內（記載：%s）"
                % (s["date"], s["wd"], s["t"], s["name"], h[:60]))
            bad += 1
            continue
        if not s["last"]:
            leave = _mins(stops[i + 1]["t"]) - travel_cost(s["go"])
            close = max(r[1] for r in inside)
            if leave > close:
                warn("%s(%s) %s %s 排到 %02d:%02d 但約 %02d:%02d 打烊（記載：%s）"
                     % (s["date"], s["wd"], s["t"], s["name"],
                        leave // 60 % 24, leave % 60,
                        close // 60 % 24, close % 60, h[:40]))
                bad += 1
    if not bad:
        ok("抵達／離開時間與 data 記載的營業時間無衝突（略過包車日 D%s）"
           % "/D".join(str(d) for d in sorted(TOUR_DAYS)))
    if nohours:
        print("    （另有 %d 站 hours 沒有可解析的時段，無法比對：%s）"
              % (len(nohours), nohours[:4]))


# ── 8. note 修改歷程 ────────────────────────────────────────────────

# note 裡出現這些字眼 = 把修改歷程寫進了給使用者看的行程頁。
HISTORY_WORDS = [
    "原本排", "原本寫", "原本是", "原本的", "原規劃", "原方案", "原行程",
    "已改為", "已改成", "已換成", "換掉了", "取代原", "本次修正", "訂正",
    "先前寫", "原版", "比原", "原 D", "改以", "改早", "改搭",
    "已移到", "已移至", "暫移", "暫不排",
]

# 換過主站之後最容易在別處殘留的舊站名；每換掉一站就往這裡加一筆。
RETIRED = ["杜甫草堂", "磁器口", "兩江夜遊", "雍容薈", "寬窄巷子",
           "奎星樓街", "人民公園"]

# 有些「原」是地點屬性而非修改歷程（例：原址、原貌、原味）
# 有些字眼是現場應變說明而非修改歷程：「錯過班次可改搭索道」講的是當下怎麼辦。
HISTORY_CONTEXT_ALLOW = [r"原本就", r"原址", r"原貌", r"原味", r"原汁",
                         r"可改搭", r"錯過.{0,10}改搭"]


def check_note_history(stops):
    bad = 0
    for s in stops:
        note = s["note"]
        hits = []
        for w in HISTORY_WORDS:
            if w not in note:
                continue
            ctxs = [note[max(0, m.start() - 12):m.end() + 25]
                    for m in re.finditer(re.escape(w), note)]
            if all(any(re.search(p, c) for p in HISTORY_CONTEXT_ALLOW) for c in ctxs):
                continue
            hits.append(w)
        for m in re.finditer(r"20\d\d-\d\d-\d\d", note):
            ctx = note[max(0, m.start() - 25):m.end() + 25]
            if not re.search(r"回信|回覆|來信|公告|官網|租期|開幕|核對", ctx):
                hits.append("日期戳記(%s)" % m.group(0))
        if hits:
            warn("%s %s %s note 含修改歷程語言：%s"
                 % (s["date"], s["t"], s["name"], "、".join(hits)))
            bad += 1
    if not bad:
        ok("站點 note 無修改歷程語言（只講現況）")


# ── 9. 備選地雷 ─────────────────────────────────────────────────────

def check_alt_conflicts(stops):
    """備選清單裡不該出現 note 已點名「不要去／會撲空」的店。"""
    bad = 0
    for s in stops:
        for a in s["alt"]:
            if re.search(r"不要(改去|選|去)\s*[「『]?" + re.escape(a), s["note"]):
                err("%s %s %s note 說不要去「%s」，卻仍列在 alt 備選中"
                    % (s["date"], s["t"], s["name"], a))
                bad += 1
    if not bad:
        ok("備選清單無已知會撲空的店")


# ── 10. 遺珠榜 ──────────────────────────────────────────────────────

def check_backups(items):
    """遺珠榜 BACKUPS 也是使用者會讀的頁面，同樣不該留修改歷程或死掉的交叉引用。

    「為什麼沒排進去」是遺珠榜的本分，可以寫；
    但「原 D3 移除」「從 D2 暫移至備選」講的是使用者沒看過的舊草稿，
    「讓位給 D2 兩江夜遊」更是指向一個已經不存在的站點。

    RETIRED 站名出現在條目「標題」（冒號前）是正常的——那就是這條遺珠本身；
    出現在「說明」裡才是沒清乾淨的交叉引用。"""
    bad = 0
    for it in items:
        text = it["text"]
        hits = [w for w in HISTORY_WORDS if w in text
                and not any(re.search(pat, text) for pat in HISTORY_CONTEXT_ALLOW)]
        head, _, body = text.partition("：")
        for name in RETIRED:
            if name in body and name not in head:
                hits.append("已移除站點交叉引用(%s)" % name)
        if hits:
            warn("遺珠榜「%s」含修改歷程／失效引用：%s ← %s"
                 % (head[:24], "、".join(hits), text[:50]))
            bad += 1
    if not bad:
        ok("遺珠榜只講現況，無失效的交叉引用")


# ── 11. 跨檔殘留 ────────────────────────────────────────────────────

# changelog.html 是修改紀錄，本來就會寫舊站名，不列入檢查。
CROSS_FILES = ["prep.html", "guide.html", "itinerary.html", "restaurants.html"]


# 現行決策的字面鎖：prep.html 是純手寫的靜態頁（不像 itinerary/guide 由 trip.js 渲染），
# 行程一改就會漂掉，而站名比對抓不到「班次時間」「哪一餐」這種事實。
# 每次改動涉及訂位／購票／班次，就同步維護這兩張表。
FORBIDDEN = {
    "prep.html": [
        "約 14:00 成渝高鐵",      # D4 已改早班（約 10:00）
        "兩江夜遊",                # 已由 D2 長江索道取代
        "雍容薈 IFS二店</b>（帝王蟹午市）",  # D8 主餐已改海宴尚辰，雍容薈退為備選
        "重慶退房後寄放行李",      # D4 已改為退房直接帶走行李
    ],
}
REQUIRED = {
    "prep.html": [
        "約 10:00 成渝高鐵",
        "海宴尚辰",
        "長江索道（D2 夜間場次）",
    ],
}


def check_cross_file_facts(stops):
    """已從行程（含 alt）移除的站點，不該還出現在準備頁／攻略頁的待辦與購票說明裡；
    另外用 FORBIDDEN／REQUIRED 鎖住站名比對抓不到的現行決策（班次時間、哪一餐）。

    這是本專案與福岡專案共同的第二高頻錯誤來源：改了主站，沒清乾淨連帶物。"""
    live = set()
    for s in stops:
        live.add(s["name"])
        live.update(s["alt"])
    bad = 0
    for f in CROSS_FILES:
        if not os.path.exists(f):
            continue
        text = io.open(f, encoding="utf-8").read()
        for name in RETIRED:
            if any(name in n for n in live):
                continue
            if name in text:
                lines = [i + 1 for i, l in enumerate(text.splitlines()) if name in l]
                err("%s 殘留已從行程移除的「%s」（行 %s）" % (f, name, lines[:5]))
                bad += 1
    for f, phrases in FORBIDDEN.items():
        if not os.path.exists(f):
            continue
        text = io.open(f, encoding="utf-8").read()
        for ph in phrases:
            if ph in text:
                err("%s 殘留舊現況：%s" % (f, ph))
                bad += 1
    for f, phrases in REQUIRED.items():
        if not os.path.exists(f):
            continue
        text = io.open(f, encoding="utf-8").read()
        for ph in phrases:
            if ph not in text:
                err("%s 缺少現行決策：%s" % (f, ph))
                bad += 1
    if not bad:
        ok("prep.html／guide.html 等頁面與現行行程一致（無殘留、現行決策都在）")


# ── main ────────────────────────────────────────────────────────────

def main():
    print("=== 川渝專案健檢 ===\n")
    raw_places = load_data_dir()
    check_data(raw_places)
    check_data_js()
    check_version()

    dj = load_data_js()
    byname = {p["name"]: p for p in dj["PLACES"]}
    dup = [n for n, c in Counter(p["name"] for p in dj["PLACES"]).items() if c > 1]
    if dup:
        err("data.js 去重後仍有重複名稱（地圖會出現兩個圖釘）：%s" % dup)
    else:
        ok("data.js 去重後 %d 個地點、名稱無重複" % len(dj["PLACES"]))

    trip = dump_trip()
    if trip:
        check_trip(trip, byname)
        stops = trip["stops"]
        check_stay_duration(stops, byname)
        check_hours(stops, byname)
        check_note_history(stops)
        check_alt_conflicts(stops)
        check_backups(trip["backupItems"])
        check_cross_file_facts(stops)

    print("\n=== 錯誤 %d、警告 %d ===" % (len(ERR), len(WARN)))
    sys.exit(1 if ERR else 0)


if __name__ == "__main__":
    main()
