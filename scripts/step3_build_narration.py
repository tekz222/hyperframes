"""Step 3 - concatenate narration files in numeric order and normalize loudness.

audio/1.mp3 .. audio/N.mp3 (sorted by the integer in the filename) -> one continuous
track, loudness-normalized to NARR_LUFS. Output: work/narration.wav (48k stereo).

Loudness is normalized by *measuring* integrated loudness then applying a single
static gain (the `volume` filter cannot change duration), instead of the one-pass
`loudnorm` filter which was observed to corrupt output duration here.
"""
from __future__ import annotations
import re, json, subprocess
import lib

def measure_loudness(path):
    """Return measured integrated loudness (LUFS) via loudnorm's JSON print pass."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", f"loudnorm=I={lib.NARR_LUFS}:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    data = json.loads(m.group(0))
    return float(data["input_i"])

def main():
    lib.ensure_dirs()
    print("=== STEP 3: build narration ===")
    files = sorted(lib.AUDIO_DIR.glob("*.mp3"),
                   key=lambda p: int(re.match(r"(\d+)", p.stem).group(1)))
    print("order:", [f.name for f in files])

    listfile = lib.WORK / "audio_concat.txt"
    listfile.write_text(
        "".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")

    raw = lib.WORK / "narration_raw.wav"
    lib.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", listfile,
             "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", raw])

    measured = measure_loudness(raw)
    gain = lib.NARR_LUFS - measured
    print(f"measured integrated loudness: {measured:.2f} LUFS -> applying {gain:+.2f} dB")

    out = lib.WORK / "narration.wav"
    lib.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", raw,
             "-af", f"volume={gain:.2f}dB,alimiter=limit=0.95",
             "-ar", "48000", "-ac", "2", out])

    raw_d, out_d = lib.probe_duration(raw), lib.probe_duration(out)
    print(f"narration: {out_d:.2f}s (raw {raw_d:.2f}s) -> {out}")
    if abs(out_d - raw_d) > 1.0:
        raise SystemExit(f"!! duration drift after normalize: {out_d:.2f} vs {raw_d:.2f}")

if __name__ == "__main__":
    main()
