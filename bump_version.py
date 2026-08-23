#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步全站版號（快取破壞用）。

    python bump_version.py            # 全部 +1，並把 SITE_UPDATED_AT 改成今天
    python bump_version.py --set 140  # 指定版號
    python bump_version.py --check    # 只檢查一致性，不改檔（不一致回傳 1）

版號散落三種寫法、共 23 處，任何一處漏改都會讓使用者吃到舊快取：
  1. `data.js?v=N` / `trip.js?v=N`      HTML 的 script/preload（避免瀏覽器快取舊資料）
  2. `caches.open('sichuan-app-vN')`    各頁 warm-up 腳本 ＋ sw.js 的 APP_CACHE
                                        （只改 1 沒改這個，PWA 會一直吃舊殼層）
  3. `SITE_VERSION="vN"`                trip.js，頁尾顯示用
"""
import datetime
import io
import os
import re
import sys

FILES = ["guide.html", "itinerary.html", "map.html", "prep.html",
         "restaurants.html", "sw.js", "trip.js"]

PATTERNS = [
    (re.compile(r"(\?v=)(\d+)"), "?v="),
    (re.compile(r"(sichuan-app-v)(\d+)"), "sichuan-app-v"),
    (re.compile(r"(SITE_VERSION\s*=\s*\"v)(\d+)"), "SITE_VERSION"),
]


def read(path):
    return io.open(path, encoding="utf-8").read()


def write(path, text):
    # 讀進來時 universal newlines 已把 CRLF 轉成 \n；用預設文字模式寫回，
    # Windows 會還原成 CRLF，與 repo 現況一致。
    io.open(path, "w", encoding="utf-8").write(text)


def scan():
    """回傳 {版號: [出處, ...]}。"""
    found = {}
    for f in FILES:
        if not os.path.exists(f):
            continue
        text = read(f)
        for rx, label in PATTERNS:
            for m in rx.finditer(text):
                found.setdefault(int(m.group(2)), []).append(f"{f}:{label}")
    return found


def main():
    args = sys.argv[1:]
    found = scan()
    if not found:
        print("❌ 找不到任何版號標記")
        return 1
    total = sum(len(v) for v in found.values())

    if "--check" in args:
        if len(found) > 1:
            for v in sorted(found):
                print(f"   v{v}：{len(found[v])} 處 → {sorted(set(found[v]))}")
            print(f"❌ 版號不一致，共 {len(found)} 種：{sorted(found)}")
            return 1
        print(f"✅ 版號一致 v{list(found)[0]}（{total} 處）")
        return 0

    cur = max(found)
    if "--set" in args:
        new = int(args[args.index("--set") + 1])
    else:
        new = cur + 1

    today = datetime.date.today().strftime("%Y/%m/%d")
    for f in FILES:
        if not os.path.exists(f):
            continue
        text = orig = read(f)
        for rx, _ in PATTERNS:
            text = rx.sub(lambda m: m.group(1) + str(new), text)
        text = re.sub(r"(SITE_UPDATED_AT\s*=\s*\")[^\"]*(\")",
                      lambda m: m.group(1) + today + m.group(2), text)
        if text != orig:
            write(f, text)
    print(f"✅ 版號 v{cur} → v{new}（{total} 處）、SITE_UPDATED_AT = {today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
