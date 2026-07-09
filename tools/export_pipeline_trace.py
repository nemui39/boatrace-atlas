#!/usr/bin/env python3
"""stack2tan の実運用ログから、1レースがパイプラインを通るトレースを抽出して
サイト埋め込み用の JS (var TRACES=[...]) を生成する。読み取り専用。

usage: python3 export_pipeline_trace.py <hd> <engine> <race_id...>
   ex: python3 export_pipeline_trace.py 20260529 t3w6 20260529_15_02 20260529_07_06
"""
import json
import sys
from pathlib import Path

LIVE = Path("/home/nemui/stack2tan/data/live")


def fnum(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def load(p):
    with open(p) as f:
        return json.load(f)


def r3(x):
    return round(x, 4) if isinstance(x, float) else x


def export_race(hd, engine, race_id, settle_rows):
    d = LIVE / hd
    _, jcd, rno = race_id.split("_")
    rc = load(d / f"venue_{jcd}_race_{rno}_racecard.json")
    bi = load(d / f"venue_{jcd}_race_{rno}_beforeinfo.json")
    o3 = load(d / f"odds/venue_{jcd}_race_{rno}_odds3t.json")
    bt = load(d / f"{engine}_bets/{race_id}.json")
    row = settle_rows.get(race_id, {})

    m = rc["maindata"]
    racers = [{
        "no": int(t["teino"]),
        "name": t["racername"].replace("　", " ").strip(),
        "cls": t["classname"],
        "zwin": fnum(t.get("zwinper")),
        "motor2": fnum(t.get("motor2per")),
        "avest": fnum(t.get("avest")),
    } for t in m["teiinfolist"]]

    bm = bi["maindata"]
    ex = {int(t["teino"]): fnum(t.get("extime")) for t in bm["teiinfolist"]}
    tilt = {int(t["teino"]): fnum(t.get("tilt")) for t in bm["teiinfolist"]}
    st_rows = [{"c": s.get("csdisp") or s.get("cs"), "no": int(s["teino"]),
                "st": s.get("st")} for s in bm.get("sttenjiinfolist", [])]
    w = bm.get("weatherinfo", {})

    ol = o3["maindata"]["odds3tlist"]
    odds_pairs = []
    for e in ol:
        o = fnum(e.get("odds"))
        if o:
            odds_pairs.append({"k": e["kumi"].replace("-", ""), "o": o})
    odds_top = sorted(odds_pairs, key=lambda x: x["o"])[:5]

    dbg = bt.get("debug", {})
    settle_bets = {b["combo"].replace("-", ""): b for b in row.get("bets", [])}
    bets = []
    for b in bt.get("bets_final") or []:
        sb = settle_bets.get(b["kumi"], {})
        bets.append({
            "k": b["kumi"], "o": b["odds"],
            "pm": r3(b["p_model"]), "pmkt": r3(b["p_market"]),
            "ev": r3(b["ev"]), "edge": r3(b.get("edge")),
            "stake": b["stake"],
            "hit": sb.get("hit"), "pnl": sb.get("pnl_yen"),
        })

    return {
        "id": race_id,
        "date": hd,
        "venue": rc["holdingheader"]["jname"].replace("　", ""),
        "jcd": jcd, "rno": int(rno),
        "ktitle": rc["holdingheader"].get("ktitle"),
        "grade": rc["holdingheader"].get("tbgradename"),
        "deadline": m.get("deadline"),
        "engine": engine,
        "t_racecard": rc["dataheader"].get("cdatetime"),
        "t_before": bi["dataheader"].get("cdatetime"),
        "t_odds": o3["maindata"].get("updatetime"),
        "racers": racers,
        "tenji": {
            "ex": [ex.get(i) for i in range(1, 7)],
            "tilt": [tilt.get(i) for i in range(1, 7)],
            "st": st_rows,
        },
        "weather": {"desc": w.get("weather"), "wind": fnum(w.get("wind")),
                    "wdir": w.get("winddirec"), "wave": fnum(w.get("wave")),
                    "temp": fnum(w.get("temp")), "water": fnum(w.get("water"))},
        "odds": {"n": len(ol), "final": o3["maindata"].get("finalodds"),
                 "top": odds_top},
        "state": {"ts_mu": [r3(x) for x in dbg.get("ts_mu", [])],
                  "ts_sigma": [r3(x) for x in dbg.get("ts_sigma", [])],
                  "wwr": [r3(x) for x in dbg.get("weather_wr", [])],
                  "wind_bin": dbg.get("wind_bin")},
        "model": {"s": [r3(x) for x in dbg.get("s_values", [])],
                  "top5": [{"k": t["kumi"], "p": r3(t["prob"])}
                           for t in bt.get("p_final_top5") or []]},
        "gate": {"max_ev": dbg.get("max_ev"), "kumi": dbg.get("max_ev_kumi"),
                 "odds": dbg.get("max_ev_odds"),
                 "ev_med": dbg.get("ev_median_120"), "ev_p90": dbg.get("ev_p90_120"),
                 "n_band": dbg.get("n_odds_in_band"),
                 "n_ev11": dbg.get("n_ev_above_1.1"), "n_ev12": dbg.get("n_ev_above_1.2"),
                 "verdict": "bet" if bets else dbg.get("max_ev_gate", "no_ev")},
        "bets": bets,
        "result": {"win": row.get("winno_3t"), "div": row.get("dividend_3t"),
                   "stake": row.get("stake_yen"), "payout": row.get("payout_yen"),
                   "pnl": row.get("pnl_yen")},
    }


def main():
    hd, engine = sys.argv[1], sys.argv[2]
    race_ids = sys.argv[3:]
    settle = load(LIVE / hd / f"micro_live/{engine}_capital_settlement.json")
    rows = {r["race_id"]: r for r in settle.get("rows", [])}
    traces = [export_race(hd, engine, rid, rows) for rid in race_ids]
    out = "var TRACES=" + json.dumps(traces, ensure_ascii=False,
                                     separators=(",", ":")) + ";"
    Path("traces.js").write_text(out)
    print(f"wrote traces.js ({len(out)} chars, {len(traces)} races)")
    for t in traces:
        print(" ", t["id"], t["venue"], t["gate"]["verdict"],
              "bets:", len(t["bets"]), "pnl:", t["result"]["pnl"])


if __name__ == "__main__":
    main()
