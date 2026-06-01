"""Step 6 - render one Ken Burns clip per sentence.

Each optimized image becomes a clip of length L[k] (span + incoming crossfade) with an
eased (smoothstep) zoom + pan. Pan direction and zoom direction alternate per clip, so
the assembled sequence reads as a slow continuous pendulum drift rather than robotic,
constant-velocity motion. Clips are silent; audio is mixed at assembly.

Resumable: existing clips are skipped (use --force to rebuild). --upto SECONDS renders
only the clips needed to cover the first SECONDS of the image section (fast preview);
with no flag it renders the whole timeline (full assets).
"""
from __future__ import annotations
import sys, json, argparse
import lib

SUPER_W, SUPER_H = 2560, 1440   # supersample canvas to smooth zoompan motion

def kenburns_vf(idx, nframes):
    N = max(nframes, 2)
    s  = f"(on/{N-1})"
    sm = f"({s}*{s}*(3-2*{s}))"                      # smoothstep easing
    z0, z1 = (1.06, 1.20) if idx % 2 == 0 else (1.20, 1.06)
    zexpr = f"({z0}+({z1-z0:.4f})*{sm})"
    quad = idx % 4
    fx0, fx1, fy0, fy1 = {
        0: (0.12, 0.88, 0.50, 0.50),
        1: (0.88, 0.12, 0.50, 0.50),
        2: (0.50, 0.50, 0.12, 0.88),
        3: (0.50, 0.50, 0.88, 0.12),
    }[quad]
    fx = f"min(1,max(0,{fx0}+({fx1-fx0:.3f})*{sm}+0.03*sin(2*PI*{s})))"
    fy = f"min(1,max(0,{fy0}+({fy1-fy0:.3f})*{sm}+0.03*sin(2*PI*{s})))"
    xexpr = f"(iw-iw/zoom)*({fx})"
    yexpr = f"(ih-ih/zoom)*({fy})"
    return (
        f"scale={SUPER_W}:{SUPER_H}:force_original_aspect_ratio=increase,"
        f"crop={SUPER_W}:{SUPER_H},"
        f"zoompan=z='{zexpr}':x='{xexpr}':y='{yexpr}':d={N}:s={lib.W}x{lib.H}:fps={lib.FPS},"
        f"setsar=1,format=yuv420p"
    )

def render_one(k, entry, length, force=False):
    out = lib.CLIPS / f"{k:04d}.mp4"
    if out.exists() and not force:
        return False
    src = lib.opt_path(lib.ROOT / entry["image"])
    if not src.exists():
        raise SystemExit(f"!! optimized image missing: {src} (run step 2)")
    nframes = max(2, round(length * lib.FPS))
    lib.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", src,
        "-frames:v", str(nframes),
        "-vf", kenburns_vf(k, nframes),
        "-r", str(lib.FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", out,
    ])
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upto", type=float, default=None,
                    help="only render clips covering the first N seconds of the body")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    lib.ensure_dirs()
    timeline = json.loads((lib.WORK / "timeline.json").read_text(encoding="utf-8"))
    plan = lib.render_plan(timeline)
    n = len(timeline)

    last = n
    if args.upto is not None:
        last = next((k for k in range(n) if plan["starts"][k] >= args.upto), n)
        last = min(last + 1, n)        # include the clip straddling the boundary
    print(f"=== STEP 6: render clips [0..{last-1}] of {n} "
          f"({'preview ' + str(args.upto) + 's' if args.upto else 'full timeline'}) ===")

    done = skipped = 0
    for k in range(last):
        if render_one(k, timeline[k], plan["L"][k], force=args.force):
            done += 1
        else:
            skipped += 1
        if (done + skipped) % 20 == 0:
            print(f"  ... {done+skipped}/{last}  (rendered {done}, skipped {skipped})")
    print(f"done: rendered {done}, skipped {skipped} -> {lib.CLIPS}")

if __name__ == "__main__":
    main()
