"""Step 1 - verify the input contract and report counts/mappings. Fails loudly."""
from __future__ import annotations
import sys
import lib

def main():
    print("=== STEP 1: verify inputs ===")
    problems = []

    folders = lib.image_folders()
    print(f"image folders: {[f.name for f in folders]}")
    total_imgs = 0
    for f in folders:
        n = len(list(f.glob("*.jpeg"))) + len(list(f.glob("*.jpg"))) + len(list(f.glob("*.png")))
        total_imgs += n
        print(f"  {f.name}: {n} images")
    if total_imgs == 0:
        problems.append("no images found")

    audio = sorted(lib.AUDIO_DIR.glob("*.mp3"))
    print(f"audio files ({len(audio)}): {[a.name for a in audio]}")
    if not audio:
        problems.append("no narration files in audio/")

    music = sorted(lib.MUSIC_DIR.glob("*.*"))
    print(f"music files ({len(music)}): {[m.name for m in music]}")
    if not music:
        problems.append("no background-music file in music/")

    anims = sorted(lib.ANIM_DIR.glob("*.*")) if lib.ANIM_DIR.is_dir() else []
    print(f"intro animations ({len(anims)}): {[a.name for a in anims]}")
    if not anims:
        problems.append("no intro clips in animations/ (user requested an intro)")

    if not lib.CAPTIONS_JSON.exists():
        problems.append("captions.json missing")
    if not lib.PROMPTS.exists():
        problems.append("prompts file historia_iracema_completo.txt missing")

    # frase <-> image reconciliation
    frases = lib.load_frases()
    imgmap = lib.frase_to_image()
    print(f"Frase entries in prompts: {len(frases)} (max N = {frases[-1][0]})")
    missing = [n for n, _ in frases if n not in imgmap]
    print(f"Frase numbers with NO image (held over): {missing}")
    print(f"images mapped to a Frase: {len(imgmap)}")

    # caption / audio timeline sanity
    words = lib.load_words()
    audio_total = sum(lib.probe_duration(a) for a in audio)
    cap_end = max(w["end"] for w in words)
    print(f"caption words: {len(words)}  caption span: {cap_end:.2f}s  audio total: {audio_total:.2f}s")
    if abs(cap_end - audio_total) > 5.0:
        problems.append(f"captions span ({cap_end:.1f}s) and audio total ({audio_total:.1f}s) "
                        f"diverge by >5s - captions.json may not match this audio order")

    print("\n--- RESULT ---")
    if problems:
        for p in problems:
            print(f"  [X] {p}")
        sys.exit(1)
    print("  [OK] all inputs present and consistent")

if __name__ == "__main__":
    main()
