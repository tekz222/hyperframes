"""Step 2 - optimize every source image to 1920x1080 (scale-to-cover), reduce size.

Originals are never touched; optimized copies go to work/images_opt/.
Idempotent: skips images already optimized (use --force to rebuild).
"""
from __future__ import annotations
import sys
import lib

def main(force=False):
    lib.ensure_dirs()
    print("=== STEP 2: optimize images ===")
    srcs = []
    for folder in lib.image_folders():
        for p in sorted(folder.iterdir(), key=lambda x: (lib._label(x) or 0)):
            if p.suffix.lower() in (".jpeg", ".jpg", ".png"):
                srcs.append(p)
    print(f"{len(srcs)} source images")
    done = skipped = 0
    for i, src in enumerate(srcs, 1):
        out = lib.opt_path(src)
        if out.exists() and not force:
            skipped += 1
            continue
        lib.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", src,
            "-vf", f"scale={lib.W}:{lib.H}:force_original_aspect_ratio=increase,"
                   f"crop={lib.W}:{lib.H},setsar=1",
            "-q:v", "3", out,
        ])
        done += 1
        if done % 25 == 0:
            print(f"  ... {i}/{len(srcs)} processed")
    print(f"done: {done} optimized, {skipped} already present -> {lib.IMG_OPT}")

if __name__ == "__main__":
    main(force="--force" in sys.argv)
