"""Step 7 - assemble the final video.

  intro      animations/* -> zoom/crop out the Veo logo -> concat (keeps own audio)
  body video clips -> eased crossfades -> drifting dust overlay -> burned karaoke
  body audio narration (-16 LUFS) + looped, crossfaded, side-chain-ducked music
  final      concat(intro, body) then trim to --duration (default 180s)

Music never plays over the intro; narration + music start with the image section.
Big filtergraphs are written to *.txt and fed via -filter_complex_script (avoids the
Windows command-line length limit and quoting pitfalls).
"""
from __future__ import annotations
import argparse, json, re, subprocess
import lib
import step6_render_clips as step6

LOGO_ZOOM = 1.18      # zoom-in for intro clips so the bottom-right Veo logo is cropped out
LOOP_XFADE = 3.0      # seconds of crossfade at each music loop seam
MARGIN = 2.0          # extra body seconds so the final trim lands cleanly

def _script(name, text):
    p = lib.WORK / name
    p.write_text(text, encoding="utf-8")
    return p

# ---------------------------------------------------------------- intro
def build_intro():
    clips = sorted(lib.ANIM_DIR.glob("*.*"),
                   key=lambda p: int(re.match(r"(\d+)", p.stem).group(1))
                   if re.match(r"(\d+)", p.stem) else 0)
    zw, zh = (round(lib.W * LOGO_ZOOM) // 2) * 2, (round(lib.H * LOGO_ZOOM) // 2) * 2
    parts, maps = [], []
    for i, _ in enumerate(clips):
        parts.append(
            f"[{i}:v]scale={zw}:{zh},crop={lib.W}:{lib.H}:0:0,setsar=1,"
            f"fps={lib.FPS},format=yuv420p[v{i}];"
            f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}];")
        maps.append(f"[v{i}][a{i}]")
    graph = "".join(parts) + "".join(maps) + f"concat=n={len(clips)}:v=1:a=1[v][a]"
    sf = _script("fc_intro.txt", graph)
    out = lib.WORK / "intro.mp4"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for c in clips:
        cmd += ["-i", c]
    cmd += ["-filter_complex_script", sf, "-map", "[v]", "-map", "[a]",
            "-r", str(lib.FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out]
    lib.run(cmd)
    return out

# ---------------------------------------------------------------- body video
def build_body_video(M, body_dur, plan):
    g = []
    for k in range(M):
        g.append(f"[{k}:v]settb=AVTB,fps={lib.FPS},setsar=1,format=yuv420p[c{k}];")
    prev = "c0"
    for k in range(1, M):
        out = f"x{k}"
        g.append(f"[{prev}][c{k}]xfade=transition=fade:"
                 f"duration={plan['c'][k]}:offset={plan['offsets'][k]}[{out}];")
        prev = out
    di, dj = M, M + 1   # dust input indices
    g.append(f"[{di}:v]scale=2400:1350,format=rgba[dA];")
    g.append(f"[{dj}:v]scale=2400:1350,format=rgba[dB];")
    g.append(f"[{prev}][dA]overlay=x='-(mod(t*6,480))':y='-(mod(t*3.5,270))':"
             f"shortest=1[o1];")
    g.append(f"[o1][dB]overlay=x='-(mod(t*4,480))':y='-(mod(t*5,270))':shortest=1[o2];")
    # fontsdir points libass at the bundled Montserrat Black, so captions render the
    # same on any machine even if the font isn't installed system-wide.
    g.append("[o2]ass=f=work/captions.ass:fontsdir=assets/fonts[vout]")
    sf = _script("fc_body_video.txt", "".join(g))

    out = lib.WORK / "body_video.mp4"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats"]
    for k in range(M):
        cmd += ["-i", lib.CLIPS / f"{k:04d}.mp4"]
    cmd += ["-loop", "1", "-i", lib.WORK / "dust1.png",
            "-loop", "1", "-i", lib.WORK / "dust2.png",
            "-filter_complex_script", sf, "-map", "[vout]",
            "-t", f"{body_dur:.3f}", "-r", str(lib.FPS),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", out]
    lib.run(cmd)
    return out

# ---------------------------------------------------------------- body audio
def build_body_audio(body_dur):
    music = sorted(lib.MUSIC_DIR.glob("*.*"))[0]
    mlen = lib.probe_duration(music)
    unit = max(1.0, mlen - LOOP_XFADE)
    K = max(1, int(body_dur // unit) + 2)        # music copies for the crossfaded loop

    g = []
    if K == 1:
        g.append("[1:a]anull[bed];")
    else:
        g.append(f"[1:a][2:a]acrossfade=d={LOOP_XFADE}:c1=tri:c2=tri[m1];")
        for j in range(2, K):
            g.append(f"[m{j-1}][{j+1}:a]acrossfade=d={LOOP_XFADE}:c1=tri:c2=tri[m{j}];")
        g.append(f"[m{K-1}]anull[bed];")
    g.append(f"[bed]atrim=0:{body_dur:.3f},asetpts=N/SR/TB,volume={lib.MUSIC_GAIN}[bedq];")
    g.append("[0:a]asplit=2[nmix][nkey];")
    g.append("[bedq][nkey]sidechaincompress=threshold=0.02:ratio=8:attack=5:"
             "release=350[duck];")
    g.append("[nmix][duck]amix=inputs=2:duration=first:normalize=0[mx];")
    g.append("[mx]alimiter=limit=0.97[aout]")
    sf = _script("fc_body_audio.txt", "".join(g))

    out = lib.WORK / "body_audio.m4a"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", lib.WORK / "narration.wav"]
    for _ in range(K):
        cmd += ["-i", music]
    cmd += ["-filter_complex_script", sf, "-map", "[aout]",
            "-t", f"{body_dur:.3f}", "-c:a", "aac", "-b:a", "192k", out]
    lib.run(cmd)
    return out

# ---------------------------------------------------------------- mux + final
def mux_body(v, a):
    out = lib.WORK / "body.mp4"
    lib.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", v, "-i", a, "-c:v", "copy", "-c:a", "copy", "-shortest", out])
    return out

def assemble_final(intro, body, duration):
    out = lib.OUTPUT / "story_video.mp4"
    graph = "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]"
    sf = _script("fc_final.txt", graph)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats",
           "-i", intro, "-i", body, "-filter_complex_script", sf,
           "-map", "[v]", "-map", "[a]"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-r", str(lib.FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", out]
    lib.run(cmd)
    return out

# ---------------------------------------------------------------- orchestration
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=180.0,
                    help="final trim length in seconds (default 180; 0 = whole story)")
    args = ap.parse_args()
    lib.ensure_dirs()
    print("=== STEP 7: assemble ===")

    timeline = json.loads((lib.WORK / "timeline.json").read_text(encoding="utf-8"))
    plan = lib.render_plan(timeline)
    n = len(timeline)

    print("- intro")
    intro = build_intro()
    intro_dur = lib.probe_duration(intro)
    print(f"  intro duration: {intro_dur:.2f}s")

    full = (args.duration == 0)
    if full:
        body_dur = plan["total"]
        M = n
    else:
        body_dur = min(plan["total"], args.duration - intro_dur + MARGIN)
        M = next((k for k in range(n) if plan["starts"][k] >= body_dur), n)
        M = min(M + 1, n)
    print(f"- body: {M} clips, {body_dur:.2f}s "
          f"(final target {'whole story' if full else str(args.duration)+'s'})")

    # ensure the clips we need exist
    missing = [k for k in range(M) if not (lib.CLIPS / f"{k:04d}.mp4").exists()]
    if missing:
        print(f"  rendering {len(missing)} missing clips first...")
        for k in missing:
            step6.render_one(k, timeline[k], plan["L"][k])

    print("- body video (crossfades + dust + karaoke)")
    bv = build_body_video(M, body_dur, plan)
    print("- body audio (narration + ducked looped music)")
    ba = build_body_audio(body_dur)
    print("- mux body")
    body = mux_body(bv, ba)
    print("- final concat + trim")
    out = assemble_final(intro, body, None if full else args.duration)
    print(f"\nDONE -> {out}  ({lib.probe_duration(out):.2f}s)")

if __name__ == "__main__":
    main()
