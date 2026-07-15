#!/usr/bin/env python3
"""Apply the recorded Amap coordinate audit to source JSON files."""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

from zhconv import convert


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "audit" / "amap_coordinates_2026-07-15.json"


def norm_name(value: str) -> str:
    value = convert(value or "", "zh-cn")
    return re.sub(r"\s+", "", value.replace("（", "(").replace("）", ")").replace("·", "").replace(".", ""))


def city_for(path: Path, item: dict) -> str:
    city = item.get("city", "")
    if city in ("成都", "重庆"):
        return city
    name = path.name.lower()
    if "chengdu" in name:
        return "成都"
    if "chongqing" in name:
        return "重庆"
    return city


def object_spans(text: str):
    decoder = json.JSONDecoder()
    pos = text.find("[") + 1
    while pos > 0:
        while pos < len(text) and (text[pos].isspace() or text[pos] == ","):
            pos += 1
        if pos >= len(text) or text[pos] == "]":
            return
        value, end = decoder.raw_decode(text, pos)
        yield pos, end, value
        pos = end


def render_like(original: str, value: dict, line_prefix: str) -> str:
    if "\n" not in original:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    rendered = json.dumps(value, ensure_ascii=False, indent=2)
    return rendered.replace("\n", "\n" + line_prefix)


def main() -> None:
    payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit = {(p["city"], norm_name(p["name"])): p for p in payload["places"]}
    matched = set()
    updated_rows = 0
    touched_files = 0

    for filename in sorted(glob.glob(str(ROOT / "data" / "*.json"))):
        path = Path(filename)
        if path.name.startswith(("guides", "ratings", "tours")):
            continue
        text = path.read_text(encoding="utf-8")
        replacements = []
        for start, end, item in object_spans(text):
            if not isinstance(item, dict) or not item.get("name") or "lat" not in item or "lng" not in item:
                continue
            key = (city_for(path, item), norm_name(item["name"]))
            result = audit.get(key)
            if not result:
                continue
            matched.add(key)
            if result["status"] == "verified":
                item["address"] = result["address"]
                item["lat"] = result["lat"]
                item["lng"] = result["lng"]
                item["amap_poiid"] = result["amap_poiid"]
                item["coordinate_status"] = "verified"
                item["coordinate_source"] = "高德地图 GCJ-02（2026-07-15核对）"
            else:
                item["lat"] = None
                item["lng"] = None
                item.pop("amap_poiid", None)
                item["coordinate_status"] = "unverified"
                item["coordinate_source"] = "高德地图未可靠匹配（2026-07-15，地图暂不显示）"

            line_start = text.rfind("\n", 0, start) + 1
            prefix = text[line_start:start]
            replacements.append((start, end, render_like(text[start:end], item, prefix)))
            updated_rows += 1

        if replacements:
            for start, end, rendered in reversed(replacements):
                text = text[:start] + rendered + text[end:]
            path.write_text(text, encoding="utf-8")
            touched_files += 1

    missing = sorted(set(audit) - matched)
    print(f"updated_rows={updated_rows} touched_files={touched_files} matched_audit={len(matched)}/{len(audit)}")
    if missing:
        print("missing audit keys:")
        for city, name in missing:
            print(f"  {city} {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
