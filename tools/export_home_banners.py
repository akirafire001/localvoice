"""Export mobile-sized WebP encodings without changing the original PNG artwork."""

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs/ui/asset-production/home-banners'
DEST = ROOT / 'app/assets/s1/home_banners'


def main():
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    items = manifest['retained'] + manifest['jobs']
    if len(items) != 22 or len({item['file'] for item in items}) != 22:
        raise ValueError('Exactly 22 unique source banners are required')
    DEST.mkdir(parents=True, exist_ok=True)
    exports = []
    for item in items:
        source = SOURCE / 'originals' / item['file']
        with Image.open(source) as image:
            if image.size != (1774, 887):
                raise ValueError(f'Unexpected dimensions: {source}')
            if 'A' in image.getbands() and image.getchannel('A').getextrema()[0] != 255:
                raise ValueError(f'Opaque artwork required: {source}')
            destination = DEST / (source.stem + '.webp')
            image.convert('RGB').save(destination, 'WEBP', quality=92, method=6)
        with Image.open(destination) as exported:
            if exported.size != (1774, 887):
                raise ValueError(f'Unexpected export dimensions: {destination}')
        exports.append({
            'source': source.relative_to(ROOT).as_posix(),
            'file': destination.relative_to(ROOT).as_posix(),
            'label': item['label'],
            'country': item.get('country'),
            'width': 1774,
            'height': 887,
            'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            'source_bytes': source.stat().st_size,
            'bytes': destination.stat().st_size,
            'encoding': 'WebP quality 92, method 6',
        })
    (SOURCE / 'exports.json').write_text(
        json.dumps(exports, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    original_bytes = sum(item['source_bytes'] for item in exports)
    runtime_bytes = sum(item['bytes'] for item in exports)
    print(f'{len(exports)} banners, 1774x887: {original_bytes / 1024**2:.2f} MiB PNG -> '
          f'{runtime_bytes / 1024**2:.2f} MiB WebP ({100 * (1 - runtime_bytes / original_bytes):.1f}% smaller)')


if __name__ == '__main__':
    main()
