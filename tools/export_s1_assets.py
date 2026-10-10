"""Slice generated S1 atlases; preserve their alpha and artwork (Pillow + NumPy)."""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'ui' / 'asset-production' / 's1'
DEST = ROOT / 'app' / 'assets' / 's1'


def cuts(mask, count, axis):
    # Generated atlases can have slightly uneven whitespace. Cut at the closest
    # empty gutter, rather than clipping an icon at a nominal cell boundary.
    projection = mask.sum(axis=1 if axis == 0 else 0)
    length = len(projection)
    result = [0]
    step = length / count
    for index in range(1, count):
        nominal = index * step
        lo, hi = round(nominal - step * 0.28), round(nominal + step * 0.28)
        choices = range(max(lo, result[-1] + 1), min(hi + 1, length))
        result.append(min(choices, key=lambda p: (projection[max(0, p - 2):p + 3].sum(), abs(p - nominal))))
    return result + [length]


def main():
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    exported = []
    for job in manifest['jobs']:
        atlas = Image.open(SOURCE / job['file'])
        if atlas.mode != 'RGBA' or atlas.getchannel('A').getextrema()[0] != 0:
            raise ValueError(f"Real alpha required: {job['file']}")
        mask = np.array(atlas.getchannel('A')) > 24
        rows, cols = cuts(mask, job['rows'], 0), cuts(mask, job['cols'], 1)
        for index, item in enumerate(job['items']):
            row, col = divmod(index, job['cols'])
            tile = atlas.crop((cols[col], rows[row], cols[col + 1], rows[row + 1]))
            alpha = np.array(tile.getchannel('A'))
            occupied = alpha > 24
            if not occupied.any():
                raise ValueError(f"Empty slot: {item['key']}")
            # Strong pixels on an internal cut mean the atlas did not leave a gutter.
            if ((col and occupied[:, 0].any()) or
                (col < job['cols'] - 1 and occupied[:, -1].any()) or
                (row and occupied[0, :].any()) or
                (row < job['rows'] - 1 and occupied[-1, :].any())):
                raise ValueError(f"Subject touches a cut: {item['key']}")
            ys, xs = np.where(alpha > 8)
            bounds = (max(0, int(xs.min()) - 2), max(0, int(ys.min()) - 2),
                      min(tile.width, int(xs.max()) + 3), min(tile.height, int(ys.max()) + 3))
            subject = tile.crop(bounds)
            target = (256, 256) if job['kind'] == 'icons' else (640, 480)
            margin = 20 if job['kind'] == 'icons' else 12
            subject.thumbnail((target[0] - 2 * margin, target[1] - 2 * margin), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', target)
            canvas.alpha_composite(subject, ((target[0] - subject.width) // 2,
                                             (target[1] - subject.height) // 2))
            folder = DEST / job['kind']
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (item['key'] + '.png')
            canvas.save(path, optimize=True)
            assert canvas.getchannel('A').getextrema()[0] == 0
            assert all(canvas.getpixel(p)[3] == 0 for p in
                       ((0, 0), (0, target[1] - 1), (target[0] - 1, 0), (target[0] - 1, target[1] - 1)))
            exported.append({'file': str(path.relative_to(ROOT)).replace('\\', '/'),
                             'source': job['file'], 'slot': index, 'bounds': bounds})

    (SOURCE / 'exports.json').write_text(json.dumps(exported, ensure_ascii=False, indent=2), encoding='utf-8')
    qa = SOURCE / 'qa'
    qa.mkdir(exist_ok=True)
    for kind, cell, columns in [('icons', (112, 132), 6), ('illustrations', (320, 260), 3)]:
        paths = [ROOT / e['file'] for e in exported if f'/{kind}/' in e['file']]
        rows = (len(paths) + columns - 1) // columns
        preview = Image.new('RGB', (cell[0] * columns, cell[1] * rows), '#FBFAF5')
        draw = ImageDraw.Draw(preview)
        for i, path in enumerate(paths):
            art = Image.open(path)
            art.thumbnail((cell[0] - 24, cell[1] - 40), Image.Resampling.LANCZOS)
            x, y = (i % columns) * cell[0], (i // columns) * cell[1]
            preview.paste(art, (x + (cell[0] - art.width) // 2, y + 8), art)
            draw.text((x + 4, y + cell[1] - 24), path.stem, fill='#075747')
        preview.save(qa / f'{kind}-export-preview.png')
    print(f'Exported {len(exported)} assets with transparent corners and no cut subjects.')


if __name__ == '__main__':
    main()
