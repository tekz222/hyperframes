"""Step 5 - generate soft dust-particle overlay textures.

Two static dot fields (different seeds/densities) are produced; the assembly step
drifts them slowly at different speeds (parallax) and blends them over the image
section with 'lighten' so only the motes show. Pure ffmpeg, fully reproducible.
"""
from __future__ import annotations
import lib

# low-res noise -> high threshold -> few soft pixels -> upscale + blur = soft motes,
# emitted as white RGBA where alpha = mote intensity (so overlay keeps base colours).
def make(seed, thresh, sigma, alpha, out, gen_w=170, gen_h=96):
    lib.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={gen_w}x{gen_h}",
        "-f", "lavfi", "-i", "color=c=white:s=2400x1350",
        "-frames:v", "1",
        "-filter_complex",
        (f"[0:v]format=gray,noise=alls=100:all_seed={seed}:allf=u,"
         f"lutyuv=y='if(gt(val,{thresh}),val,0)',"
         f"scale=2400:1350:flags=bicubic,gblur=sigma={sigma},"
         f"lutyuv=y=val*{alpha}[a];"
         f"[1:v]format=rgba[w];[w][a]alphamerge[out]"),
        "-map", "[out]", out,
    ])

def avg_luma(path):
    import subprocess
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
         "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"], capture_output=True, text=True).stderr
    import re
    m = re.findall(r"YAVG=([\d.]+)", out)
    return float(m[-1]) if m else -1.0

def main():
    lib.ensure_dirs()
    print("=== STEP 5: dust overlay ===")
    d1 = lib.WORK / "dust1.png"
    d2 = lib.WORK / "dust2.png"
    # lower thresholds let more motes through; higher alpha makes them clearly visible
    # (the old values were so sparse/faint the dust was easy to miss). Two layers at
    # different densities are drifted at different speeds in step 7 for parallax depth.
    make(seed=11, thresh=92, sigma=2.6, alpha=0.95, out=d1, gen_w=210, gen_h=118)
    make(seed=47, thresh=93, sigma=1.9, alpha=0.70, out=d2, gen_w=195, gen_h=110)
    for d in (d1, d2):
        print(f"  {d.name}: avg luma {avg_luma(d):.2f}")

if __name__ == "__main__":
    main()
