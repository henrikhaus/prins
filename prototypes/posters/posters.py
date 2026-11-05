"""Fourteen poster concepts on the real grid. Each function returns a 312x216 image."""
from __future__ import annotations

import math

import segno
from PIL import Image, ImageDraw

from kit import (H, W, atkinson, bayer, blank, blur, clip, finish, font, halftone, line, rng, stamp, stroke, tone, word,
                 xor_stamp)


def stack():
    """Every line set to the full measure. The fastest route to looking like a poster."""
    c = blank()
    d = ImageDraw.Draw(c)
    hazard = tone(lambda x, y: 1 if (x + y) % 28 < 14 else 0, W, 14)
    c.paste(hazard, (0, 0))
    a = word("DEPLOY", "impact", w=296, h=64)
    stamp(c, a, 8, 22)
    d.rectangle([0, 92, W, 170], fill=0)
    b = word("BLOCKED", "impact", w=296, h=66)
    stamp(c, b, 8, 98, 255)
    s = word("APPROVE THE MIGRATION", "din", w=296, h=25)
    stamp(c, s, 8, 180)
    d.rectangle([0, 210, W, H], fill=0)
    return c


def mirror():
    """A real ray trace: mirror ball, checker floor, soft shadow, all resolved through one dither."""
    SS = 2
    w, h = W * SS, H * SS
    cam = (0.0, 1.5, -4.8)
    ball = (1.15, 1.2, -1.0)
    r = 1.2
    light = (-0.55, 0.75, -0.4)
    ll = math.sqrt(sum(v * v for v in light))
    light = tuple(v / ll for v in light)

    def floor_col(px, pz):
        check = (math.floor(px * 0.95) + math.floor(pz * 0.95)) % 2
        base = 0.96 if check else 0.03
        dx, dz = px - ball[0] - 0.55, pz - ball[2] - 0.2
        dist = math.sqrt(dx * dx + dz * dz * 0.7)
        base *= 0.08 + 0.92 * min(1.0, max(0.0, (dist - 0.75) / 0.95))
        fog = min(1.0, max(0.0, (pz - 1) / 20))
        return base * (1 - fog) + 0.34 * fog

    def trace(o, dd, depth=0):
        oc = (o[0] - ball[0], o[1] - ball[1], o[2] - ball[2])
        b = sum(a * e for a, e in zip(oc, dd))
        q = sum(a * a for a in oc) - r * r
        disc = b * b - q
        if disc > 0 and depth < 2:
            t = -b - math.sqrt(disc)
            if t > 1e-3:
                p = tuple(o[i] + dd[i] * t for i in range(3))
                n = tuple((p[i] - ball[i]) / r for i in range(3))
                dn = sum(dd[i] * n[i] for i in range(3))
                refl = tuple(dd[i] - 2 * dn * n[i] for i in range(3))
                col = trace(p, refl, depth + 1)
                spec = max(0.0, sum(refl[i] * light[i] for i in range(3))) ** 60
                edge = min(1.0, max(0.0, (-dn - 0.08) / 0.2))
                return min(1.0, col * edge + spec * 1.6)
        if dd[1] < -1e-4:
            t = -o[1] / dd[1]
            return floor_col(o[0] + dd[0] * t, o[2] + dd[2] * t)
        if depth:  # What the ball sees is a bright studio, not the black sky behind it.
            return 0.25 + 0.75 * min(1.0, max(0.0, 1 - dd[1] * 1.15))
        return 0.0

    data = bytearray(w * h)
    for j in range(h):
        for i in range(w):
            x, y = (i + 0.5 - w / 2) / (h * 0.82), (h / 2 - j - 0.5) / (h * 0.82) - 0.16
            n = math.sqrt(x * x + y * y + 1)
            col = trace(cam, (x / n, y / n, 1 / n))
            data[j * w + i] = max(0, min(255, int(col * 255)))
    gray = Image.frombytes("L", (w, h), bytes(data)).resize((W, H), Image.BOX)
    c = atkinson(gray)
    a = word("DEMO", "futura", w=118)
    b = word("DAY", "futura", w=118)
    stamp(c, a, 12, 12, 255)
    stamp(c, b, 12, 12 + a.height + 5, 255)
    return c


def extrude():
    """Type with a vanishing point. Depth is free once the engine owns it."""
    vp = (156, 18)
    c = bayer(tone(lambda x, y: 0.7 if (math.atan2(y - vp[1], x - vp[0]) * 28 / math.pi) % 2 < 1 else 1.0))
    m = word("SHIP IT", "impact", w=292, h=96)
    face = Image.new("L", (W, H), 0)
    face.paste(m, (10, 112))
    for t in range(62, 0, -1):
        s = 1 - t * 0.0098
        size = (max(1, round(W * s)), max(1, round(H * s)))
        scaled = face.resize(size, Image.NEAREST)
        ox, oy = round(vp[0] - vp[0] * s), round(vp[1] - vp[1] * s)
        layer = Image.new("L", (W, H), 0)
        layer.paste(scaled, (ox, oy))
        c.paste(0 if t % 20 else 255, (0, 0), layer)
    from PIL import ImageFilter

    fat = face.filter(ImageFilter.MaxFilter(5))
    c.paste(0, (0, 0), fat)
    c.paste(255, (0, 0), face)
    return c


def relief():
    """A hidden word lifts out of ruled lines. Only the height map knows it is there."""
    src = blank(0)
    m = word("FOCUS", "impact", w=284, h=122)
    src.paste(m, (14, 30))
    soft = blur(src, 1.3)
    hp, mp = soft.load(), src.load()
    c = blank(0)
    d = ImageDraw.Draw(c)
    for y0 in range(4, H + 16, 4):
        sy = min(H - 1, y0)
        pts = [(x, y0 - hp[min(W - 1, max(0, x)), sy] / 255 * 11) for x in range(-1, W + 2)]
        d.polygon(pts + [(W + 2, H + 20), (-1, H + 20)], fill=0)
        for x in range(0, W):
            inside = hp[x, sy] > 120
            py = pts[x + 1][1]
            d.line([(x, py), (x + 1, pts[x + 2][1])], fill=255, width=3 if inside else 1)
    d.rectangle([0, 182, W, H], fill=255)
    cap = word("14:00 - 16:00  DO NOT DISTURB", "din", w=288, h=22)
    stamp(c, cap, 12, 188)
    return c


def bauhaus():
    """Two shapes and a numeral, collided with XOR. Overlap does the design."""
    c = blank()
    d = ImageDraw.Draw(c)
    d.ellipse([-58, -22, 202, 238], fill=0)
    d.rectangle([218, 104, 312, 216], fill=0)
    d.pieslice([218, 44, 312, 164], 180, 360, fill=0)
    n = word("14", "futura", h=122)
    xor_stamp(c, n, 14, 47)
    t = word("COFFEE", "futura", w=84)
    stamp(c, t, 222, 12)
    sub = word(":00", "futura", w=70)
    stamp(c, sub, 230, 118, 255)
    wi = word("WITH IDA", "din", w=70, h=22)
    stamp(c, wi, 230, 170, 255)
    return c


def giant():
    """One numeral, set absurdly large in a high-contrast face, printed in halftone."""
    c = blank()
    screen = halftone(lambda x, y: 0.42 + 0.72 * max(0.0, min(1.0, y / 210)), cell=5)
    m = word("3", "bodoni", h=236)
    clip(screen, m, c, 2, -10)
    a = word("days", "didot-it", w=128)
    stamp(c, a, 172, 22)
    rule_y = 22 + a.height + 10
    ImageDraw.Draw(c).rectangle([172, rule_y, 300, rule_y + 1], fill=0)
    b = word("to launch", "didot-it", w=128)
    stamp(c, b, 172, rule_y + 10)
    foot = line("MONDAY 9 NOV", "din", 16, 1)
    stamp(c, foot, 172, H - foot.height - 14)
    return c


def ridges():
    """The week's real numbers as a mountain range. A chart nobody has to read."""
    data = [12, 31, 18, 44, 27, 9, 6]
    c = blank()
    sky = bayer(tone(lambda x, y: 1 - max(0.0, 0.34 - y / 380)))
    c.paste(sky)
    d = ImageDraw.Draw(c)
    d.ellipse([222, 14, 280, 72], fill=255, outline=0, width=2)

    def spline(x):
        pos = x / W * (len(data) - 1)
        i = min(len(data) - 2, int(pos))
        t = pos - i
        t = t * t * (3 - 2 * t)
        return data[i] * (1 - t) + data[i + 1] * t

    r = rng(7)
    layers = 5
    for k in range(layers):
        phase = r.random() * 9
        base = 62 + k * 20
        amp = 1.25 - k * 0.09
        shade = 0.84 - k * 0.19

        def ridge(x):
            v = spline((x + k * 41) % W)
            return base - v * amp * 0.7 + math.sin(x / (21 - k) + phase) * 7 + math.sin(x / 6.3 + phase * 2) * 2.2

        tops = [ridge(x) for x in range(W)]
        lay = bayer(tone(lambda x, y: shade - (y - tops[x]) * 0.0022 if y >= tops[x] else 1))
        mask = tone(lambda x, y: 1 if y >= tops[x] else 0)
        c.paste(lay, (0, 0), mask)
        d.line([(x, tops[x]) for x in range(W)], fill=0, width=1)
    # The nearest ridge is the week itself, in solid black, so the numbers sit on clean ink.
    front = [150 - spline(x) * 0.42 + math.sin(x / 11) * 1.5 for x in range(W)]
    d.polygon([(x, front[x]) for x in range(W)] + [(W, H), (0, H)], fill=0)
    big = word("147", "impact", h=52)
    stamp(c, big, 12, 154, 255)
    x = 12 + big.width + 10
    t = word("COMMITS", "din", h=23)
    stamp(c, t, x, 154, 255)
    t2 = word("THIS WEEK", "din", h=23)
    stamp(c, t2, x, 183, 255)
    return c


def ticket():
    """A real object, not a layout: the meeting is a boarding pass, and the QR scans."""
    c = blank()
    d = ImageDraw.Draw(c)
    d.rounded_rectangle([3, 3, W - 4, H - 4], radius=10, outline=0, width=2)
    d.rounded_rectangle([3, 3, W - 4, 34], radius=10, fill=0)
    d.rectangle([3, 16, W - 4, 34], fill=0)
    stamp(c, word("BOARDING PASS", "din", h=17), 14, 11, 255)
    stamp(c, word("1:1", "din", h=17), W - 36, 11, 255)
    stub = 210
    for y in range(44, H - 12, 7):
        d.rectangle([stub, y, stub + 1, y + 3], fill=0)
    for cy in (35, H - 4):
        d.ellipse([stub - 6, cy - 6, stub + 7, cy + 6], fill=255, outline=0, width=2)

    def label(text, value, x, y, vh):
        stamp(c, line(text, "din", 13, 1), x, y)
        stamp(c, word(value, "din", h=vh), x, y + 14)

    label("FROM", "YOU", 14, 41, 36)
    d.rectangle([66, 71, 80, 74], fill=0)
    d.polygon([(78, 64), (90, 72), (78, 81)], fill=0)
    label("TO", "MARIA", 100, 41, 36)
    d.rectangle([14, 101, 200, 102], fill=0)
    label("BOARDS", "15:30", 14, 106, 30)
    label("GATE", "ROOM 4", 104, 106, 30)
    bars = rng("maria-1530")
    x = 14
    while x < 200:
        b = bars.choice((1, 1, 2, 3))
        d.rectangle([x, 164, min(x + b - 1, 200), 202], fill=0)
        x += b + bars.choice((1, 2, 2, 3))
    code = segno.make("https://meet.example/maria", error="m", boost_error=False)
    matrix = code.matrix
    size = len(matrix)
    scale = 88 // size
    ox, oy = 218 + (86 - size * scale) // 2, 46
    for j, row in enumerate(matrix):
        for i, cell in enumerate(row):
            if cell:
                d.rectangle([ox + i * scale, oy + j * scale, ox + (i + 1) * scale - 1, oy + (j + 1) * scale - 1], fill=0)
    stamp(c, line("SEAT", "din", 13, 1), 222, 148)
    stamp(c, word("1A", "din", h=34), 222, 164)
    return c


def moon():
    """Copperplate engraving: a lit sphere drawn only in swelling lines, like a banknote."""
    cx, cy, r = 212, 104, 96
    gen = rng(11)
    craters = [(gen.uniform(-0.9, 0.9), gen.uniform(-0.9, 0.9), gen.uniform(0.05, 0.2)) for _ in range(26)]
    craters = [c for c in craters if c[0] ** 2 + c[1] ** 2 < 0.9]
    lx, ly, lz = -0.62, -0.46, 0.63
    tilt = math.radians(-24)
    ct, st = math.cos(tilt), math.sin(tilt)
    out = bytearray(W * H)
    stars = rng(3)
    star_set = {(stars.randrange(W), stars.randrange(H)) for _ in range(110)}
    for y in range(H):
        for x in range(W):
            u, v = (x - cx) / r, (y - cy) / r
            d2 = u * u + v * v
            if d2 >= 1:
                out[y * W + x] = 255 if (x, y) in star_set else 0
                continue
            z = math.sqrt(1 - d2)
            nx, ny, nz = u, v, z
            albedo = 1.0
            for cu, cv, cr in craters:
                du, dv = u - cu, v - cv
                dist = math.sqrt(du * du + dv * dv)
                if dist < cr * 1.25:
                    t = dist / cr
                    slope = 0.75 * (1 - t) if t < 1 else -1.6 * (t - 1)
                    if dist > 1e-4:
                        nx += du / dist * slope * -1 * 0.8
                        ny += dv / dist * slope * -1 * 0.8
                    if t < 0.9:
                        albedo *= 0.82
            mare = math.sin(u * 3.1 + v * 1.7 + 1.0) + math.sin(v * 4.3 - u * 1.1) * 0.7
            if mare > 0.75:
                albedo *= 0.72
            n = math.sqrt(nx * nx + ny * ny + nz * nz)
            lambert = max(0.0, (nx * lx + ny * ly + nz * lz) / n)
            bright = min(1.0, 0.1 + (lambert ** 0.82) * albedo * 1.15)
            ru, rv = u * ct - v * st, u * st + v * ct
            lat = math.asin(max(-1, min(1, rv))) / (math.pi / 2)
            lon = ru / max(0.05, math.sqrt(1 - rv * rv))
            phase = (lat * 25 + 0.12 * math.sin(lon * 7)) % 1
            w = 0.5 * (1 - bright) ** 0.8 * 1.02
            out[y * W + x] = 0 if abs(phase - 0.5) < w else 255
    c = Image.frombytes("L", (W, H), bytes(out))
    ImageDraw.Draw(c).rectangle([0, 0, 0, 0], fill=0)
    a = word("Good", "didot-it", w=98)
    b = word("night", "didot-it", w=98)
    # Clear a little night around the words, so the stars never touch the letters.
    d = ImageDraw.Draw(c)
    d.rectangle([6, 8, 120, 8 + a.height + b.height + 62], fill=0)
    stamp(c, a, 12, 16, 255)
    stamp(c, b, 12, 16 + a.height + 8, 255)
    cap = line("LAPTOP OFF 23:00", "din", 16, 1)
    d.rectangle([0, H - 26, cap.width + 22, H], fill=0)
    stamp(c, cap, 12, H - cap.height - 10, 255)
    return c


def truchet(seed="thursday-5-nov"):
    """Generative cover: the seed comes from the date, so no two mornings match. Costs no tokens."""
    r = rng(seed)
    SS = 3
    c = Image.new("L", (W * SS, H * SS), 255)
    d = ImageDraw.Draw(c)
    cell = 26 * SS
    band = int(cell * 0.34)
    for gy in range(0, H * SS, cell):
        for gx in range(0, W * SS + cell, cell):
            mode = r.random()
            bx = [gx, gy, gx + cell, gy + cell]
            half = cell // 2
            if mode < 0.46:
                d.arc([gx - half, gy - half, gx + half, gy + half], 0, 90, fill=0, width=band)
                d.arc([gx + half, gy + half, gx + cell + half, gy + cell + half], 180, 270, fill=0, width=band)
            elif mode < 0.92:
                d.arc([gx + half, gy - half, gx + cell + half, gy + half], 90, 180, fill=0, width=band)
                d.arc([gx - half, gy + half, gx + half, gy + cell + half], 270, 360, fill=0, width=band)
            else:
                d.line([(gx + half, gy), (gx + half, gy + cell)], fill=0, width=band)
                d.line([(gx, gy + half), (gx + cell, gy + half)], fill=0, width=band)
    c = c.resize((W, H), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    d = ImageDraw.Draw(c)
    d.rectangle([44, 58, 268, 158], fill=255)
    d.rectangle([48, 62, 264, 154], fill=0)
    a = word("THURSDAY", "futura", w=196)
    stamp(c, a, 58, 72, 255)
    b = word("3 THINGS  -  5 NOV", "din", w=196, h=30)
    stamp(c, b, 58, 72 + a.height + 12, 255)
    return c


def ransom():
    """Every letter cut from a different page. Personality for free, from a single seed."""
    c = bayer(tone(lambda x, y: 0.93))
    r = rng(23)
    fonts = ["impact", "didot", "rockwell", "courier", "futura", "phosphate-s", "typewriter", "black", "bodoni", "krung", "georgia"]
    rows = [("CALL", 14, 62), ("SAM", 76, 72), ("BACK", 146, 58)]
    r.shuffle(fonts)
    idx = 0
    for text, top, h in rows:
        widths = [int(h * r.uniform(0.82, 1.06)) for _ in text]
        gaps = [r.randint(3, 8) for _ in text]
        x = (W - sum(widths) - sum(gaps[:-1])) // 2
        for ch, w, gap in zip(text, widths, gaps):
            f = fonts[idx % len(fonts)]
            idx += 1
            style = r.choice(("black", "white", "white", "black", "gray"))
            if ch == "A" and text == "SAM":
                style = "black"
            tile = Image.new("L", (w, h), 0 if style == "black" else 255)
            if style == "gray":
                tile = bayer(tone(lambda x, y: 0.62, w, h))
            td = ImageDraw.Draw(tile)
            td.rectangle([0, 0, w - 1, h - 1], outline=0, width=1)
            glyph = word(ch, f, h=int(h * r.uniform(0.62, 0.78)))
            if glyph.width > w - 8:
                glyph = word(ch, f, w=w - 8)
            ink = 255 if style == "black" else 0
            if style == "gray":
                td.rectangle([4, 4, w - 5, h - 5], fill=255)
            tile.paste(ink, ((w - glyph.width) // 2, (h - glyph.height) // 2), glyph)
            rot = r.uniform(-7, 7)
            big = Image.new("L", (w + 26, h + 26), 255)
            alpha = Image.new("L", big.size, 0)
            big.paste(tile, (13, 13))
            alpha.paste(255, (13, 13, 13 + w, 13 + h))
            rb = big.rotate(rot, Image.NEAREST)
            ra = alpha.rotate(rot, Image.NEAREST)
            yo = top + r.randint(-3, 3) - 13
            c.paste(0, (x + 3 - 13, yo + 3), ra)
            c.paste(rb, (x - 13, yo), ra)
            x += w + gap
    return c


def merged():
    """The concept is the picture: two branches literally become one. Commits are stations."""
    SS = 4
    big_canvas = Image.new("L", (W * SS, H * SS), 255)
    d = ImageDraw.Draw(big_canvas)

    def scaled(pts):
        return [(x * SS, y * SS) for x, y in pts]

    def s_curve(x0, y0, x1, y1, n=120):
        pts = []
        for i in range(n + 1):
            t = i / n
            e = t * t * (3 - 2 * t)
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * e))
        return pts

    my = 58
    top = [(-10, 18), (66, 18)] + s_curve(66, 18, 182, my)
    bot = [(-10, 98), (66, 98)] + s_curve(66, 98, 182, my)
    stroke(d, scaled(top), 9 * SS, 0)
    stroke(d, scaled(bot), 9 * SS, 0)
    stroke(d, scaled([(178, my), (262, my)]), 17 * SS, 0)

    def dot(x, y, r, fill):
        d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=fill)

    for x, y in ((14, 18), (40, 18), (10, 98), (30, 98), (50, 98)):
        dot(x, y, 8, 0)
        dot(x, y, 5, 255)
    dot(276, my, 28, 0)
    dot(276, my, 18, 255)
    dot(276, my, 9, 0)
    c = big_canvas.resize((W, H), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    stamp(c, line("main", "menlo", 13), 72, 28)
    stamp(c, line("fix/auth-timeout", "menlo", 13), 60, 108)
    big = word("MERGED", "futura", w=292)
    stamp(c, big, 10, 127)
    y = 127 + big.height + 8
    n = word("#418", "din", h=24)
    stamp(c, n, 10, y)
    st = word("+1,204  -388", "din", h=24)
    stamp(c, st, 302 - st.width, y)
    return c


def rain():
    """A forecast with no axes to read. The dry hours are empty, so that's where the words go."""
    hours = [0, 0, 0, 0, 0.18, 0.6, 1.0, 0.8, 0.42]
    c = blank(0)
    d = ImageDraw.Draw(c)
    r = rng(5)

    def level(x):
        pos = x / W * (len(hours) - 1)
        i = min(len(hours) - 2, int(pos))
        return hours[i] + (hours[i + 1] - hours[i]) * (pos - i)

    for _ in range(3000):
        x = r.uniform(0, W + 20)
        y = r.uniform(-12, 184)
        if r.random() < level(x) ** 1.2:
            length = 6 + 14 * level(x)
            d.line([(x, y), (x - length * 0.34, y + length)], fill=255, width=1)
    d.rectangle([0, 184, W, H], fill=0)
    d.line([(0, 184), (W, 184)], fill=255, width=2)
    for i, x in enumerate(range(0, 9)):
        hx = 8 + x * (W - 16) / 8
        d.line([(hx, 184), (hx, 188)], fill=255)
        if i % 2 == 0:
            lab = line(f"{12 + i}", "din", 15)
            stamp(c, lab, min(W - lab.width - 4, max(4, hx - lab.width / 2)), 192, 255)
    a = word("RAIN", "impact", w=132)
    b = word("AT 16", "impact", w=132)
    stamp(c, a, 12, 12, 255)
    stamp(c, b, 12, 18 + a.height, 255)
    t = line("TAKE A JACKET", "din", 16, 1)
    stamp(c, t, 12, 26 + a.height + b.height, 255)
    return c


def airmail():
    """A friend's note arrives as post. The sender is filled in by the connector, never the model."""
    c = blank()
    d = ImageDraw.Draw(c)
    # Airmail edge.
    for i in range(-20, W + 20, 12):
        k = (i // 12) % 2
        d.polygon([(i, 0), (i + 6, 0), (i, 8), (i - 6, 8)], fill=0 if k else 255)
        d.polygon([(i, H - 8), (i + 6, H - 8), (i, H), (i - 6, H)], fill=0 if k else 255)
    # Stamp.
    sx, sy, sw, sh = 214, 16, 86, 104
    d.rectangle([sx, sy, sx + sw, sy + sh], fill=0)
    for x in range(sx, sx + sw + 1, 8):
        for y in (sy, sy + sh):
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=255)
    for y in range(sy, sy + sh + 1, 8):
        for x in (sx, sx + sw):
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=255)
    d.rectangle([sx + 7, sy + 7, sx + sw - 7, sy + sh - 7], fill=255)
    # A candle, engraved.
    ix, iy, iw, ih = sx + 9, sy + 9, sw - 18, sh - 18
    screen = halftone(lambda x, y: 1 - min(1, math.hypot((x - ix - iw / 2) / 34, (y - iy - 24) / 38)), cell=4.2)
    d.rectangle([ix, iy, ix + iw, iy + ih], fill=0)
    region = screen.crop((ix, iy, ix + iw, iy + ih)).point(lambda v: 255 - v)
    c.paste(region, (ix, iy))
    cx = ix + iw // 2
    d.rectangle([cx - 8, iy + 38, cx + 8, iy + ih], fill=255, outline=0)
    for y in range(iy + 40, iy + ih, 6):
        d.line([(cx - 8, y + 4), (cx + 8, y)], fill=0)
    d.line([(cx, iy + 30), (cx, iy + 38)], fill=0, width=2)
    d.polygon([(cx, iy + 8), (cx + 7, iy + 22), (cx + 3, iy + 31), (cx - 3, iy + 31), (cx - 7, iy + 22)], fill=255, outline=0)
    # The words.
    a = word("Happy", "didot-it", w=120, thresh=62)
    b = word("birthday", "didot-it", w=176, thresh=62)
    e = word("Sam", "didot-it", w=78, thresh=62)
    stamp(c, a, 14, 18)
    stamp(c, b, 14, 18 + a.height + 8)
    stamp(c, e, 14, 18 + a.height + b.height + 18)
    # The postmark, overlapping the stamp as a real one does.
    rx, ry = 214, 150
    pm = Image.new("L", (W, H), 0)
    pd = ImageDraw.Draw(pm)
    pd.ellipse([rx - 34, ry - 34, rx + 34, ry + 34], outline=255, width=3)
    pd.ellipse([rx - 25, ry - 25, rx + 25, ry + 25], outline=255, width=1)
    for k in range(5):
        pts = [(x, ry - 22 + k * 11 + math.sin(x / 9) * 3) for x in range(rx + 36, W + 2, 2)]
        pd.line(pts, fill=255, width=2)
    from PIL import ImageChops

    c.paste(ImageChops.invert(c), (0, 0), pm)
    d = ImageDraw.Draw(c)
    d.ellipse([rx - 24, ry - 24, rx + 24, ry + 24], fill=255)
    stamp(c, word("PRINS", "din", w=34), rx - 17, ry - 15)
    stamp(c, word("5 NOV", "din", w=34), rx - 17, ry + 3)
    stamp(c, line("FROM", "din", 14, 1), 14, 166)
    stamp(c, word("HENRIK", "din", h=26), 52, 164)
    return c


POSTERS = [stack, relief, mirror, ticket, moon, merged, giant, rain, ransom, ridges, bauhaus, airmail, extrude, truchet]
