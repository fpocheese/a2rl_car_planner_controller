"""Replace only the Visio-downsampled blocking panel; keep PDF drawing streams."""
from io import BytesIO
from pathlib import Path
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject
from reportlab.pdfgen import canvas

source, png, output = map(Path, sys.argv[1:])
buffer = BytesIO()
panel = canvas.Canvas(buffer, pagesize=(4204, 2125))
panel.drawImage(str(png), 0, 0, width=4204, height=2125, mask="auto")
panel.showPage()
panel.save()
image_pdf = PdfReader(buffer)
replacement = next(
    ref.get_object()
    for ref in image_pdf.pages[0]["/Resources"]["/XObject"].values()
    if ref.get_object().get("/Subtype") == "/Image"
)
assert (replacement["/Width"], replacement["/Height"]) == (4204, 2125)

writer = PdfWriter(clone_from=source)
seen, targets = set(), []

def walk(obj):
    resources = obj.get("/Resources", {})
    xobjects = resources.get("/XObject", {})
    for name, reference in xobjects.items():
        child = reference.get_object()
        if child.get("/Subtype") == "/Image":
            if (child.get("/Width"), child.get("/Height")) == (394, 199):
                targets.append((xobjects, name))
        elif reference.idnum not in seen:
            seen.add(reference.idnum)
            walk(child)

walk(writer.pages[0])
assert len(targets) == 1, f"Expected one blocking panel, found {len(targets)}"
container, name = targets[0]
new_image = replacement.clone(writer)
# Visio places its JPEG in a vertically reflected image coordinate system.
# Counter-reflect a unit-square PDF form, keeping the PNG pixels untouched.
form = DecodedStreamObject()
form.set_data(b"q 1 0 0 -1 0 1 cm /HiRes Do Q\n")
form.update({
    NameObject("/Type"): NameObject("/XObject"),
    NameObject("/Subtype"): NameObject("/Form"),
    NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 1, 1)]),
    NameObject("/Resources"): DictionaryObject({
        NameObject("/XObject"): DictionaryObject({
            NameObject("/HiRes"): new_image.indirect_reference,
        }),
    }),
})
container[name] = writer._add_object(form)
writer.write(output)
print(f"Replaced {name}: 394 x 199 JPEG -> 4204 x 2125 lossless image")
