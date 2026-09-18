# Removes the files of the HD interface and the HD globe that are no longer part of the hd-render branch
# (they live on the frozen branch hd-ui-globe). Run from E:\OpenXCom:
#   powershell -ExecutionPolicy Bypass -File rollback_ui_globe.ps1
$files = @(
    "src\Engine\HdFont.cpp",
    "src\Engine\HdFont.h",
    "src\Engine\HdUi.cpp",
    "src\Engine\HdUi.h",
    "src\Engine\HdUiArt.cpp",
    "src\Engine\HdUiArt.h",
    "src\Engine\HdUiDraw.cpp",
    "src\Engine\stb_truetype.h",
    "src\Geoscape\HdGlobe.cpp",
    "src\Geoscape\HdGlobe.h",
    "src\Geoscape\HdGlobeOverlay.cpp",
    "src\Geoscape\HdGlobeOverlay.h",
    "tools\hdart\gen_ui.py",
    "tools\hdart\upscale_ui.py",
    "tools\hdglobe\README.md",
    "tools\hdglobe\get_textures.ps1",
    "tools\hdglobe\prep_textures.py",
    "tools\hdui\get_fonts.ps1"
)
foreach ($f in $files) {
    if (Test-Path $f) { Remove-Item -Force $f; Write-Host "removed $f" } else { Write-Host "already gone $f" }
}
foreach ($d in @("tools\hdglobe", "tools\hdui")) {
    if ((Test-Path $d) -and -not (Get-ChildItem -Recurse -File $d)) { Remove-Item -Recurse -Force $d; Write-Host "removed folder $d" }
}
Write-Host "done - now: cd build-release; cmake ..; ninja"
