import os, re, json, random, datetime, textwrap, requests
from bs4 import BeautifulSoup  # installed in the workflow

OUT_DIR = "docs"
COVERS_DIR = "docs/covers"
BOOKS_FILE = "books.json"

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)

# ---------- helpers ----------
def strip_gutenberg_boilerplate(txt: str) -> str:
    start = re.search(r"\*\*\* START OF(.*?)\*\*\*", txt, flags=re.I|re.S)
    end   = re.search(r"\*\*\* END OF(.*?)\*\*\*", txt, flags=re.I|re.S)
    body = txt[(start.end() if start else 0):(end.start() if end else len(txt))]
    body = re.sub(r'\r', '', body)
    return body.strip()

def normalize_spaces(txt: str) -> str:
    return re.sub(r'[ \t\f\v]+', ' ', re.sub(r'\n{2,}', '\n\n', txt)).strip()

def split_chapters(txt: str):
    # Try common chapter markers first
    parts = re.split(r'\n\s*(CHAPTER\s+\w+\.?.*|BOOK\s+\w+\.?.*|SECTION\s+\w+\.?.*)\n', txt, flags=re.I)
    if len(parts) > 1:
        # Re-stitch as [title, content] pairs
        chunks = []
        it = iter(parts)
        head = next(it, '')
        if head.strip():
            chunks.append(("Introduction", head))
        for title, content in zip(it, it):
            title = title.strip()
            chunks.append((title, content.strip()))
        return chunks
    # Fallback: split on long dashed headings or big gaps
    rough = re.split(r'\n\s*[-=]{3,}\s*\n', txt)
    return [(f"Section {i+1}", s.strip()) for i, s in enumerate(rough) if s.strip()]

def choose_important_section(chunks):
    # Prefer intros/forewords or chapters with these leadership/self-dev keywords
    KEYWORDS = [
        "introduction","preface","foreword","self-reliance","character","discipline",
        "habit","leadership","strategy","decision","time","focus","resolve","courage",
        "thought and character","purpose","planning"
    ]
    # Score each chunk: short-enough + keyword boost + early-position boost
    scored = []
    for idx, (title, content) in enumerate(chunks):
        words = len(content.split())
        # We want ~300–600 words; allow 220–900 with penalty outside range
        target_low, target_high = 220, 900
        length_score = 1.0
        if words < target_low:
            length_score -= (target_low - words) / target_low
        elif words > target_high:
            length_score -= (words - target_high) / target_high
        kw_score = 0.0
        t = f"{title}\n{content[:300]}".lower()
        for kw in KEYWORDS:
            if kw in t:
                kw_score += 0.7
        pos_score = max(0.0, 0.5 - idx * 0.03)  # earlier sections slightly preferred
        score = length_score + kw_score + pos_score
        scored.append((score, idx, title, content))
    scored.sort(reverse=True)
    # Pick the top-scoring, but if it's too long, trim to ~550 words at paragraph boundary
    for score, idx, title, content in scored:
        paras = [p.strip() for p in content.split("\n") if p.strip()]
        # Build up to ~550 words
        sel = []
        wcount = 0
        for p in paras:
            w = len(p.split())
            if wcount + w > 580 and sel:
                break
            sel.append(p)
            wcount += w
        chosen = "\n\n".join(sel).strip()
        if len(chosen.split()) >= 220:
            return title, chosen
    # Fallback: first reasonable chunk
    title, content = chunks[0]
    return title, content[:1200]

def safe_html(s: str) -> str:
    # very light escape for &, <, >
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ---------- load catalog ----------
with open(BOOKS_FILE, "r", encoding="utf-8") as f:
    catalog = json.load(f)

book = random.choice(catalog)

# ---------- fetch & pick ----------
resp = requests.get(book["gutenberg_url"], timeout=60)
resp.raise_for_status()
raw = resp.text

body = strip_gutenberg_boilerplate(raw)
# Ensure nice newlines around headings
body = re.sub(r'(\n\s*)(CHAPTER|BOOK|SECTION)\b', r'\n\n\2', body, flags=re.I)
chunks = split_chapters(body)
if not chunks:
    chunks = [("Passage", body[:1800])]

section_title, passage = choose_important_section(chunks)

# ---------- build HTML (no links, show cover image if present) ----------
today = datetime.date.today().strftime("%B %d, %Y")
cover_path = f"covers/{book.get('cover','placeholder.jpg')}"
cover_exists = os.path.exists(os.path.join(OUT_DIR, cover_path))

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Daily One-Pager • {today}</title>
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; background:#0f172a; color:#e2e8f0; }}
  .wrap {{ max-width: 820px; margin: 56px auto; padding: 0 20px; }}
  .card {{ background:#111827; border-radius:20px; padding:28px; box-shadow:0 10px 30px rgba(0,0,0,.35); }}
  h1 {{ margin: 0 0 6px; font-size: 26px; }}
  .meta {{ opacity:.85; font-size:14px; margin-bottom:16px }}
  .cover {{ width: 160px; height: 220px; background:#1f2937; border-radius:8px; margin: 6px 0 18px; display:block; }}
  .nocover {{ display:flex; align-items:center; justify-content:center; color:#94a3b8; font-size:13px; }}
  p {{ line-height:1.75; white-space:pre-wrap; }}
  .section {{ font-size: 16px; opacity:.9; margin-top: -6px; margin-bottom:12px; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="meta">{safe_html(today)}</div>
      <h1>{safe_html(book['title'])}</h1>
      <div class="meta">by {safe_html(book['author'])}</div>
      {"<img class='cover' alt='Book cover' src='" + safe_html(cover_path) + "' />" if cover_exists else "<div class='cover nocover'>cover image not found</div>"}
      <div class="section">{safe_html(section_title)}</div>
      <p>{safe_html(passage)}</p>
    </div>
  </div>
</body>
</html>"""

with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print("Generated daily one-pager.")
