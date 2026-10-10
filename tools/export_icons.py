"""Export the selected LocalVoice artwork without redrawing it (requires Pillow)."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "docs" / "branding"
SOURCE = BRANDING / "localvoice-icon.png"


def main():
    with Image.open(SOURCE) as original:
        if original.width != original.height:
            raise ValueError("The selected source must be square")
        if "A" in original.getbands() and original.getchannel("A").getextrema() != (255, 255):
            raise ValueError("The selected app icon must have an opaque background")
        artwork = original.convert("RGB")

    outputs = {}

    def export(path, size):
        path.parent.mkdir(parents=True, exist_ok=True)
        artwork.resize((size, size), Image.Resampling.LANCZOS).save(path)
        outputs[path] = size

    for name, size in {
        "app-icon-1024.png": 1024,
        "favicon-16.png": 16,
        "favicon-32.png": 32,
        "favicon-48.png": 48,
        "apple-touch-icon.png": 180,
    }.items():
        export(BRANDING / name, size)

    ico_sizes = [(n, n) for n in (16, 32, 48, 64)]
    artwork.resize((64, 64), Image.Resampling.LANCZOS).save(
        BRANDING / "favicon.ico", sizes=ico_sizes
    )

    android_res = ROOT / "app" / "android" / "app" / "src" / "main" / "res"
    for density, size in {
        "mdpi": 48,
        "hdpi": 72,
        "xhdpi": 96,
        "xxhdpi": 144,
        "xxxhdpi": 192,
    }.items():
        export(android_res / f"mipmap-{density}" / "ic_launcher.png", size)

    ios_set = ROOT / "app" / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    contents = json.loads((ios_set / "Contents.json").read_text(encoding="utf-8"))
    for entry in contents["images"]:
        width, height = map(float, entry["size"].split("x"))
        scale = float(entry["scale"].removesuffix("x"))
        if width != height or not (width * scale).is_integer():
            raise ValueError(f"Unsupported iOS icon size: {entry}")
        export(ios_set / entry["filename"], int(width * scale))

    for path, size in outputs.items():
        with Image.open(path) as image:
            assert image.size == (size, size), path
            assert image.mode == "RGB", path
            image.verify()
    with Image.open(BRANDING / "favicon.ico") as image:
        assert image.ico.sizes() == set(ico_sizes)
        for size in ico_sizes:
            assert image.ico.getimage(size).size == size
    print(f"Exported and verified {len(outputs)} opaque PNG files and 4 ICO sizes.")


if __name__ == "__main__":
    main()
