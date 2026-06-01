"""Step 6 - render one Ken Burns clip per sentence.

Each optimized image becomes a clip of length L[k] (span + incoming crossfade) with an
eased (smoothstep) zoom plus a slow, low-frequency sine sway, so the image appears to
float / swing gently like a pendulum instead of panning on a straight line. The motion
is rendered on a larger canvas and downscaled to 1080p, which averages out zoompan's
per-frame integer rounding (the cause of the visible "shake"). Clips are silent; audio
is mixed at assembly.

Resumable: existing clips are skipped (use --force to rebuild). --upto SECONDS renders
only the clips needed to cover the first SECONDS of the image section (fast preview);
with no flag it renders the whole timeline (full assets).
"""
from __future__ import annotations
import sys, json, argparse, math
import lib

# Render the Ken Burns motion on a 1.5x canvas, then downscale to 1080p. The downscale
# averages away zoompan's 1px x/y rounding each frame, which is what made the old output
# look like it was shaking. Even dimensions keep libx264 happy.
SUPER_W = (round(lib.W * 1.5) // 2) * 2     # 2880
SUPER_H = (round(lib.H * 1.5) // 2) * 2     # 1620

def kenburns_vf(idx, nframes):
    N = max(nframes, 2)
    t  = f"(on/{N-1})"                               # 0..1 across the clip
    sm = f"({t}*{t}*(3-2*{t}))"                      # smoothstep easing for the zoom
    z0, z1 = (1.08, 1.20) if idx % 2 == 0 else (1.20, 1.08)
    zexpr = f"({z0}+({z1-z0:.4f})*{sm})"
    # Slow pendulum float: a single low-frequency sine sway (half a cycle per clip) with
    # a per-clip phase offset so consecutive images swing in different directions. There
    # is deliberately no high-frequency term, so the result drifts but never shakes.
    phase = (idx % 4) * (math.pi / 2)
    fx = f"(0.5+0.20*sin(PI*{t}+{phase:.5f}))"       # horizontal sway, +/-20% of pan room
    fy = f"(0.5+0.12*cos(PI*{t}+{phase:.5f}))"       # gentler vertical sway
    xexpr = f"(iw-iw/zoom)*{fx}"
    yexpr = f"(ih-ih/zoom)*{fy}"
    return (
        f"scale={SUPER_W}:{SUPER_H}:force_original_aspect_ratio=increase,"
        f"crop={SUPER_W}:{SUPER_H},"
        f"zoompan=z='{zexpr}':x='{xexpr}':y='{yexpr}':d={N}:s={SUPER_W}x{SUPER_H}:fps={lib.FPS},"
        f"scale={lib.W}:{lib.H}:flags=lanczos,setsar=1,format=yuv420p"
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
