"""Check native PNG payloads from test_decorated_backgrounds.cjs, without USB."""
from io import BytesIO
import json
import os
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_calibration import prepare_panel_image
from server import encode_panel_png

folder = Path(os.environ.get('TURZX_VERIFY_OUTPUT', 'runtime/decor-backgrounds'))
rows = []
for path in sorted(folder.glob('*-[HV].png')):
    with Image.open(path) as source:
        image = prepare_panel_image(source, 270 if source.width > source.height else 0, 'rgb')
    payload, step = encode_panel_png(image)
    assert image.size == (720, 1280)
    assert image.getchannel('A').getextrema() == (255, 255)
    assert payload[25] == 6
    rows.append({'name': path.name, 'bytes': len(payload), 'quantization_step': step})
assert rows, 'Run node tests/test_decorated_backgrounds.cjs first'
(folder / 'encoding.json').write_text(json.dumps(rows, indent=2))
maximum = max(rows, key=lambda row: row['bytes'])
print(f"{len(rows)} RGBA frames, largest: {maximum}")
assert all(row['bytes'] < 1024 * 1024 for row in rows), [row for row in rows if row['bytes'] >= 1024 * 1024]
