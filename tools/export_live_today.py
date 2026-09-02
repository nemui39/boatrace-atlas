#!/usr/bin/env python3
"""sub PC の当日ライブログを rsync で吸い出し、data/live_today.json を生成する。
読み取り専用 (sub 側には一切書き込まない)。

usage: python3 tools/export_live_today.py [YYYYMMDD]
"""
import datetime
import json
import re
import subprocess
import time
import sys
from pathlib import Path

SUB = "sub"
REMOTE = "/home/sub/stack2tan/data/live"
REPO = Path(__file__).resolve().parent.parent
CACHE = Path("/tmp/botrace_live_cache")
STACK = Path("/home/nemui/stack2tan")
# 実弾micro_liveから外れても、診断表示だけ継続するshadowエンジン。
# bets_finalは公開側で無効化し、賭金・収支へは混ぜない。
DISPLAY_ONLY_ENGINES = set()
# 実弾昇格済みだがpreflight/submissionsを出す前でも拾いたいエンジン
FORCE_LIVE_ENGINES = {"t3w6_calB"}
# 推論artifactのdir名が "<eng>_bets" でないエンジン
BETS_DIR_ALIAS = {"market_rank_kl_delta015": "market_rank_kl_delta015_forward_shadow_bets",
                  # 正式チャンピオン(family_ens_w070 δ0.05): source artifact→dispatcher実弾化
                  "family_ens_w070_delta005": "formal_champion_forward_source_v1/artifacts"}
# 無送信shadow形式のartifactを実弾ディスパッチする系(KL): 上位キー由来の指標
KL_META_KEYS = ("roi_role", "maturity_decision_use", "band_counts",
                "decision", "forward_eligibility", "projection", "runtime_snapshot")


def adapt_formal_champion(d):
    """正式チャンピオンのsource artifactをKL型(120配列+bets_final)へ正規化する。
    decision.candidate_bets(死亡済み残差候補)は送信禁止なので一切使わない。"""
    dec = d.get("decision")
    if not isinstance(dec, dict) or "formal_bets" not in dec or d.get("ev_120"):
        return d
    inp, prob = d.get("input") or {}, d.get("probability") or {}
    ko, od, pf = inp.get("kumi_order_120"), inp.get("odds_120"), prob.get("p0_decision")
    if not (ko and od and pf) or len(pf) != len(od):
        return d
    d["kumi_order_120"], d["odds_120"], d["p_final_120"] = ko, od, pf
    d["p_market_120"] = prob.get("market120")
    d["ev_120"] = [p * o for p, o in zip(pf, od)]
    d["bets_final"] = dec.get("formal_bets") or []
    d["band_counts"] = dec.get("band_counts")
    # 指標一覧へは正式側の集計だけ出す(死亡済み候補の名前を画面に出さない)
    d["decision"] = {k: v for k, v in dec.items() if not k.startswith("candidate")}
    d["_gate_no_ticket"] = "fc_no_ticket"
    return d


def bets_dir(eng):
    return BETS_DIR_ALIAS.get(eng, f"{eng}_bets")


def fnum(x, default=None):
    if x is None:
        return default
    s = re.sub(r"[^0-9.\-]", "", str(x))
    try:
        return float(s)
    except ValueError:
        return default


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
    """実弾エンジンに、存在する観測専用エンジンを加えて返す。"""
    r = subprocess.run(
        ["ssh", SUB, f"ls -d {REMOTE}/{hd}/micro_live/*_submissions "
                     f"{REMOTE}/{hd}/micro_live/*_preflight.json "
                     f"{REMOTE}/{hd}/micro_live/*_dispatch "
                     f"{REMOTE}/{hd}/*_bets 2>/dev/null"],
        capture_output=True, text=True)
    live, bets = set(), set()
    for line in r.stdout.split():
        name = Path(line).name
        if name.endswith("_submissions"):
            live.add(name[:-len("_submissions")])
        elif name.endswith("_preflight.json"):
            live.add(name[:-len("_preflight.json")])
        elif name.endswith("_dispatch"):
            live.add(name[:-len("_dispatch")])
        elif name.endswith("_bets"):
            bets.add(name[:-len("_bets")])
    active = (live | (FORCE_LIVE_ENGINES & bets)) or bets
    display_only = (DISPLAY_ONLY_ENGINES & bets) - active
    return sorted(active | display_only), display_only


def _now_hm_minus(dl):
    """締切"HH:MM"から現在までの経過分(締切前なら負)。"""
    try:
        now = datetime.datetime.now()
        h, m = map(int, str(dl).split(":"))
        return (now - now.replace(hour=h, minute=m, second=0,
                                  microsecond=0)).total_seconds() / 60
    except (ValueError, AttributeError):
        return -9999


def rsync(src, dst):
    subprocess.run(["rsync", "-az", "--timeout=20", src, str(dst) + "/"],
                   capture_output=True)


def main():
    hd = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime("%Y%m%d")
    day = CACHE / hd
    day.mkdir(parents=True, exist_ok=True)
    engines, display_only = detect_engines(hd)
    print("engines:", engines, "display_only:", sorted(display_only))
    rsync(f"{SUB}:{REMOTE}/{hd}/schedule.json", day)
    rsync(f"{SUB}:{REMOTE}/{hd}/morning_status.json", day)
    rsync(f"{SUB}:{REMOTE}/{hd}/venue_*_racecard.json", day / "cards")
    rsync(f"{SUB}:/home/sub/stack2tan/data/json/{hd[:4]}/{hd[4:6]}/{hd[6:]}/"
          f"venue_*_oddstf.json", day / "oddstf")
    rsync(f"{SUB}:{REMOTE}/{hd}/micro_live/", day / "micro_live")
    for eng in engines:
        (day / bets_dir(eng)).mkdir(parents=True, exist_ok=True)
        rsync(f"{SUB}:{REMOTE}/{hd}/{bets_dir(eng)}/", day / bets_dir(eng))

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
    blocked = {}
    for eng in engines:
        for f in (day / "micro_live" / f"{eng}_submissions").glob("*_live.json"):
            try:
                rc = json.load(open(f))
            except json.JSONDecodeError:
                continue
            rid = rc.get("source_race_id") or f.stem.replace("_live", "")
            res = rc.get("result") or {}
            if rc.get("status") != "submitted_success" and res.get("status") != "success":
                # 送信前ガード遮断等: 実弾は出ていないので賭金0として記録
                blocked[(eng, rid)] = rc.get("status") or res.get("status") or "blocked"
                continue
            receipts[(eng, rid)] = {
                b["combo"].replace("-", ""): b["amount"]
                for b in (rc.get("payload") or {}).get("bets", [])}
        # KL型: ディスパッチ受領票(重複除去/締切/sender遮断)
        for f in (day / "micro_live" / f"{eng}_dispatch").glob("*.json"):
            try:
                dr = json.load(open(f))
            except json.JSONDecodeError:
                continue
            rid = dr.get("race_id") or f.stem
            st, reason = dr.get("status"), str(dr.get("reason") or "")
            if st in ("submitted", "admitted", "already_attempted"):
                continue
            pre = "fc_" if eng.startswith("family_ens") else "kl_"
            if "overlap" in reason or "dedup" in reason:
                blocked.setdefault((eng, rid), pre + "overlap")
            elif "deadline" in reason or "remaining" in reason:
                blocked.setdefault((eng, rid), pre + "deadline")
            else:
                blocked.setdefault((eng, rid), pre + str(st))

    races = []
    for eng in engines:
        is_observer = eng in display_only
        for f in sorted((day / bets_dir(eng)).glob("*.json")):
            try:
                d = json.load(open(f))
            except json.JSONDecodeError:
                continue
            rid = d.get("race_id", f.stem)
            if not rid or not rid.startswith(hd):
                continue  # 当日以外(朝の試行ログ等)/preflight等の非レースJSONを除外
            d = adapt_formal_champion(d)
            dbg = d.get("debug") or {}
            if not dbg and isinstance(d.get("ev_120"), list) and d.get("kumi_order_120"):
                # KL型: debug無し。120配列から同等指標を合成
                ev, ko0, od = d["ev_120"], d["kumi_order_120"], d.get("odds_120") or []
                i0 = max(range(len(ev)), key=lambda i: ev[i])
                sv = sorted(ev)
                dbg = {"max_ev": round(ev[i0], 4), "max_ev_kumi": str(ko0[i0]).replace("-", ""),
                       "max_ev_odds": od[i0] if i0 < len(od) else None,
                       "ev_median_120": round(sv[len(sv) // 2], 4),
                       "ev_p90_120": round(sv[int(len(sv) * 0.9)], 4),
                       "n_odds_in_band": None,
                       "max_ev_gate": d.get("_gate_no_ticket", "kl_no_ticket")}
                for k in KL_META_KEYS:
                    if d.get(k) is not None:
                        dbg[k] = d[k]
            row = settle.get((eng, rid), {})
            amts = receipts.get((eng, rid))
            bf = d.get("bets_final") or []
            if amts is not None:
                bets = [{"k": b["kumi"], "o": b.get("odds"),
                         "ev": round(b.get("ev", 0), 2), "stake": amts[b["kumi"]],
                         "pm": round(b["p_model"], 5) if b.get("p_model") else None}
                        for b in bf if b["kumi"] in amts]
                for k, a in amts.items():
                    if not any(x["k"] == k for x in bets):
                        bets.append({"k": k, "o": None, "ev": None, "stake": a})
            else:
                bets = [{"k": b["kumi"], "o": b.get("odds"),
                         "ev": round(b.get("ev", 0), 2),
                         # 紙上stake(KLのstake=4800等)を実弾表示に使わない
                         "stake": b.get("stake_flat100") or b.get("stake"),
                         "pm": round(b["p_model"], 5) if b.get("p_model") else None}
                        for b in bf]
            blk = blocked.get((eng, rid))
            if blk and not bf:
                blk = None  # 券なしレースの受領票は遮断でなく単なる見送り
            if blk and amts is None:
                bets = []  # ガード遮断: 意図買い目はあるが未送信=賭金0
            elif bets and amts is None:
                # 実弾エンジンなのに締切+2分を過ぎてもreceiptが無い=送信未確認。
                # 実額が証明できないので成績へ入れない(送信経路の欠陥検知を兼ねる)
                sc0 = sched.get(rid, {})
                dl0 = sc0.get("deadline")
                if dl0 and _now_hm_minus(dl0) >= 2:
                    bets = []
                    blk = "no_receipt"
            if is_observer:
                bets = []  # shadowの疑似買い目を実弾成績へ混ぜない
            # debug全フィールドの自動吸い上げ (スカラー+1段ネスト辞書)
            SKIP = {"max_ev", "max_ev_kumi", "max_ev_odds", "ev_median_120",
                    "ev_p90_120", "n_odds_in_band", "s_values", "ts_mu",
                    "ts_sigma", "weather_wr"}
            extra = {}
            for k, v in dbg.items():
                if k in SKIP:
                    continue
                if isinstance(v, bool) or isinstance(v, (int, str)):
                    extra[k] = str(v)[:60] if isinstance(v, str) else v
                elif isinstance(v, float):
                    extra[k] = round(v, 4)
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, bool) or isinstance(v2, (int, str)):
                            extra[f"{k}.{k2}"] = (str(v2)[:60]
                                                  if isinstance(v2, str) else v2)
                        elif isinstance(v2, float):
                            extra[f"{k}.{k2}"] = round(v2, 4)
            pf, ko = d.get("p_final_120"), d.get("kumi_order_120")
            if pf and ko:
                t5 = [{"k": str(k2).replace("-", ""), "p": round(p2, 4)}
                      for k2, p2 in sorted(zip(ko, pf), key=lambda x: -x[1])[:30]]
            else:
                t5 = [{"k": t["kumi"], "p": round(t["prob"], 4)}
                      for t in d.get("p_final_top5") or []]
            for k in ("candidate", "package_for_day", "gate_score", "day_metric_a",
                      "day_metric_b", "day_metric_combo", "state_mode",
                      "observation_only"):
                v = d.get(k)
                if isinstance(v, bool) or isinstance(v, (int, str)):
                    extra[k] = str(v)[:60] if isinstance(v, str) else v
                elif isinstance(v, float):
                    extra[k] = round(v, 4)
            sc = sched.get(rid, {})
            races.append({
                "id": rid, "eng": eng,
                "obs": is_observer,
                "venue": sc.get("venue_name"), "rno": sc.get("rno"),
                "deadline": sc.get("deadline"),
                "verdict": ("observe" if is_observer else
                            ("blocked:" + blk if (blk and not bets) else
                             ("bet" if bets else dbg.get("max_ev_gate", "no_ev")))),
                "max_ev": dbg.get("max_ev"), "max_ev_kumi": dbg.get("max_ev_kumi"),
                "bets": bets,
                "win": row.get("winno_3t"), "pnl": row.get("pnl_yen"),
                "settled": row.get("status") == "settled",
                "detail": {
                    "s": [round(x, 3) for x in dbg.get("s_values", [])],
                    "mu": [round(x, 1) for x in dbg.get("ts_mu", [])],
                    "sg": [round(x, 2) for x in dbg.get("ts_sigma", [])],
                    "wr": [round(x, 3) for x in dbg.get("weather_wr", [])],
                    "t5": t5,
                    "med": dbg.get("ev_median_120"), "p90": dbg.get("ev_p90_120"),
                    "nb": dbg.get("n_odds_in_band"),
                    "mev": dbg.get("max_ev"), "mevk": dbg.get("max_ev_kumi"),
                    "mevo": dbg.get("max_ev_odds"), "x": extra},
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
        if not wk.isdigit():
            # レース中止/不成立: 全買い目が元返し(収支0)
            r["win"] = win
            r["pnl"] = 0
            r["prov"] = True
            r["cancel"] = True
            r["ret"] = sum(b["stake"] for b in r["bets"])
            continue
        # フライング等の返還艇: その艇を含む買い目は掛金払い戻し(収支0)
        ret = {str(x) for x in (rr["maindata"].get("returnlist") or [])}
        stake = payout = refunded = 0
        for b in r["bets"]:
            if ret and any(c in ret for c in b["k"]):
                refunded += b["stake"]
                continue
            stake += b["stake"]
            if b["k"] == wk:
                payout += b["stake"] // 100 * div
        r["win"] = win
        r["pnl"] = payout - stake
        r["prov"] = True
        if refunded:
            r["ret"] = refunded
        total["stake"] += stake
        total["payout"] += payout
        total["pnl"] += payout - stake
        if payout:
            total["hits"] += 1

    races.sort(key=lambda r: (r["deadline"] or "99:99", r["id"], r["eng"]))

    # システムランプ: bet-server状態 / 朝バッチ / 推論の鮮度
    sysd = {}
    latest = None
    for eng in engines:
        for f in (day / "micro_live" / f"{eng}_submissions").glob("*_live.json"):
            m = f.stat().st_mtime
            if latest is None or m > latest[0]:
                latest = (m, f)
    if latest:
        try:
            bs = json.load(open(latest[1])).get("bet_server_status") or {}
            sysd["bet"] = {"ok": bool(bs.get("logged_in")), "bal": bs.get("balance")}
        except json.JSONDecodeError:
            pass
    ms = day / "morning_status.json"
    if ms.exists():
        sysd["morning"] = {"ok": True, "t": datetime.datetime.fromtimestamp(
            ms.stat().st_mtime).strftime("%H:%M")}
    newest = 0.0
    for eng in engines:
        for f in (day / bets_dir(eng)).glob("*.json"):
            newest = max(newest, f.stat().st_mtime)
    if newest:
        sysd["infer_age_min"] = round((time.time() - newest) / 60, 1)

    schedule = [{"id": rid, "v": r.get("venue_name"), "jcd": r["jcd"],
                 "rno": r["rno"], "dl": r.get("deadline")}
                for rid, r in sorted(sched.items(),
                                     key=lambda kv: kv[1].get("deadline") or "99")]
    # 次レース表示用: 出走表(枠/選手/級/勝率/ST)+単勝オッズ
    for s in schedule:
        jcd, rno = s["jcd"], int(s["rno"])
        cf = day / "cards" / f"venue_{jcd}_race_{rno:02d}_racecard.json"
        if cf.exists():
            try:
                tl = json.load(open(cf))["maindata"]["teiinfolist"]
                s["card"] = [{"n": int(t["teino"]),
                              "name": t["racername"].replace("\u3000", " ").strip(),
                              "cls": t["classname"], "win": fnum(t.get("zwinper")),
                              "st": fnum(t.get("avest"))} for t in tl]
            except (KeyError, ValueError, json.JSONDecodeError):
                pass
        tf = day / "oddstf" / f"venue_{jcd}_race_{rno:02d}_oddstf.json"
        if tf.exists():
            try:
                om = json.load(open(tf))["maindata"]
                tans = {e["kumi"]: fnum(e.get("odds")) for e in om.get("oddstlist", [])}
                s["tan"] = [tans.get(str(i)) for i in range(1, 7)]
                s["tan_t"] = om.get("updatetime")
            except (KeyError, json.JSONDecodeError):
                pass

    out = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": hd,
        "n_scheduled": len(sched),
        "schedule": schedule,
        "n_processed": len({r["id"] for r in races}),
        "n_bet_races": len({r["id"] for r in races if r["bets"]}),
        "total": total,
        "sys": sysd,
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
