"""
LLM normalisation pass — maps all unmapped raw_names from price_readings
to cardmarket_products entries or marks them null_mapped.

Run from project root: python3 scripts/run_llm_mapping.py
"""
import sqlite3, difflib, re
from datetime import datetime, timezone

# ── helpers ───────────────────────────────────────────────────────────────────

def fix_enc(s):
    """Fix common UTF-8-as-Latin1 mojibake (e.g. PokÃ©mon → Pokémon)."""
    try:
        return s.encode('latin1').decode('utf-8')
    except Exception:
        return s

def split_concat(s):
    """Split words that got concatenated: 'Pokemon151CollectionEX' → 'Pokemon 151 Collection EX'."""
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    s = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', s)
    s = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', s)
    return s

def normalize(s):
    """Normalize a name for fuzzy matching."""
    s = fix_enc(s)
    s = split_concat(s)
    s = s.lower()
    # Remove TCG brand prefixes (both sides will strip these)
    for pfx in ['pokémon tcg:', 'pokémon tcg -', 'pokemon tcg:', 'pokemon tcg -',
                'pokémon:', 'pokemon:']:
        s = s.replace(pfx, '')
    s = s.replace('pokémon', 'pokemon')
    # Strip Finnish decorators
    for w in [' keräilykortit', ' keräilykortti', ' keräilykorttipeli',
              ' korttipakkaus', ' kortit', ' boosterpakkaus', ' boosteri',
              ' boosteria', ' kpl', ' erilaisia', ' ennakkotilaus',
              ' (max ', '/asiakas']:
        s = s.replace(w, ' ')
    # Strip language annotations
    for w in ['(englanniksi)', '(japaniksi)', '(yksinkertaistettu kiina)',
              'englanniksi', 'japaniksi', 'yksinkertaistettu kiina',
              'simplified chinese', 'japanese', 'english',
              't-chinese', 's-chinese', 'korean']:
        s = s.replace(w, ' ')
    # Normalize separators/punctuation
    for ch in '–—:/\\&()[]{}':
        s = s.replace(ch, ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def combined_sim(a, b):
    """Max of char-level SequenceMatcher and word-level Jaccard."""
    char_sim = difflib.SequenceMatcher(None, a, b).ratio()
    wa, wb = set(a.split()), set(b.split())
    word_j = len(wa & wb) / len(wa | wb) if (wa | wb) else 0
    return max(char_sim, word_j)

# ── null-map patterns — clearly NOT sealed Pokemon TCG in Cardmarket catalogue ─

NULL_PATTERNS = [
    # Non-Pokemon brands
    'brainrot', 'disney lorcana', 'gabby', 'gamegenic',
    'grinch pehmolelu', 'happy birthday pop up', 'holomonsters',
    'k-pop demon', 'kpop demon', 'skifidol',
    'topps englannin', 'topps formula',
    'ultimate guard katana', 'upper deck mvp',
    # FIFA / football
    'fifa', 'panini top class',
    # Other TCG
    'mtg:', 'magic the gathering', 'magic: the gathering',
    # LEGO / Mega Construx building toys
    'lego pokemon', 'lego pokémon', 'mega construx',
    # MEGA brand building toys (not Mega Evolution TCG!)
    'mega pokemon bulbasaur', 'mega pokemon center',
    'mega pokemon pikachu', 'mega pokemon charizard 1664',
    'mega pokemon forest center', 'mega pokemon jumbo great ball',
    'mega pokemon jungle voyage', 'mega pokemon motion',
    'mega pokemon paldea', 'mega pokemon pixel',
    'mega pokemon trainer pack pallot', 'mega pokemon tuulimylly',
    'mega pokemon ultimate jungle', 'mega pokémon zubat',
    'mega construx jumbo rakennettava',
    # Board games / puzzles
    'monopoly', 'muuttuva labyrintti', 'palapeli', 'ravensburger 3d',
    # Plush toys
    'pehmolelu', ' pehmo', 'squishmallows', 'pehmoreppu',
    # Action figures / Clip'n'Go toys
    'battle figuuri', 'battle spinner', 'battle feature figure',
    'battle figures', "clip 'n' go", "clip 'n go", "clip'n'go",
    'clip-on maskotti', 'figuuri ja clip', 'hahmopakkaus battle',
    'epic battle', 'epic suuri figuuri', 'carry case playset',
    'pokemon battle figuuri 8-pack', 'pokemon battle spinner areena',
    # Costumes / dress-up
    'naamiaisasu', 'haalariasu', 'fancy dress', 'pikachu-puku',
    'naamari pikachu',
    # Headbands / non-TCG accessories
    'panta pikachu', 'pikachu korvat',
    # Generic accessories not in catalogue
    'ultra pro penny sleeves', 'ultra pro regular toploader',
    'ultra pro silver blue 9', 'ultra pro warhammer',
    'ultra pro pikachu toploader and penny',
    # Other toys/items
    'värityskirja', 'folioilmapallo', 'digitaalinen led rannekello',
    'takara tomy', 'pallo pehmolelu', 'pehmo clip on',
    'pehmolelu 20 cm gen ix', 'pehmolelu 30 cm erilaisia',
    'pehmolelu 50 cm eevee', '20 cm pehmolelu cuddly',
    'pehmo 10 cm poképallo', 'pikachu pehmolelu reppu',
    'keräilykansio ja korttipakka',
    # Funko
    'funko',
    # Individual promo cards (not sealed)
    'togekiss –', 'umbreon ex – sv',
    "team rocket's moltres", "team rocket's persian",
    'ursaring – skyridge', 'venonat – skyridge',
    'zamazenta – destined rivals #',
]

def is_null_mapped(raw):
    low = raw.lower()
    if any(p in low for p in NULL_PATTERNS):
        return True
    # Pokemon 25v. juhlamalli = commemorative plush/figure
    if 'juhlamalli' in low and 'tcg' not in low:
        return True
    # Individual promo cards: "Name – Set #NNN"
    if re.search(r'–\s*[^–\n]+#\d{2,}', raw):
        return True
    return False

# ── main ──────────────────────────────────────────────────────────────────────

conn = sqlite3.connect('pokemon.db')
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

names = [r[0] for r in conn.execute('''
    SELECT DISTINCT raw_name FROM price_readings
    WHERE raw_name NOT IN (SELECT raw_name FROM name_mappings)
    ORDER BY raw_name
''').fetchall()]
print(f"{len(names)} unmapped names to process")

catalogue = conn.execute(
    "SELECT id, name FROM cardmarket_products ORDER BY name"
).fetchall()
cat_orig = [c[1] for c in catalogue]
cat_ids  = {c[1]: c[0] for c in catalogue}
cat_norm = [normalize(n) for n in cat_orig]

results = []
null_count = 0
matched_count = 0
undecided_count = 0

for raw in names:
    # ── null-map check ───────────────────────────────────────────────────────
    if is_null_mapped(raw):
        results.append((raw, None, None, 0.97, 'null_mapped'))
        null_count += 1
        continue

    # ── fuzzy catalogue match ────────────────────────────────────────────────
    norm_raw = normalize(raw)

    # get_close_matches for efficiency (cutoff 0.35 so we catch partial Finnish names)
    close = difflib.get_close_matches(norm_raw, cat_norm, n=5, cutoff=0.35)

    if not close:
        results.append((raw, None, None, None, 'undecided'))
        undecided_count += 1
        continue

    # re-rank with combined sim
    ranked = sorted(close, key=lambda c: -combined_sim(norm_raw, c))
    best_norm = ranked[0]
    best_score = combined_sim(norm_raw, best_norm)

    # resolve back to original catalogue entry (first match wins for ties)
    try:
        best_idx = cat_norm.index(best_norm)
    except ValueError:
        results.append((raw, None, None, None, 'undecided'))
        undecided_count += 1
        continue

    best_orig = cat_orig[best_idx]
    best_id   = cat_ids[best_orig]

    if best_score >= 0.85:
        results.append((raw, best_id, None, round(best_score, 3), 'mapped'))
        matched_count += 1
    elif best_score >= 0.35:
        results.append((raw, None, best_id, round(best_score, 3), 'undecided'))
        undecided_count += 1
    else:
        results.append((raw, None, None, round(best_score, 3), 'undecided'))
        undecided_count += 1

print(f"  null_mapped: {null_count}, mapped: {matched_count}, undecided: {undecided_count}")

# ── insert ────────────────────────────────────────────────────────────────────
for raw_name, cm_id, suggestion_id, conf, status in results:
    mapped_at = now if status in ('mapped', 'null_mapped') else None
    conn.execute("""
        INSERT OR IGNORE INTO name_mappings
            (raw_name, cardmarket_product_id, llm_suggestion_id, confidence, status, mapped_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (raw_name, cm_id, suggestion_id, conf, status, mapped_at))

conn.commit()
print(f"Committed {len(results)} rows")

# ── verify ────────────────────────────────────────────────────────────────────
stats = dict(conn.execute("SELECT status, COUNT(*) FROM name_mappings GROUP BY status").fetchall())
print("\nFinal name_mappings stats:", stats)

print("\nSample MAPPED (20 most recent):")
for row in conn.execute("""
    SELECT nm.raw_name, cp.name, nm.confidence
    FROM name_mappings nm
    JOIN cardmarket_products cp ON nm.cardmarket_product_id = cp.id
    WHERE nm.status = 'mapped'
    ORDER BY nm.rowid DESC LIMIT 20
""").fetchall():
    print(f"  {row[2]:.2f} | {row[0][:50]:50} → {row[1][:50]}")

print("\nSample UNDECIDED with suggestions (10):")
for row in conn.execute("""
    SELECT nm.raw_name, cp.name, nm.confidence
    FROM name_mappings nm
    LEFT JOIN cardmarket_products cp ON nm.llm_suggestion_id = cp.id
    WHERE nm.status = 'undecided' AND nm.llm_suggestion_id IS NOT NULL
    ORDER BY nm.rowid DESC LIMIT 10
""").fetchall():
    print(f"  {row[2]:.2f} | {row[0][:50]:50} → {row[1][:50] if row[1] else '—'}")

print("\nSample NULL_MAPPED (10 most recent):")
for row in conn.execute("""
    SELECT raw_name FROM name_mappings WHERE status='null_mapped'
    ORDER BY rowid DESC LIMIT 10
""").fetchall():
    print(f"  {row[0]}")

conn.close()
print("\nDone.")
