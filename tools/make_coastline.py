#!/usr/bin/env python3
"""Natural Earth 50m から日本の海岸線を抽出し、index.html 埋め込み用の
ISLANDS 配列 (islands.js) を生成する。

usage:
  curl -sL -o ne50.json "https://raw.githubusercontent.com/martynafford/natural-earth-geojson/master/50m/cultural/ne_50m_admin_0_countries.json"
  python3 make_coastline.py ne50.json
"""
import json
import math
import sys

MIN_AREA = 0.015   # deg^2: これ未満の小島は捨てる
MIN_LAT = 31.0     # 構図のため南西諸島(沖縄・屋久島等)は外す
TOL = 0.018        # Douglas-Peucker 許容誤差 (deg)


def area(ring):
    s = 0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(s) / 2


def dp(pts, tol):
    """Douglas-Peucker。閉リング(始点=終点)は基準線が退化するので点距離にフォールバック。"""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        dmax, imax = -1, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L < 1e-9:
                dist = math.hypot(px - ax, py - ay)
            else:
                dist = abs(dy * (px - ax) - dx * (py - ay)) / L
            if dist > dmax:
                dmax, imax = dist, i
        if dmax > tol:
            keep[imax] = True
            stack.append((a, imax))
            stack.append((imax, b))
    return [p for p, k in zip(pts, keep) if k]


def main(path):
    d = json.load(open(path))
    feats = d["features"] if "features" in d else [d]
    jp = next(f for f in feats
              if f.get("properties", {}).get("ADMIN") == "Japan"
              or f.get("properties", {}).get("admin") == "Japan")
    polys = jp["geometry"]["coordinates"]

    kept = []
    for poly in polys:
        ring = poly[0]
        a = area(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        if a < MIN_AREA or cy < MIN_LAT:
            continue
        kept.append((a, dp(ring, TOL)))

    kept.sort(key=lambda x: -x[0])  # 面積降順: [0]=本州 [1]=北海道 [2]=九州 [3]=四国 ...
    total = 0
    lines = []
    for a, s in kept:
        pts = [[round(p[0], 2), round(p[1], 2)] for p in s]
        out = [pts[0]]
        for p in pts[1:]:
            if p != out[-1]:
                out.append(p)
        if out[0] == out[-1]:
            out = out[:-1]
        if len(out) < 4:
            continue
        total += len(out)
        print(f"  area={a:.3f} pts={len(out)}")
        lines.append("[" + ",".join(f"[{p[0]},{p[1]}]" for p in out) + "]")

    js = "var ISLANDS=[\n" + ",\n".join(lines) + "\n];"
    with open("islands.js", "w") as f:
        f.write(js)
    print(f"total {total} pts -> islands.js ({len(js)} chars)")
    print("index.html の ISLANDS 配列と手で差し替えること")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ne50.json")
