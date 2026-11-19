"""Public icons for the installable Beta PWA; no stored or user-supplied assets."""
from functools import lru_cache
from io import BytesIO
from PIL import Image, ImageDraw


@lru_cache(maxsize=3)
def render_icon_png(size: int) -> bytes:
    if size not in (180, 192, 512):
        raise ValueError("Unsupported icon size")
    base = 1024
    img = Image.new("RGB", (base, base), (14, 21, 52))
    d = ImageDraw.Draw(img)
    for y in range(base):
        p = y / (base - 1)
        d.line(((0, y), (base, y)), fill=(int(21 + 12 * p), int(98 - 32 * p), int(227 - 38 * p)), width=1)
    d.rounded_rectangle((105, 115, 919, 909), radius=190, fill=(19, 83, 208), outline=(76, 141, 248), width=5)
    # A warehouse roof and a recognisable open-door symbol.
    d.polygon([(244, 452), (508, 267), (772, 452)], fill=(247, 251, 255))
    d.rounded_rectangle((282, 443, 734, 759), radius=40, fill=(247, 251, 255))
    d.rounded_rectangle((406, 548, 610, 759), radius=20, fill=(22, 100, 222))
    d.line([(432, 600), (584, 600)], fill=(218, 237, 255), width=12)
    d.line([(432, 665), (584, 665)], fill=(218, 237, 255), width=12)
    d.ellipse((471, 705, 495, 729), fill=(218, 237, 255))
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    img.save(output, "PNG", optimize=True)
    return output.getvalue()
