# 🇹🇷 Turkcha so'zlar boti

Har kuni Telegram orqali turkcha so'zlarni **o'zbekcha tarjimasi, misol gapi va talaffuzi** bilan yuboradi,
keyin ularni **oraliqli takrorlash** (spaced repetition) va qisqa testlar bilan mustahkamlaydi.

## Imkoniyatlar

- **Kunlik so'zlar** — har foydalanuvchi o'z vaqtida va o'z sonida oladi (standart: 09:00, 5 ta)
- **Misol gaplar** — turkcha gap + tarjimasi (tarjima spoiler ostida, avval o'zingiz taxmin qiling)
- **Talaffuz** — 🔊 tugmasi audio yuboradi (gTTS, bir marta yaratilib keshlanadi)
- **Takrorlash testi** — 4 variantli savollar; to'g'ri javobda oraliq 1 → 3 → 7 → 14 → 30 → 60 kunga o'sadi
- **✅ Bilaman / 🔁 Takrorlayman** — har so'z ostida
- **Darajalar** — A1, A2, B1
- **Pulsiz ishlaydi** — 250 dan ortiq tayyor so'z (A1: 114, A2: 78, B1: 62) misol gaplari bilan ichiga o'rnatilgan, API kaliti shart emas
- **Hech qachon takrorlanmaydigan yangi so'zlar** — xohlasangiz, so'zlar tugaganda AI yangilarini yaratadi:
  **bepul Gemini kaliti** (aistudio.google.com/apikey) yoki pullik Claude kaliti bilan
- **Statistika**, admin buyrug'i, xatolarni adminga yuborish, bloklagan foydalanuvchini avtomatik o'chirish
- SQLite (WAL), Docker, loglar, testlar

## Buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `/soz` | Bugungi so'zlar |
| `/test` | Takrorlash testi |
| `/statistika` | Natijalar |
| `/sozlamalar` | Daraja va kunlik sonni tugmalar bilan o'zgartirish |
| `/vaqt 20:00` | Yuborish vaqti |
| `/soni 10` | Kuniga so'zlar soni (1–20) |
| `/daraja A2` | Daraja |
| `/stop`, `/start` | Kunlik xabarlarni to'xtatish / yoqish |
| `/admin` | Umumiy statistika (faqat `ADMIN_ID`) |

## Ishga tushirish (mahalliy)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # BOT_TOKEN va ANTHROPIC_API_KEY ni to'ldiring
python -m bot
```

## VPS'da Docker bilan

```bash
cp .env.example .env        # to'ldiring
docker compose up -d --build
docker compose logs -f
```

Ma'lumotlar `bot-data` nomli volume'da saqlanadi. Zaxira nusxa:

```bash
docker compose cp bot:/app/data/bot.sqlite3 ./backup.sqlite3
```

## Sozlamalar (`.env`)

| O'zgaruvchi | Izoh |
|---|---|
| `BOT_TOKEN` | Majburiy, @BotFather dan |
| `GEMINI_API_KEY` | Bepul. Yangi so'z yaratish uchun (aistudio.google.com/apikey). Bo'sh bo'lsa, faqat ichki so'zlar |
| `GEMINI_MODEL` | Standart `gemini-2.5-flash`. Model eskirib, xato bersa, AI Studio'dagi hozirgi Flash modeliga almashtiring |
| `ANTHROPIC_API_KEY` | Pullik muqobil. Ikkalasi ham bo'lsa, Claude ishlatiladi |
| `ANTHROPIC_MODEL` | Standart `claude-sonnet-5-5` |
| `ADMIN_ID` | Sizning Telegram ID'ingiz (xato xabarlari va `/admin`) |
| `TIMEZONE` | Standart `Asia/Tashkent` (barcha foydalanuvchilar uchun umumiy) |
| `DEFAULT_SEND_TIME`, `DEFAULT_WORDS_PER_DAY` | Yangi foydalanuvchilar uchun standart |
| `QUIZ_LENGTH`, `GENERATE_BATCH` | Test uzunligi va bir martada yaratiladigan so'zlar |

## Tuzilma

```
bot/
  main.py        kirish nuqtasi, handlerlar ro'yxati, scheduler
  handlers.py    buyruqlar va tugmalar
  delivery.py    kunlik yuborish + rejalashtirilgan yuborish
  words.py       ichki ro'yxat va (ixtiyoriy) Gemini/Claude orqali yangi so'zlar
  srs.py         oraliqli takrorlash mantig'i
  db.py          SQLite (users, words, user_words)
  tts.py         talaffuz audiosi
  formatting.py  matnlar va tugmalar
  seed_words.json  254 ta tayyor so'z (A1, A2, B1)
tests/           srs, baza va parser testlari
```

## Testlar

```bash
pip install -r requirements-dev.txt
pytest
```

## Eslatmalar

- AI yaratgan tarjimalar odatda yaxshi, lekin 100% kafolatlanmagan. `words` jadvalini vaqti-vaqti bilan
  ko'zdan kechirib, xatolarni tuzatib turish tavsiya etiladi.
- gTTS Google'ning norasmiy xizmatiga tayanadi. Audio ishlamay qolsa, bot qolgan funksiyalar bilan ishlayveradi.
- Bot long polling bilan ishlaydi: domen yoki HTTPS kerak emas.
