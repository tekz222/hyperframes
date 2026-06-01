<#
  hyperframes - one-command story-video build.

  Usage:
    .\build.ps1                 # render the 3-minute (180s) deliverable
    .\build.ps1 -Duration 90    # render a 90s preview
    .\build.ps1 -Full           # composite & encode the WHOLE story (no trim)

  Re-runnable end to end: every step is idempotent (optimized images, narration,
  alignment, dust and per-image clips are all skipped if already present), so a second
  run only redoes the final assembly. Pass -Force to rebuild per-image clips.

  Requires ffmpeg/ffprobe and python (with torch+openai-whisper not needed - captions
  come from captions.json) on PATH.
#>
param(
  [double]$Duration = 180,
  [switch]$Full,
  [switch]$Force
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
Set-Location $PSScriptRoot

python scripts/step1_verify.py;            if ($LASTEXITCODE) { exit 1 }
python scripts/step2_optimize_images.py;   if ($LASTEXITCODE) { exit 1 }
python scripts/step3_build_narration.py;   if ($LASTEXITCODE) { exit 1 }
python scripts/step4_align_captions.py;    if ($LASTEXITCODE) { exit 1 }
python scripts/step5_make_dust.py;         if ($LASTEXITCODE) { exit 1 }

# render the entire Ken Burns timeline (all per-image clips) - the long pole
$clipArgs = @("scripts/step6_render_clips.py")
if ($Force) { $clipArgs += "--force" }
python @clipArgs;                          if ($LASTEXITCODE) { exit 1 }

# assemble + trim
$dur = if ($Full) { 0 } else { $Duration }
python scripts/step7_assemble.py --duration $dur; if ($LASTEXITCODE) { exit 1 }

python scripts/step8_verify.py
