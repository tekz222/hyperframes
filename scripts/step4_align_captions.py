"""Step 4 - align sentences to the word timeline and emit karaoke captions.

Outputs:
  work/timeline.json   one entry per Frase: {n, start, end, image, held}
  work/captions.ass    TikTok-style word-by-word karaoke (narration-relative times)

The image<->sentence sync and the captions are both driven by captions.json, so a
word's on-screen image and its highlighted caption word share the same clock.
"""
from __future__ import annotations
import json, re
import lib

# ---- caption styling (ASS) ----
FONT        = "Montserrat Black"   # heavy sans-serif, bundled in assets/fonts
FONT_SIZE   = 78
HL_COLOR    = "&H0000FFFF"   # active word: pure bright yellow (AABBGGRR -> R255 G255 B0)
BASE_COLOR  = "&H00FFFFFF"   # inactive words: white
OUTLINE     = "&H00000000"   # pure black outline
OUTLINE_W   = 7             # outline thickness (px) - thick so text reads on any image
MAX_WORDS   = 5             # words per caption line
MAX_CHARS   = 30            # or break a line once it gets this wide
SENT_END    = re.compile(r'[.!?:]["”»)]?$')

def _ass_time(t: float) -> str:
    if t < 0: t = 0.0
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"

def _chunk_lines(words):
    """Group words into short caption lines, breaking at sentence ends."""
    lines, cur, chars = [], [], 0
    for i, w in enumerate(words):
        cur.append(i)
        chars += len(w["raw"]) + 1
        end_sentence = bool(SENT_END.search(w["raw"]))
        if len(cur) >= MAX_WORDS or chars >= MAX_CHARS or end_sentence:
            lines.append(cur)
            cur, chars = [], 0
    if cur:
        lines.append(cur)
    return lines

def build_ass(words, path, end_limit=None):
    lines = _chunk_lines(words)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {lib.W}
PlayResY: {lib.H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{FONT},{FONT_SIZE},{BASE_COLOR},{BASE_COLOR},{OUTLINE},&H64000000,0,0,0,0,100,100,0,0,1,{OUTLINE_W},0,2,80,80,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in lines:
        lwords = [words[i] for i in line]
        line_start = lwords[0]["start"]
        line_end   = lwords[-1]["end"]
        if end_limit is not None and line_start >= end_limit:
            break
        for k, wi in enumerate(line):
            w = words[wi]
            ev_start = w["start"] if k == 0 else words[line[k-1]]["end"]
            ev_end   = w["end"] if k < len(line) - 1 else line_end
            if end_limit is not None:
                ev_end = min(ev_end, end_limit)
            if ev_end <= ev_start:
                continue
            parts = []
            for j, wj in enumerate(lwords):
                txt = wj["raw"].upper().replace("{", "(").replace("}", ")")
                if j == k:
                    parts.append(r"{\c" + HL_COLOR + r"\fscx112\fscy112}" + txt +
                                 r"{\c" + BASE_COLOR + r"\fscx100\fscy100}")
                else:
                    parts.append(txt)
            text = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_ass_time(ev_start)},{_ass_time(ev_end)},"
                f"Karaoke,,0,0,0,,{text}")
    path.write_text(head + "\n".join(events) + "\n", encoding="utf-8")
    return len(events)

def main():
    lib.ensure_dirs()
    print("=== STEP 4: align + captions ===")
    timeline, words = lib.build_timeline()

    tl_path = lib.WORK / "timeline.json"
    tl_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    body_dur = timeline[-1]["end"]
    print(f"timeline: {len(timeline)} sentences, image-section duration {body_dur:.2f}s")
    print(f"  -> {tl_path}")

    ass = lib.WORK / "captions.ass"
    nev = build_ass(words, ass)
    print(f"captions: {nev} karaoke events -> {ass}")

    # ---- spot-check a few sentences ----
    print("\n--- spot-check (sentence -> [start,end] -> image) ---")
    for idx in (0, 1, 6, len(timeline)//2, len(timeline)-1):
        e = timeline[idx]
        held = "  (held-over image)" if e["held"] else ""
        print(f"  Frase {e['n']:>3}  {e['start']:>7.2f}-{e['end']:>7.2f}s  "
              f"{e['image']}{held}")
        print(f"        \"{next(t for n,t in lib.load_frases() if n==e['n'])[:70]}...\"")

    # sanity: monotonic + coverage
    bad = [i for i in range(1, len(timeline)) if timeline[i]["start"] < timeline[i-1]["start"]]
    print(f"\nmonotonic starts: {'OK' if not bad else 'PROBLEM at '+str(bad[:5])}")
    matched_words = sum(e["w1"] - e["w0"] + 1 for e in timeline)
    print(f"words covered by sentences: ~{matched_words} of {len(words)}")

if __name__ == "__main__":
    main()
