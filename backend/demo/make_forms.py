"""
Demo uchun NAMUNA laboratoriya blankalarini yaratadi (sintetik, real hujjat emas).
Ishga tushirish:  python demo/make_forms.py
"""
from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def f(size, bold=False, mono=False):
    try:
        return ImageFont.truetype(FONT_MONO if mono else (FONT_B if bold else FONT), size)
    except OSError:
        return ImageFont.load_default()


FORMS = [
    {   # QIZIL: preeklampsiya xavfi
        "file": "tahlil_bahromova_naima.jpg", "lang": "uz", "photo": True,
        "name": "Bahromova Naima", "age": 26, "ga": 33,
        "hb": "112", "rbc": "3,9", "wbc": "8,1", "plt": "214", "glu": "4,8",
        "prot": "0,6", "color": "sariq", "sg": "1020", "bp": "152/98",
    },
    {   # YASHIL: hammasi normal
        "file": "tahlil_akbarxodjayeva_aziza.jpg", "lang": "uz", "photo": False,
        "name": "Akbarxodjayeva Aziza", "age": 29, "ga": 28,
        "hb": "124", "rbc": "4,2", "wbc": "7,4", "plt": "236", "glu": "4,5",
        "prot": "0", "color": "och sariq", "sg": "1018", "bp": "112/70",
    },
    {   # SARIQ: anemiya (blanka rus tilida — AI ikki tilni o'qiydi)
        "file": "analiz_gulyamova_farzona.jpg", "lang": "ru", "photo": True,
        "name": "Гулямова Фарзона", "age": 31, "ga": 30,
        "hb": "98", "rbc": "3,5", "wbc": "6,9", "plt": "198", "glu": "4,6",
        "prot": "отр.", "color": "соломенно-жёлтый", "sg": "1015", "bp": "114/72",
    },
]

T = {
    "uz": dict(org="TOSHKENT SHAHAR SOG'LIQNI SAQLASH BOSH BOSHQARMASI",
               clinic="42-OILAVIY POLIKLINIKA · KLINIK-DIAGNOSTIK LABORATORIYA",
               title="TAHLIL NATIJALARI", fio="F.I.Sh.:", age="Yoshi:", date="Sana:",
               ga="Homiladorlik muddati:", weeks="hafta",
               blood="UMUMIY QON TAHLILI", bio="BIOKIMYOVIY TAHLIL", urine="SIYDIK UMUMIY TAHLILI",
               col=("Ko'rsatkich", "Natija", "Birlik", "Me'yor"),
               hb="Gemoglobin (HGB)", rbc="Eritrotsitlar (RBC)", wbc="Leykotsitlar (WBC)",
               plt="Trombotsitlar (PLT)", glu="Glyukoza (och qoringa)", colr="Rangi",
               sg="Solishtirma og'irlik", prot="Oqsil",
               nurse="Patronaj hamshirasi o'lchovi:", bp="Arterial bosim",
               sign="Laborant: ________   Imzo: ________"),
    "ru": dict(org="ГЛАВНОЕ УПРАВЛЕНИЕ ЗДРАВООХРАНЕНИЯ г. ТАШКЕНТА",
               clinic="СЕМЕЙНАЯ ПОЛИКЛИНИКА №17 · КЛИНИКО-ДИАГНОСТИЧЕСКАЯ ЛАБОРАТОРИЯ",
               title="РЕЗУЛЬТАТЫ АНАЛИЗОВ", fio="Ф.И.О.:", age="Возраст:", date="Дата:",
               ga="Срок беременности:", weeks="нед.",
               blood="ОБЩИЙ АНАЛИЗ КРОВИ", bio="БИОХИМИЧЕСКИЙ АНАЛИЗ", urine="ОБЩИЙ АНАЛИЗ МОЧИ",
               col=("Показатель", "Результат", "Ед.", "Норма"),
               hb="Гемоглобин (HGB)", rbc="Эритроциты (RBC)", wbc="Лейкоциты (WBC)",
               plt="Тромбоциты (PLT)", glu="Глюкоза (натощак)", colr="Цвет",
               sg="Удельный вес", prot="Белок",
               nurse="Измерение патронажной медсестры:", bp="Артериальное давление",
               sign="Лаборант: ________   Подпись: ________"),
}


def render(d: dict) -> Image.Image:
    t = T[d["lang"]]
    W, H = 1240, 1754
    img = Image.new("RGB", (W, H), "white")
    g = ImageDraw.Draw(img)
    ink, grey, line = (25, 25, 40), (110, 110, 120), (170, 170, 180)

    g.text((W // 2, 70), t["org"], font=f(24, True), fill=ink, anchor="mm")
    g.text((W // 2, 108), t["clinic"], font=f(22), fill=ink, anchor="mm")
    g.line((80, 140, W - 80, 140), fill=ink, width=3)
    g.text((W // 2, 195), t["title"], font=f(40, True), fill=ink, anchor="mm")

    y = 260
    g.text((90, y), f"{t['fio']}  {d['name']}", font=f(28), fill=ink)
    g.text((820, y), f"{t['age']} {d['age']}", font=f(28), fill=ink)
    y += 50
    g.text((90, y), f"{t['date']}  {date.today().strftime('%d.%m.%Y')}", font=f(28), fill=ink)
    g.text((620, y), f"{t['ga']} {d['ga']} {t['weeks']}", font=f(28), fill=ink)

    def table(y, title, rows):
        g.text((90, y), title, font=f(28, True), fill=ink)
        y += 48
        xs = (90, 560, 780, 960)
        g.rectangle((80, y - 6, W - 80, y + 38), fill=(238, 238, 244))
        for x, c in zip(xs, t["col"]):
            g.text((x, y), c, font=f(24, True), fill=ink)
        y += 46
        for r in rows:
            for i, (x, c) in enumerate(zip(xs, r)):
                g.text((x, y), c, font=f(30, True, mono=True) if i == 1 else f(26), fill=ink)
            y += 46
            g.line((80, y - 6, W - 80, y - 6), fill=line, width=1)
        return y + 30

    y = 400
    y = table(y, t["blood"], [
        (t["hb"], d["hb"], "g/l" if d["lang"] == "uz" else "г/л", "110–150"),
        (t["rbc"], d["rbc"], "×10¹²/l", "3,5–5,0"),
        (t["wbc"], d["wbc"], "×10⁹/l", "4,0–9,0"),
        (t["plt"], d["plt"], "×10⁹/l", "150–400"),
    ])
    y = table(y, t["bio"], [(t["glu"], d["glu"], "mmol/l" if d["lang"] == "uz" else "ммоль/л", "3,3–5,0")])
    y = table(y, t["urine"], [
        (t["colr"], d["color"], "", ""),
        (t["sg"], d["sg"], "", "1010–1025"),
        (t["prot"], d["prot"], "g/l" if d["lang"] == "uz" else "г/л", "< 0,1"),
    ])

    # Hamshira qo'lda yozgan bosim (qo'lyozmaga o'xshash, ko'k siyoh)
    g.text((90, y + 10), t["nurse"], font=f(26, True), fill=ink)
    g.text((90, y + 60), f"{t['bp']}:", font=f(26), fill=ink)
    hand = Image.new("RGBA", (420, 90), (0, 0, 0, 0))
    ImageDraw.Draw(hand).text((10, 10), d["bp"], font=f(58, True), fill=(20, 50, 160, 255))
    hand = hand.rotate(4, expand=True, resample=Image.BICUBIC)
    img.paste(hand, (470, y + 25), hand)
    g.text((800, y + 60), "mm sim. ust." if d["lang"] == "uz" else "мм рт. ст.", font=f(24), fill=grey)

    g.text((90, H - 150), t["sign"], font=f(24), fill=grey)

    # NAMUNA belgisi — bu real hujjat emas
    wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(wm).text((W // 2, H // 2), "NAMUNA · DEMO", font=f(150, True),
                            fill=(240, 54, 138, 38), anchor="mm")
    wm = wm.rotate(30, resample=Image.BICUBIC)
    img = Image.alpha_composite(img.convert("RGBA"), wm).convert("RGB")
    ImageDraw.Draw(img).text((W // 2, H - 70), "Namuna blanka — Uzilmas hakaton demosi uchun, real hujjat emas",
                             font=f(22), fill=(240, 54, 138), anchor="mm")
    return img


def photo_effect(img: Image.Image, seed: int) -> Image.Image:
    """Telefon bilan olingan suratga o'xshatish: qiyshayish, soya, iliq yorug'lik, shovqin."""
    rnd = random.Random(seed)
    img = img.rotate(rnd.uniform(-3, 3), expand=True, fillcolor=(70, 62, 55), resample=Image.BICUBIC)
    w, h = img.size
    grad = Image.new("L", (256, 1))
    grad.putdata([int(70 * (i / 255) ** 2) for i in range(256)])
    shade = grad.resize((w, h), Image.BILINEAR)
    dark = Image.new("RGB", (w, h), (40, 30, 20))
    img = Image.composite(dark, img, shade)
    warm = Image.new("RGB", (w, h), (255, 236, 205))
    img = Image.blend(img, warm, 0.12)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    canvas = Image.new("RGB", (w + 120, h + 120), (92, 74, 60))
    canvas.paste(img, (60, 60))
    return canvas.resize((int((w + 120) * 0.62), int((h + 120) * 0.62)), Image.LANCZOS)


if __name__ == "__main__":
    for i, d in enumerate(FORMS):
        im = render(d)
        if d["photo"]:
            im = photo_effect(im, i)
        im.save(OUT / d["file"], quality=88)
        print("OK", d["file"], im.size)
