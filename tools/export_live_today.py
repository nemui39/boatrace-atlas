#!/usr/bin/env python3
"""sub PC の当日ライブログを rsync で吸い出し、data/live_today.json を生成する。
読み取り専用 (sub 側には一切書き込まない)。

usage: python3 tools/export_live_today.py [YYYYMMDD]
"""
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

SUB = "sub"
REMOTE = "/home/sub/stack2tan/data/live"
REPO = Path(__file__).resolve().parent.parent
CACHE = Path("/tmp/botrace_live_cache")
STACK = Path("/home/nemui/stack2tan")


def fetch_result(hd, jcd, rno, cache_dir):
    """結果JSONをキャッシュ優先で取得 (stack2tanのfetch_raceresultを再利用)"""
    f = cache_dir / f"venue_{jcd}_race_{int(rno):02d}_raceresult.json"
    if f.exists():
        try:
            return json.load(open(f))
        except json.JSONDecodeError:
            pass
    sys.path.insert(0, str(STACK / "scripts"))
    try:
        from live_fetch import fetch_raceresult
        return fetch_raceresult(hd, jcd, int(rno), cache_dir)
    except Exception:
        return None


def detect_engines(hd):
    """実弾エンジン = micro_live/*_submissions を持つもの。無ければ *_bets 全部"""
    r = subprocess.run(
        ["ssh", SUB, f"ls -d {REMOTE}/{hd}/micro_live/*_submissions "
                     f"{REMOTE}/{hd}/*_bets 2>/dev/null"],
        capture_output=True, text=True)
    subs, bets = [], []
    for line in r.stdout.split():
        name = Path(line).name
        if name.endswith("_submissions"):
            subs.append(name[:-len("_submissions")])
        elif name.endswith("_bets"):
            bets.append(name[:-len("_bets")])
    return subs or bets


def rsync(src, dst):
    subprocess.run(["rsync", "-az", "--timeout=20", src, str(dst) + "/"],
                   capture_output=True)


def main():
    hd = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y%m%d")
    day = CACHE / hd
    day.mkdir(parents=True, exist_ok=True)
    engines = detect_engines(hd)
    print("engines:", engines)
    rsync(f"{SUB}:{REMOTE}/{hd}/schedule.json", day)
    rsync(f"{SUB}:{REMOTE}/{hd}/micro_live/", day / "micro_live")
    for eng in engines:
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

    # 実送信レシート(bet-serverが受理した額)が賭金の正
    receipts = {}
    for eng in engines:
        for f in (day / "micro_live" / f"{eng}_submissions").glob("*_live.json"):
            try:
                rc = json.load(open(f))
            except json.JSONDecodeError:
                continue
            rid = rc.get("source_race_id") or f.stem.replace("_live", "")
            res = rc.get("result") or {}
            if rc.get("status") != "submitted_success" and res.get("status") != "success":
                continue
            receipts[(eng, rid)] = {
                b["combo"].replace("-", ""): b["amount"]
                for b in (rc.get("payload") or {}).get("bets", [])}

    races = []
    for eng in engines:
        for f in sorted((day / f"{eng}_bets").glob("*.json")):
            try:
                d = json.load(open(f))
            except json.JSONDecodeError:
                continue
            rid = d.get("race_id", f.stem)
            if not rid.startswith(hd):
                continue  # 当日以外(朝の試行ログ等)を除外
            dbg = d.get("debug", {})
            row = settle.get((eng, rid), {})
            amts = receipts.get((eng, rid))
            bf = d.get("bets_final") or []
            if amts is not None:
                bets = [{"k": b["kumi"], "o": b.get("odds"),
                         "ev": round(b.get("ev", 0), 2), "stake": amts[b["kumi"]]}
                        for b in bf if b["kumi"] in amts]
                for k, a in amts.items():
                    if not any(x["k"] == k for x in bets):
                        bets.append({"k": k, "o": None, "ev": None, "stake": a})
            else:
                bets = [{"k": b["kumi"], "o": b.get("odds"),
                         "ev": round(b.get("ev", 0), 2), "stake": b.get("stake")}
                        for b in bf]
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
                "detail": {
                    "s": [round(x, 3) for x in dbg.get("s_values", [])],
                    "mu": [round(x, 1) for x in dbg.get("ts_mu", [])],
                    "sg": [round(x, 2) for x in dbg.get("ts_sigma", [])],
                    "wr": [round(x, 3) for x in dbg.get("weather_wr", [])],
                    "t5": [{"k": t["kumi"], "p": round(t["prob"], 4)}
                           for t in d.get("p_final_top5") or []],
                    "med": dbg.get("ev_median_120"), "p90": dbg.get("ev_p90_120"),
                    "nb": dbg.get("n_odds_in_band"),
                    "mev": dbg.get("max_ev"), "mevk": dbg.get("max_ev_kumi"),
                    "mevo": dbg.get("max_ev_odds")},
            })
    # 暫定精算: 本体settle未反映のBETレースは自前で結果を取得しPnLを仮確定
    rescache = day / "results"
    rescache.mkdir(exist_ok=True)
    now = datetime.datetime.now()
    nmin = now.hour * 60 + now.minute
    for r in races:
        if not r["bets"] or r["pnl"] is not None or not r.get("deadline"):
            continue
        h, m = r["deadline"].split(":")
        if nmin < int(h) * 60 + int(m) + 6:  # 結果確定待ち
            continue
        _, jcd, rno = r["id"].split("_")
        rr = fetch_result(hd, jcd, rno, rescache)
        if not rr:
            continue
        try:
            i3 = rr["maindata"]["infolist3t"][0]
            win = i3["winno"]
            div = int(re.sub(r"[^0-9]", "", i3.get("dividend") or "") or 0)
        except (KeyError, IndexError, TypeError):
            continue
        wk = win.replace("-", "")
        payout = sum(b["stake"] // 100 * div for b in r["bets"] if b["k"] == wk)
        stake = sum(b["stake"] for b in r["bets"])
        r["win"] = win
        r["pnl"] = payout - stake
        r["prov"] = True
        total["stake"] += stake
        total["payout"] += payout
        total["pnl"] += payout - stake
        if payout:
            total["hits"] += 1

    races.sort(key=lambda r: (r["deadline"] or "99:99", r["id"], r["eng"]))

    schedule = [{"id": rid, "v": r.get("venue_name"), "jcd": r["jcd"],
                 "rno": r["rno"], "dl": r.get("deadline")}
                for rid, r in sorted(sched.items(),
                                     key=lambda kv: kv[1].get("deadline") or "99")]
    out = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": hd,
        "n_scheduled": len(sched),
        "schedule": schedule,
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
