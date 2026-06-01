"""Shared helpers for the hyperframes story-video pipeline.

Pure standard library + ffmpeg/ffprobe on PATH. All other scripts import from here.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, glob, math
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so paths/markers never crash.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------- paths / config
ROOT      = Path(__file__).resolve().parent.parent
WORK      = ROOT / "work"
IMG_OPT   = WORK / "images_opt"
CLIPS     = WORK / "clips"
OUTPUT    = ROOT / "output"
CAPTIONS_JSON = ROOT / "captions.json"
PROMPTS   = ROOT / "historia_iracema_completo.txt"
AUDIO_DIR = ROOT / "audio"
MUSIC_DIR = ROOT / "music"
ANIM_DIR  = ROOT / "animations"

W, H, FPS   = 1920, 1080, 30
CROSSFADE   = 0.5          # seconds of crossfade between consecutive images
SUPERSAMPLE = 2            # zoompan works on a 2x canvas to avoid jitter
NARR_LUFS   = -16.0        # integrated loudness target for narration
MUSIC_GAIN  = 0.18         # base music level before sidechain ducking

def ensure_dirs():
    for d in (WORK, IMG_OPT, CLIPS, OUTPUT):
        d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- subprocess
def run(cmd, cwd=ROOT, check=True):
    """Print a command, run it, stream its output, raise on failure."""
    printable = " ".join(_q(str(c)) for c in cmd)
    print("\n>>", printable, flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd))
    if check and r.returncode != 0:
        raise SystemExit(f"!! command failed (exit {r.returncode}): {printable}")
    return r.returncode

def _q(s):
    return f'"{s}"' if (" " in s or "\t" in s) else s

def probe_duration(path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)], text=True)
    return float(out.strip())

def probe_stream(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,codec_name,r_frame_rate",
         "-of", "json", str(path)], text=True)
    return json.loads(out)["streams"][0]

# ---------------------------------------------------------------- image folders
def image_folders():
    """Ordered list of input image folders: images/, images2/, images3/, ..."""
    out = []
    if (ROOT / "images").is_dir():
        out.append(ROOT / "images")
    n = 2
    while (ROOT / f"images{n}").is_dir():
        out.append(ROOT / f"images{n}")
        n += 1
    return out

def _label(path: Path):
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else None

def opt_path(src: Path) -> Path:
    """Deterministic optimized-image path for a given source image."""
    lbl = _label(src) or 0
    return IMG_OPT / f"{src.parent.name}_{lbl:03d}.jpg"

def frase_to_image():
    """Map global Frase number -> source image Path (cumulative by folder max-label).

    images/ carries labels 1..max -> Frase 1..max; images2/ continues after images/'s
    max label, etc. Missing labels (e.g. images/121) simply have no entry.
    """
    mapping = {}
    offset = 0
    for folder in image_folders():
        labels = {}
        for p in folder.iterdir():
            lbl = _label(p)
            if lbl is not None:
                labels[lbl] = p
        if not labels:
            continue
        for lbl, p in labels.items():
            mapping[offset + lbl] = p
        offset += max(labels)          # advance by max label so gaps keep alignment
    return mapping

# ---------------------------------------------------------------- prompts / frases
def load_frases():
    """Return ordered list of (n, sentence_text) parsed from the prompts file."""
    txt = PROMPTS.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"(?m)^Frase\s+(\d+)\s*:\s*(.+?)\s*$", txt):
        out.append((int(m.group(1)), m.group(2).strip()))
    out.sort(key=lambda x: x[0])
    return out

# ---------------------------------------------------------------- captions / words
def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w, flags=re.UNICODE).lower()

def load_words():
    """Load captions.json -> list of dicts {raw, norm, start, end} (seconds)."""
    data = json.loads(CAPTIONS_JSON.read_text(encoding="utf-8"))
    words = []
    for w in data:
        raw = w["text"].strip()
        words.append({
            "raw": raw,
            "norm": _norm(raw),
            "start": w["startMs"] / 1000.0,
            "end": w["endMs"] / 1000.0,
        })
    return words

def align_frases_to_words(frases, words):
    """Sequentially match each Frase's tokens to the word stream.

    Returns list of dicts: {n, text, start, end, w0, w1} where w0..w1 is the
    inclusive word-index range covered by the sentence. Tolerant to small
    mismatches via a short look-ahead resync window.
    """
    spans = []
    p = 0
    nwords = len(words)
    WINDOW = 12
    for n, text in frases:
        toks = [t for t in (_norm(t) for t in text.split()) if t]
        if not toks:
            continue
        w0 = w1 = None
        for tok in toks:
            found = -1
            for j in range(p, min(p + WINDOW, nwords)):
                if words[j]["norm"] == tok:
                    found = j
                    break
            if found == -1:
                continue                 # frase-only token (filler/punctuation split): skip
            if w0 is None:
                w0 = found
            w1 = found
            p = found + 1
        if w0 is None:                   # whole sentence unmatched: anchor at current p
            w0 = w1 = min(p, nwords - 1)
        spans.append({
            "n": n, "text": text,
            "start": words[w0]["start"],
            "end": words[w1]["end"],
            "w0": w0, "w1": w1,
        })
    # guarantee monotonic, non-overlapping-ish ordering
    for i in range(1, len(spans)):
        if spans[i]["start"] < spans[i-1]["end"]:
            spans[i]["start"] = spans[i-1]["end"]
        if spans[i]["end"] <= spans[i]["start"]:
            spans[i]["end"] = spans[i]["start"] + 0.30
    return spans

# ---------------------------------------------------------------- timeline
def render_plan(timeline):
    """Per-clip timing shared by the clip renderer and the assembler.

    Each clip k is rendered with length L[k] = span[k] + c[k]; in the xfade chain the
    incoming transition c[k] overlaps the previous clip, so the net advance per image
    is exactly span[k]. That keeps the video timeline identical to the narration
    timeline (so burned captions stay in sync). c[k] is shrunk for short sentences.
    """
    spans = [max(0.05, e["end"] - e["start"]) for e in timeline]
    n = len(spans)
    c = [0.0] * n
    for k in range(1, n):
        c[k] = round(min(CROSSFADE, 0.45 * spans[k-1], 0.45 * spans[k]), 3)
    L = [round(spans[k] + c[k], 3) for k in range(n)]
    starts = [0.0] * n
    for k in range(1, n):
        starts[k] = round(starts[k-1] + spans[k-1], 3)
    offsets = [None] * n
    for k in range(1, n):
        offsets[k] = round(starts[k] - c[k], 3)
    total = round(starts[-1] + spans[-1], 3) if n else 0.0
    return {"spans": spans, "c": c, "L": L, "starts": starts,
            "offsets": offsets, "total": total}

def build_timeline():
    """Combine alignment + image mapping into the render timeline (one entry/Frase)."""
    frases = load_frases()
    words  = load_words()
    spans  = align_frases_to_words(frases, words)
    imgmap = frase_to_image()
    timeline = []
    last_img = None
    for s in spans:
        img = imgmap.get(s["n"])
        held = False
        if img is None:
            img = last_img            # hold previous image across a missing one
            held = True
        else:
            last_img = img
        if img is None:
            continue                  # nothing to show yet (shouldn't happen for n=1)
        timeline.append({
            "n": s["n"],
            "start": round(s["start"], 3),
            "end": round(s["end"], 3),
            "image": str(img.relative_to(ROOT)).replace("\\", "/"),
            "held": held,
            "w0": s["w0"], "w1": s["w1"],
        })
    return timeline, words
