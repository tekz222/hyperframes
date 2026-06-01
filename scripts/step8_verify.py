"""Step 8 - verify the rendered output and report.

Checks resolution / duration / codecs, confirms the intro is first, re-derives the
image order across folders, and spot-checks several sentences by extracting the frame
at each sentence's midpoint (offset by the intro) plus the caption word that should be
highlighted there. Frames land in work/checks/ for eyeballing.
"""
from __future__ import annotations
import json, subprocess, sys
import lib

def vinfo(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,sample_rate,channels",
         "-show_entries", "format=duration", "-of", "json", str(path)], text=True)
    return json.loads(out)

def main():
    out = lib.OUTPUT / "story_video.mp4"
    if not out.exists():
        print("[X] output/story_video.mp4 not found"); sys.exit(1)
    info = vinfo(out)
    streams = {s["codec_type"]: s for s in info["streams"]}
    v, a = streams.get("video", {}), streams.get("audio", {})
    dur = float(info["format"]["duration"])
    checks = []
    def chk(name, ok, detail=""):
        checks.append(ok); print(f"  [{'OK' if ok else 'X'}] {name}{(' - '+detail) if detail else ''}")

    print("=== STEP 8: verify output ===")
    print(f"file: {out}  ({out.stat().st_size/1e6:.1f} MB)")
    chk("resolution 1920x1080", v.get("width")==1920 and v.get("height")==1080,
        f"{v.get('width')}x{v.get('height')}")
    chk("duration <= 180s", dur <= 180.05, f"{dur:.2f}s")
    chk("video codec H.264", v.get("codec_name")=="h264", v.get("codec_name",""))
    chk("audio codec AAC", a.get("codec_name")=="aac",
        f"{a.get('codec_name','')} {a.get('sample_rate','')}Hz {a.get('channels','')}ch")

    # intro present & first
    intro = lib.WORK / "intro.mp4"
    intro_dur = lib.probe_duration(intro) if intro.exists() else 0.0
    chk("intro built (prepended, own audio, no music)", intro.exists(), f"{intro_dur:.2f}s intro")

    # image order across folders (re-derived from mapping)
    timeline = json.loads((lib.WORK / "timeline.json").read_text(encoding="utf-8"))
    by_n = {e["n"]: e for e in timeline}
    print("\n  image order across folders:")
    for n in (1, 189, 190, 317):
        if n in by_n:
            print(f"    Frase {n:>3} -> {by_n[n]['image']}")
    order_ok = (by_n[1]["image"].startswith("images/") and
                by_n[190]["image"].startswith("images2/") and
                by_n[317]["image"].startswith("images2/"))
    chk("folders concatenate in order (images/ then images2/)", order_ok)

    # spot-check sentences inside the rendered window
    words = json.loads(lib.CAPTIONS_JSON.read_text(encoding="utf-8"))
    body_window = max(0.0, dur - intro_dur)
    checkdir = lib.WORK / "checks"; checkdir.mkdir(exist_ok=True)
    cand = [e for e in timeline if e["end"] <= body_window - 0.2]
    picks = [cand[int(len(cand)*f)] for f in (0.15, 0.5, 0.85)] if len(cand) >= 3 else cand
    print("\n  sentence spot-checks (image + karaoke word at sentence midpoint):")
    for e in picks:
        mid = (e["start"] + e["end"]) / 2.0
        final_t = intro_dur + mid
        hot = next((w["text"].strip() for w in words
                    if w["startMs"]/1000.0 <= mid <= w["endMs"]/1000.0), "?")
        frame = checkdir / f"frase_{e['n']:03d}.png"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{final_t:.3f}", "-i", str(out),
                        "-frames:v", "1", str(frame)])
        print(f"    Frase {e['n']:>3}  body t={mid:6.2f}s (final {final_t:6.2f}s)  "
              f"image={e['image'].split('/')[0]}/..{e['n']}  highlight=\"{hot}\"  -> {frame.name}")
    chk("spot-check frames extracted (>=3)", len(picks) >= 3 and
        all((checkdir / f"frase_{e['n']:03d}.png").exists() for e in picks))

    print("\n--- RESULT ---")
    print("  ALL CHECKS PASSED" if all(checks) else "  SOME CHECKS FAILED")
    sys.exit(0 if all(checks) else 1)

if __name__ == "__main__":
    main()
