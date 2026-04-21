# Felvételi Games

Gamifikált felvételi felkészítő alkalmazás középiskolai (4, 6, 8 osztályos gimnáziumi) matematika és magyar nyelv feladatokhoz.

A feladatsorokat az [oktatas.hu](https://www.oktatas.hu)-ról tölti le, GPT-vel dolgozza fel, majd egy interaktív Streamlit kvíz felületen keresztül teszi elérhetővé — hangfelismeréssel, TTS felolvasással és azonnali GPT értékeléssel.

---

## Funkciók

- **Automatikus letöltés** — feladatsorok és javítási útmutatók scrapeléssel vagy ZIP-ből
- **GPT-alapú kinyerés** — strukturált feladatobjektumok Markdown + LaTeX formázással
- **Streamlit kvíz UI** — típus-alapú válaszmegadás (radio, szabad szöveg, hangfelvétel)
- **Azonnali értékelés** — GPT összehasonlítja a választ az elfogadott megoldásokkal
- **TTS / STT** — OpenAI Whisper + TTS hangos kérdések és válaszok
- **Menet követés** — pontszám, streak, megoldott feladatok, időmérés
- **CLI eszközök** — letöltés, feldolgozás, állapotellenőrzés egy parancsból

---

## Telepítés

### Előfeltételek

- Python 3.10+
- [conda](https://docs.conda.io/) (ajánlott) vagy virtualenv
- `pdftotext` rendszerfüggőség (poppler)
- OpenAI API kulcs

### Lépések

```bash
# 1. conda környezet létrehozása
conda create -n felvi python=3.12
conda activate felvi

# 2. pdftotext telepítése (conda-forge)
conda install -c conda-forge pdftotext

# 3. Csomag telepítése fejlesztői módban
pip install -e ".[dev]"

# 4. Környezeti változók beállítása
cp .env.example .env
# Szerkeszd a .env fájlt (lásd alább)
```

### `.env` konfiguráció

```dotenv
# OpenAI API kulcs (kötelező)
OPENAI_API_KEY=sk-...

# Adatbázis elérési útja (opcionális, alap: ./data/felvi.db)
FELVI_DB=W:/Users/Felvi/felvi.db

# Feladatsor PDF-ek mappája (opcionális, alap: ./exams)
FELVI_EXAMS=W:/Users/Felvi/exams

# Asset mappa TTS MP3 fájlokhoz (opcionális, alap: ./data/assets)
FELVI_ASSETS=W:/Users/Felvi/assets

# GPT modell (opcionális, alap: gpt-4o)
LLM_MODEL=gpt-4o
```

---

## CLI használat

Minden parancs a `felvi` CLI-n keresztül érhető el.

### `felvi info` — Állapotellenőrzés

```bash
felvi info              # teljes áttekintés
felvi info --szint 4    # csak a 4 osztályos anyag
```

Megmutatja:
- Konfiguráció (DB, exams, assets mappa)
- Letöltött PDF-ek évfolyam / év / változat bontásban (fl✓ ut✓)
- DB statisztika (feladatszám szint és tárgy szerint)

### `felvi scrape` — PDF-ek letöltése

```bash
# Gyors: összes évfolyam ZIP-ből (ajánlott első futtatáshoz)
felvi scrape --zip

# Csak 4 osztályos (9. évfolyamos) feladatsorok
felvi scrape --only 4 --zip

# Legfrissebb 2 év scrapeléssel (lassabb, de aktuálisabb)
felvi scrape --only 4 --years 2

# Száraz futás (csak listáz, nem tölt le)
felvi scrape --dry-run
```

**`--only` értékek:** `4` = 4 osztályos gimnázium, `6` = 6 osztályos, `8` = 8 osztályos

### `felvi parse` — GPT feldolgozás

```bash
# 2023-as 4 osztályos matek feladatok
felvi parse --szint 4 --year 2023 --targy matek

# Összes letöltött anyag feldolgozása
felvi parse

# Max 3 pár (teszteléshez)
felvi parse --szint 4 --year 2023 --limit 3

# Feldolgozás + CLI review
felvi parse --szint 4 --year 2023 --review

# DB-be mentés nélkül (teszt)
felvi parse --dry-run
```

---

## Fájlnév konvenció

A PDF-ek neve: `{T}{G}_{YYYY}_{N}_{tipus}.pdf`

| Mező | Értékek | Példa |
|---|---|---|
| `T` | `A` = magyar, `M` = matek | `A` |
| `G` | `8` = 4 osztályos, `6` = 6 osztályos, `4` = 8 osztályos | `8` |
| `YYYY` | Év | `2023` |
| `N` | Változat száma | `1`, `2` |
| `tipus` | `fl` = feladatlap, `ut` = útmutató | `fl` |

Példa: `M8_2023_1_fl.pdf` → 4 osztályos matek, 2023, 1. változat, feladatlap

---

## Az app futtatása

```bash
conda activate felvi
cd felvi_games
streamlit run src/felvi_games/app.py
```

Megnyílik: **http://localhost:8501**

A Streamlit automatikusan észleli a kódváltozásokat és újratölt mentéskor.

---

## Tesztek futtatása

```bash
conda activate felvi
cd felvi_games
pytest tests/ -q
```

A PDF-scraping tesztek (`test_matek_prefix` stb.) valódi fájlokhoz kötöttek — kihagyhatók:

```bash
pytest tests/ -q -k "not (test_matek_prefix or test_magyar_prefix or test_4osztaly_prefix or test_matek_feladatlap or test_magyar_utmutato or test_4osztaly_feladatlap or test_get_menetek_returns_newest_first)"
```

---

## Projekt struktúra

```
felvi_games/
├── src/felvi_games/
│   ├── app.py          # Streamlit UI
│   ├── cli.py          # CLI belépési pont (felvi scrape/parse/info)
│   ├── scraper.py      # PDF letöltés oktatas.hu-ról
│   ├── pdf_parser.py   # PDF → TaskBlock → GPT → Feladat pipeline
│   ├── status.py       # Konfig / PDF / DB állapotellenőrzés
│   ├── ai.py           # GPT értékelés (check_answer)
│   ├── db.py           # SQLAlchemy adatbázis réteg
│   ├── models.py       # Feladat, FeladatCsoport, GameState adatmodellek
│   ├── config.py       # Env változók, útvonalak
│   └── review.py       # CLI review eszköz
├── tests/
│   ├── test_db.py
│   ├── test_pdf_parser.py
│   └── test_review.py
├── data/               # SQLite DB + TTS asset-ek (gitignore)
├── exams/              # Letöltött PDF-ek (gitignore)
├── docs/
│   └── swe.md          # Fejlesztési elvek és folyamat
└── pyproject.toml
```

---

## Tipikus első indítás

```bash
conda activate felvi

# 1. Állapotellenőrzés
felvi info

# 2. PDF-ek letöltése (4 osztályos, minden év)
felvi scrape --only 4 --zip

# 3. Feldolgozás (pl. 2023-as matek)
felvi parse --szint 4 --year 2023 --targy matek

# 4. Állapot újra
felvi info --szint 4

# 5. App indítása
streamlit run src/felvi_games/app.py
```
