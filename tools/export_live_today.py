#!/usr/bin/env python3
"""sub PC の当日ライブログを rsync で吸い出し、data/live_today.json を生成する。
読み取り専用 (sub 側には一切書き込まない)。

usage: python3 tools/export_live_today.py [YYYYMMDD]
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

SUB = "sub"
REMOTE = "/home/sub/stack2tan/data/live"
REPO = Path(__file__).resolve().parent.parent
CACHE = Path("/tmp/botrace_live_cache")
ENGINES = ["t3w6", "condthird_sigma4_laneproj", "condthird_blend020"]


def rsync(src, dst):
    subprocess.run(["rsync", "-az", "--timeout=20", src, str(dst) + "/"],
                   capture_output=True)


def main():
    hd = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y%m%d")
    day = CACHE / hd
    day.mkdir(parents=True, exist_ok=True)
    rsync(f"{SUB}:{REMOTE}/{hd}/schedule.json", day)
    rsync(f"{SUB}:{REMOTE}/{hd}/micro_live/", day / "micro_live")
    for eng in ENGINES:
        rsync(f"{SUB}:{REMOTE}/{hd}/{eng}_bets/", day / f"{eng}_bets")

    sched = {}
    sp = day / "schedule.json"
    if sp.exists():
        for r in json.load(open(sp)):
            rid = f"{r['hd']}_{r['jcd']}_{int(r['rno']):02d}"
            sched[rid] = r

    settle = {}
    total = {"stake": 0, "payout": 0, "pnl": 0, "hits": 0}
    for f in (day / "micro_live").glob("*_capital_settlement.json"):
        try:
            s = json.load(open(f))
        except json.JSONDecodeError:
            continue
        eng = f.name.replace("_capital_settlement.json", "")
        for row in s.get("rows", []):
            settle[(eng, row["race_id"])] = row
        total["stake"] += s.get("stake_yen") or 0
        total["payout"] += s.get("payout_yen") or 0
        total["pnl"] += s.get("pnl_yen") or 0
        total["hits"] += sum(1 for r in s.get("rows", []) if r.get("hits"))

    races = []
    for eng in ENGINES:
        for f in sorted((day / f"{eng}_bets").glob("*.json")):
            try:
                d = json.load(open(f))
            except json.JSONDecodeError:
                continue
            rid = d.get("race_id", f.stem)
            dbg = d.get("debug", {})
            row = settle.get((eng, rid), {})
            bets = [{"k": b["kumi"], "o": b.get("odds"), "ev": round(b.get("ev", 0), 2),
                     "stake": b.get("stake")} for b in d.get("bets_final") or []]
            sc = sched.get(rid, {})
            races.append({
                "id": rid, "eng": eng,
                "venue": sc.get("venue_name"), "rno": sc.get("rno"),
                "deadline": sc.get("deadline"),
                "verdict": "bet" if bets else dbg.get("max_ev_gate", "no_ev"),
                "max_ev": dbg.get("max_ev"), "max_ev_kumi": dbg.get("max_ev_kumi"),
                "bets": bets,
                "win": row.get("winno_3t"), "pnl": row.get("pnl_yen"),
                "settled": row.get("status") == "settled",
            })
    races.sort(key=lambda r: (r["deadline"] or "99:99", r["id"], r["eng"]))

    out = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": hd,
        "n_scheduled": len(sched),
        "n_processed": len({r["id"] for r in races}),
        "n_bet_races": len({r["id"] for r in races if r["bets"]}),
        "total": total,
        "races": races,
    }
    dst = REPO / "data"
    dst.mkdir(exist_ok=True)
    with open(dst / "live_today.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"live_today.json: {out['n_processed']} processed / "
          f"{out['n_scheduled']} scheduled, pnl {total['pnl']}")


if __name__ == "__main__":
    main()
