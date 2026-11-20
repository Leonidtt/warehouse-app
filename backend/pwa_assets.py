"""Main PWA icon chosen by the owner: captain hat, ships, warehouse and spotlights."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image

@lru_cache(maxsize=3)
def render_icon_png(size:int)->bytes:
    if size not in (180,192,512):
        raise ValueError("Unsupported PWA icon size")
    with Image.open(Path(__file__).with_name("pwa_logo_source.webp")) as source:
        icon=source.convert("RGB").resize((size,size),Image.Resampling.LANCZOS)
    output=BytesIO()
    icon.save(output,format="PNG",optimize=True)
    return output.getvalue()
