"""Export the generated wallpapers at native display sizes without palette PNGs."""

import argparse
from io import BytesIO
from pathlib import Path
import shutil

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[3]
DESTINATION = ROOT / "web" / "assets" / "claude"
DECORATED_BACKGROUNDS = ("floral", "celestial", "atelier", "botanical", "paperland", "glasswave")
DECORATED_ORIGINALS = ("stand", "thought", "greeting")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v1", "v2", "v3", "v3-thought", "v3-greeting",
                                             *(f"v4-{key}" for key in DECORATED_BACKGROUNDS),
                                             *(f"v3-decorated-{key}" for key in DECORATED_ORIGINALS)), default="v3")
    parser.add_argument("--collection-dir", type=Path,
                        help="Import and export all six decorated backgrounds named <id>.png")
    parser.add_argument("--originals-dir", type=Path,
                        help="Import decorated edits of stand, thought and greeting")
    parser.add_argument("--portraits-dir", type=Path,
                        help="Import nine dedicated portrait artworks named <id>.png")
    args = parser.parse_args()
    if args.portraits_dir:
        sources = {key: args.portraits_dir / f"{key}.png"
                   for key in (*DECORATED_ORIGINALS, *DECORATED_BACKGROUNDS)}
        missing = [str(path) for path in sources.values() if not path.is_file()]
        if missing:
            parser.error("Missing portrait backgrounds: " + ", ".join(missing))
        for key, source in sources.items():
            version = f"v3-decorated-{key}" if key in DECORATED_ORIGINALS else f"v4-{key}"
            destination = Path(__file__).with_name(f"claude-{version}-portrait-original.png")
            shutil.copyfile(source, destination)
            export_version(version, only_orientation="portrait")
    elif args.collection_dir or args.originals_dir:
        sources = {}
        if args.collection_dir:
            sources.update({f"v4-{key}": args.collection_dir / f"{key}.png" for key in DECORATED_BACKGROUNDS})
        if args.originals_dir:
            sources.update({f"v3-decorated-{key}": args.originals_dir / f"{key}.png" for key in DECORATED_ORIGINALS})
        missing = [str(path) for path in sources.values() if not path.is_file()]
        if missing:
            parser.error("Missing generated backgrounds: " + ", ".join(missing))
        for version, source in sources.items():
            destination = Path(__file__).with_name(f"claude-{version}-landscape-original.png")
            shutil.copyfile(source, destination)
            export_version(version)
    else:
        export_version(args.version)


def export_version(version: str, only_orientation=None) -> None:
    prefix = f"claude-{version}" if version != "v1" else "claude"
    from_landscape = version.startswith(("v3", "v4"))
    decorated = version.startswith(("v4-", "v3-decorated-"))
    DESTINATION.mkdir(parents=True, exist_ok=True)
    quantize_channel = [min(255, ((value + 4) // 8) * 8) for value in range(256)]
    sizes = (("landscape", (1280, 720)), ("portrait", (720, 1280)))
    for orientation, size in sizes:
        if only_orientation and orientation != only_orientation:
            continue
        source_orientation = "landscape" if from_landscape and not decorated else orientation
        source = Path(__file__).with_name(f"{prefix}-{source_orientation}-original.png")
        if decorated and orientation == "portrait" and not source.exists() and not only_orientation:
            continue
        with Image.open(source) as original:
            if from_landscape and not decorated and orientation == "portrait":
                picture = ImageOps.fit(original.convert("RGB"), size, Image.Resampling.LANCZOS,
                                       centering=(1, .5))
            else:
                picture = original.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        if not from_landscape:
            picture = picture.point(quantize_channel * 3)
        if decorated:
            # Bound per-channel error while retaining sharp illustration edges.
            # Only display derivatives change; originals stay untouched. The
            # output remains full RGBA (not an indexed/palette PNG).
            for step in (1, 2, 3, 4, 5, 6, 8):
                lookup = [min(255, round(value / step) * step) for value in range(256)]
                candidate = picture if step == 1 else picture.point(lookup * 3)
                encoded = BytesIO()
                native = candidate.convert("RGBA")
                if orientation == "landscape":
                    native = native.rotate(270, expand=True)
                native.save(encoded, "PNG", compress_level=9)
                if len(encoded.getvalue()) <= 850_000:
                    picture = candidate
                    print(f"{version} {orientation}: channel step {step}, max error {step // 2}, native bytes {len(encoded.getvalue())}")
                    break
            else:
                raise ValueError(f"{version} {orientation} still exceeds its image budget")
        picture = picture.convert("RGBA")
        destination = DESTINATION / f"{prefix}-{orientation}.png"
        temporary = destination.with_suffix(".tmp")
        picture.save(temporary, "PNG", compress_level=9)
        temporary.replace(destination)
        with Image.open(destination) as saved:
            assert saved.size == size
            assert saved.mode == "RGBA"
            assert saved.getchannel("A").getextrema() == (255, 255)
        print(f"{destination}: {destination.stat().st_size} bytes, RGBA {size[0]}x{size[1]}")
        if decorated and orientation == "landscape":
            thumbnail = picture.convert("RGB")
            thumbnail.thumbnail((320, 180), Image.Resampling.LANCZOS)
            key = version.removeprefix("v3-decorated-").removeprefix("v4-")
            destination = DESTINATION / f"{key}-thumb.webp"
            temporary = destination.with_suffix(".tmp")
            thumbnail.save(temporary, "WEBP", quality=85, method=6)
            temporary.replace(destination)


if __name__ == "__main__":
    main()
