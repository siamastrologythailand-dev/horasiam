# -*- coding: utf-8 -*-
"""
ดึงยอดผู้เข้าชื่อ ร่าง พ.ร.บ. หลักประกันสุขภาพแห่งชาติ จาก einitiative.parliament.go.th
แล้วอัปเดตไฟล์ของแดชบอร์ดใน uc-dashboard/

- uc-dashboard/data.json       เขียนใหม่เฉพาะเมื่อยอดหรือรายชื่อร่างเปลี่ยน
- uc-dashboard/snapshots.json  บันทึกยอดวันละครั้งหลัง 18:00 น. (ใช้คิดยอด + ของวันถัดไป)

รันโดย .github/workflows/uc-dashboard.yml  (รันในเครื่องก็ได้: python .github/scripts/uc_dashboard_update.py)
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://einitiative.parliament.go.th/api/drafting-law/draft-law-list"
KEYWORD = "หลักประกันสุขภาพ"
# ลำดับการแสดงผล: ฉบับที่ 1 = นายอนุกูล, ฉบับที่ 2 = ผศ.สนั่น (ฉบับอื่นที่เข้าเงื่อนไขจะต่อท้าย)
ORDER = [
    "1e9628df-7187-4413-8612-b1f3e862c892",
    "791ae9a7-ec15-4543-98cf-dd9f3985cc6c",
]
SNAPSHOT_HOUR = 18
KEEP_DAYS = 400
TZ = timezone(timedelta(hours=7))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "uc-dashboard")
DATA = os.path.join(OUT, "data.json")
SNAPSHOTS = os.path.join(OUT, "snapshots.json")


def fetch_items():
    req = urllib.request.Request(
        API_URL,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (uc-dashboard; +https://github.com/siamastrologythailand-dev/horasiam)",
        },
    )
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:  # retry transient network errors
            last_error = e
            time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"fetch failed: {last_error}")

    items = []
    for d in payload.get("all") or []:
        headline = d.get("headline") or ""
        if KEYWORD not in (d.get("file_name") or "") + headline:
            continue
        m = re.search(r"\((.+?)\s*ผู้เสนอ\)", headline)
        proposer = re.sub(r"\s+", " ", m.group(1)).strip() if m else headline
        items.append({
            "id": d.get("id"),
            "proposer": proposer,
            "voters": int(d.get("voter_no") or 0),
        })
    rank = {id_: i for i, id_ in enumerate(ORDER)}
    items.sort(key=lambda it: rank.get(it["id"], len(ORDER)))
    return items


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def dump(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    now = datetime.now(TZ)
    items = fetch_items()
    if not items:
        raise SystemExit("no matching drafts in the parliament list")

    changed = []
    data = load(DATA, {})
    if data.get("items") != items:
        dump(DATA, {"updatedAt": now.isoformat(timespec="seconds"), "items": items})
        changed.append("data")

    snaps = load(SNAPSHOTS, {})
    today = now.strftime("%Y-%m-%d")
    if now.hour >= SNAPSHOT_HOUR and today not in snaps:
        snaps[today] = {
            "time": now.strftime("%H:%M"),
            "counts": {it["id"]: it["voters"] for it in items},
            "savedAt": now.isoformat(timespec="seconds"),
        }
        cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
        dump(SNAPSHOTS, {k: v for k, v in snaps.items() if k >= cutoff})
        changed.append("snapshot")

    counts = ", ".join(f"{it['proposer']}={it['voters']}" for it in items)
    print(f"{now:%Y-%m-%d %H:%M} {counts} | changed: {', '.join(changed) or 'nothing'}")


if __name__ == "__main__":
    main()
