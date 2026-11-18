# Uzilmas — demo va pitch (jamoa uçun)

## ✅ Sahnaga çiqişdan 15 daqiqa oldin
- [ ] `./reset_demo.sh` (yoki `python -m app.seed`) — baza toza holatda, Naima 🟢 yaşil
- [ ] `.env` da `ESCALATE_MINUTES=1`, `ACTIVE_CALL_MINUTES=3` (sahnada taymer tez körinsin)
- [ ] Server işlayapti, noutbuk zaryadda, ekran öçmaydi (energiya rejimi)
- [ ] Musobekning telefonida Telegram oçiq, ovozi yoqiq; botga test xabar keldi
- [ ] Telefonda `/nurse` oçiq (noutbuk bilan bitta Wi-Fi / hotspot)
- [ ] `demo/tahlil_bahromova_naima.jpg` boşqa telefonda ekranda oçiq (suratga oliş uçun) yoki çop etilgan
- [ ] Zaxira video (butun demo yozib olingan) noutbukda tayyor
- [ ] Brauzer: 1-tab `/dashboard` (Mutaxassis paneli), 2-tab `/doctor`, 3-tab `/` — töliq ekran (F11)

## 🎬 Demo ssenariysi (90 soniya)
| # | Kim | Nima qiladi | Ekranda |
|---|---|---|---|
| 1 | Farzona (hamşira roli) | Telefonda `/nurse` → **Bahromova Naima** → 📷 → blankani suratga oladi | "AI tahlilni öqiyapti…" → raqamlar töldi → **Yaşil → Qizil — darhol** + izoh |
| 2 | Farzona | **Tasdiqlaş va saqlaş** | Proyektorda `/dashboard`: qizil çaqnaş, ovoz, xarita Naimaga uçadi |
| 2b | Aziza | Panelda Naimaning **Jonli zanjiri**: "Mutaxassis" böğini sariq, taymer ketyapti. 1 daqiqa heç kim bosmaydi | Böğin **qizarib "UZILDI"** böladi, ovoz, "Zanjir uzildi" xabari, Telegramda boş şifokorga eskalatsiya |
| 3 | Musobek | Telefonini kötaradi: Telegram "🔴 QIZIL ZONA…" | Hakamlarga körsatadi, **✅ Qabul qildim** bosadi → panelda **"Zanjir tiklandi"**, böğin kök |
| 4 | Aziza | Mutaxassis panelida "Nega bu zona?" — qoida ID va manbani körsatadi | "R-PE · klinik protokol" |
| 5 | Aziza | **Kasalxonadan javob berildi** | `/doctor` sahifasida taymer boşlandi, Telegramga xabar |
| 6 | Naima (ixtiyoriy) | Telefonda Wi-Fi öçiradi → Aziza uçun ovoz/qölda kiritadi → "Navbatga saqlandi" → Wi-Fi yoqadi → avtomatik yuborildi | Offline işlaşi |

> Agar AI rasmni öqimasa: "Qölda" rejimga öting, 152 / 98 / 112 / 0,6 kiriting — natija bir xil. Bu ham kuçli: "AI bölmasa ham tizim işlaydi".

## 🎤 Pitch matni (3 daqiqa, özbekça)

**[0:00 — Muammo, 30 s]**
"Tasavvur qiling: Çilonzordagi hamşira homilador ayolning tahlilini oldi. Bosim 152 ga 98, siydikda oqsil bor — bu preeklampsiya belgisi. Ammo tahlil qoğozda, sumkada qoladi. Mutaxassis bu haqda bir haftadan keyin biladi. Ba'zan — keç.
Soğliqni saqlaş vazirligining özi buni uçta muammo sifatida qöygan: №9 — homiladorlar real vaqtda kuzatilmaydi, №10 — qişloqda ma'lumot raqamli tizimga kirmaydi, №11 — javob berilgandan keyin oilaviy şifokor xabar topmaydi."

**[0:30 — Yeçim, 20 s]**
"Bugun ona uç joyda yöqoladi: uyda, röyxatda va kasalxonadan çiqqanda. Biz bu zanjirni uzilmas qildik. Biz — Uzilmas. Bitta platforma onani birinçi patronaj taşrifidan tuğruqdan keyin uyga qaytguniça kuzatadi va uçala muammoni bitta zanjirda yopadi. Asosiy imkoniyatimiz — Jonli zanjir: har bir bemor uçun 5 böğin, va qaysi böğin uzilsa — kim, qaçon, nima qilmagani darhol körinadi. Hozir Toşkentdagi 103 bemordan 10 tasining zanjiri uzilgan — biz ularni köryapmiz, bugungi tizim esa körmaydi."

**[0:50 — Jonli demo, 90 s]** — yuqoridagi ssenariy.

**[2:20 — Nega bizga işoniş mumkin, 20 s]**
"Bizda zonani AI emas, oçiq qoidalar belgilaydi — JSST va klinik protokollar asosida, har birining manbasi bor. AI faqat öqiydi va tuşuntiradi. AI xavotirni kötara oladi, lekin bekor qila olmaydi. Işonçi past bölsa — 'tekşiring' deydi, heç qaçon 'norma' demaydi."

**[2:40 — Bozor va keyingi qadam, 20 s]**
"Model — B2G: Soğliqni saqlaş vazirligi va tuman tibbiyot birlaşmalari, tuman böyiça obuna. Hindistonda bunday qismlar alohida tizimlar sifatida mavjud; Özbekistonda bunday işlaydigan tizim yöq. Keyingi qadam — bitta tumanda pilot va DMED bilan integratsiya. Uzilmas — bemor zanjiri uzilmaydi."

## ❓ Hakamlar savollari — tayyor javoblar
| Savol | Javob |
|---|---|
| Çegaralar qayerdan? | JSST va homiladorlikdagi gipertenziya klinik protokollari; har bir qoidaning ID va manbasi bor (`/api/rules`). Amaliyotdan oldin akuşer-ginekolog tasdiqlaydi. |
| AI xato qilsa-çi? | AI qaror qabul qilmaydi. Raqamni öqiydi, işonçi past bölsa "tekşiring" deydi. Hamşira har doim tasdiqlaydi. Zonani qoidalar belgilaydi. |
| DMED'dan farqi? | Raqobatçi emas, qöşimça. DMED — tibbiy karta. Biz — xavfni özi köradigan va mas'ul şifokorga yetkazadigan uzluksiz zanjir. Qoğoz tahlil va internetsiz joylarda işlaymiz. Keyingi bosqiç — DMED API. |
| Şaxsiy ma'lumotlar? | Demoda hammasi sintetik. Pilotda — Özbekistondagi server, rollar böyiça kiriş, "Şaxsga doir ma'lumotlar töğrisida"gi qonun talablari. |
| Kim pul tölaydi? | Soğliqni saqlaş vazirligi / tuman tibbiyot birlaşmasi — tuman böyiça obuna. Kamroq asorat = kamroq qimmat reanimatsiya. |
| Internet bölmasa? | Hamşira ilovasi offline işlaydi, navbatga yozadi, internet çiqqanda özi yuboradi. Oğir belgilar bölsa offline ham "103 ga qönğiroq qiling" deydi. |
| Aniqlik qanday? | Qoidalar deterministik — 27 ta avtomatik test. AI öqişi: 3 xil blanka (özbek, rus, telefon surati) bilan sinaldi. Pilotda real blankalarda ölçaymiz. |
| Özbek tili? | Interfeys özbekça; ovoz Aisha STT (özbek tili uçun maxsus); "yuz ellik ikki" kabi sonlarni internetsiz ham tuşunadi. |
