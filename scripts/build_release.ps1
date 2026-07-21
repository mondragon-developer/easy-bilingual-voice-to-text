# Builds both Windows release zips into <repo>/release.
# Used locally and by .github/workflows/release.yml (CI).
#   SpeechToText-Windows-CPU.zip  - no CUDA DLLs, runs anywhere
#   SpeechToText-Windows-GPU.zip  - bundles cuBLAS/cuDNN for NVIDIA cards
#
# -Stage build : PyInstaller only (CI signs the exe after this)
# -Stage zip   : zip the (possibly signed) build into both release zips
# -Stage all   : everything (default; local unsigned builds)

param([ValidateSet("all", "build", "zip")] [string]$Stage = "all")

$ErrorActionPreference = "Stop"
$proj = Split-Path $PSScriptRoot -Parent
$out = Join-Path $proj "release"
Set-Location $proj

if ($Stage -in @("all", "build")) {
    python -m PyInstaller --noconfirm --clean --windowed --name SpeechToText `
      --icon "$proj\assets\icon.ico" `
      --add-data "$proj\assets;assets" `
      --collect-all customtkinter `
      --collect-all faster_whisper `
      --collect-all sounddevice `
      main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}

if ($Stage -eq "build") { Write-Output "BUILD_STAGE_DONE"; exit 0 }

New-Item -ItemType Directory -Force $out | Out-Null

function New-Zip($src, $dest) {
    if (Test-Path $dest) { Remove-Item $dest }
    if (Get-Command 7z -ErrorAction SilentlyContinue) {
        & 7z a -tzip -mx=5 $dest $src | Out-Null   # much faster than Compress-Archive
        if ($LASTEXITCODE -ne 0) { throw "7z failed for $dest" }
    } else {
        Compress-Archive -Path $src -DestinationPath $dest -CompressionLevel Optimal
    }
}

Write-Output "Zipping CPU build..."
New-Zip "$proj\dist\SpeechToText" "$out\SpeechToText-Windows-CPU.zip"

Write-Output "Adding NVIDIA CUDA DLLs for the GPU build..."
$nvidiaDir = python -c "import nvidia; print(list(nvidia.__path__)[0])"
foreach ($libdir in (Get-ChildItem "$nvidiaDir\*\bin" -Directory -ErrorAction SilentlyContinue)) {
    Copy-Item "$($libdir.FullName)\*.dll" "$proj\dist\SpeechToText\_internal" -Force
}

Write-Output "Zipping GPU build..."
New-Zip "$proj\dist\SpeechToText" "$out\SpeechToText-Windows-GPU.zip"

Get-ChildItem $out | ForEach-Object { Write-Output ("ASSET: " + $_.Name + "  " + [math]::Round($_.Length/1MB) + " MB") }
Write-Output "BUILD_DONE"
