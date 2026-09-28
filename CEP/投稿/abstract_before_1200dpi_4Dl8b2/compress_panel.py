"""Resample only the 4204x2125 abstract panel; retain PDF vectors and geometry."""
from pathlib import Path
import sys
import zlib
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject

source, output = map(Path, sys.argv[1:])
writer = PdfWriter(clone_from=str(source))
seen, targets = set(), []

def walk(obj):
    for ref in obj.get('/Resources', {}).get('/XObject', {}).values():
        child = ref.get_object()
        identity = id(child)
        if identity in seen:
            continue
        seen.add(identity)
        if child.get('/Subtype') == '/Image':
            if (child.get('/Width'), child.get('/Height')) == (4204, 2125):
                targets.append(child)
        elif child.get('/Subtype') == '/Form':
            walk(child)

walk(writer.pages[0])
assert len(targets) == 1, f'Expected one target, found {len(targets)}'
target = targets[0]
assert target['/ColorSpace'] == '/DeviceRGB' and target['/BitsPerComponent'] == 8
original = Image.frombytes('RGB', (4204, 2125), target.get_data())
# The panel is 4085 dpi at its 3.5-inch abstract placement in the manuscript.
size = (1235, round(2125 * 1235 / 4204))

def replace_pixels(stream, pixels):
    stream._data = zlib.compress(pixels.tobytes(), 9)
    stream[NameObject('/Filter')] = NameObject('/FlateDecode')
    stream.pop('/DecodeParms', None)
    stream[NameObject('/Width')] = NumberObject(pixels.width)
    stream[NameObject('/Height')] = NumberObject(pixels.height)
    if hasattr(stream, 'decoded_self'):
        stream.decoded_self = None

replace_pixels(target, original.resize(size, Image.LANCZOS))
if '/SMask' in target:
    mask = target['/SMask'].get_object()
    alpha = Image.frombytes('L', (4204, 2125), mask.get_data())
    replace_pixels(mask, alpha.resize(size, Image.LANCZOS))
writer.write(str(output))

before, after = PdfReader(str(source)), PdfReader(str(output))
assert before.pages[0].mediabox == after.pages[0].mediabox
assert before.pages[0].cropbox == after.pages[0].cropbox
assert before.pages[0].get_contents().get_data() == after.pages[0].get_contents().get_data()
assert before.pages[0].extract_text() == after.pages[0].extract_text()
print(f'Panel: 4204x2125 -> {size[0]}x{size[1]}; vector drawing and page geometry retained.')
print(f'Abstract PDF: {source.stat().st_size} -> {output.stat().st_size} bytes')
