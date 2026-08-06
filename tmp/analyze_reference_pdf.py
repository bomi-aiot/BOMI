from pathlib import Path
import json

import fitz
from PIL import Image, ImageDraw, ImageFont


SOURCE = Path(r"C:\Users\SSAFY\Downloads\자율PJT_해피너스_최종발표피피티자료.pdf")
OUT_DIR = Path(r"C:\BOMI\tmp\happynurse_ref")
OUT_DIR.mkdir(parents=True, exist_ok=True)

doc = fitz.open(SOURCE)
records = []
thumbs = []

for index, page in enumerate(doc):
    rect = page.rect
    zoom = min(480 / rect.width, 270 / rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    mode = "RGB" if pix.n == 3 else "RGBA"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("RGB")
    thumbs.append(image)
    records.append({
        "page": index + 1,
        "width": rect.width,
        "height": rect.height,
        "text": " ".join(page.get_text("text").split()),
    })

(OUT_DIR / "text_by_page.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
)

font = ImageFont.load_default()
cols = 5
cell_w, cell_h = 500, 312
for start in range(0, len(thumbs), 40):
    batch = thumbs[start : start + 40]
    rows = (len(batch) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#161616")
    draw = ImageDraw.Draw(sheet)
    for offset, thumb in enumerate(batch):
        x = (offset % cols) * cell_w
        y = (offset // cols) * cell_h
        tx = x + (cell_w - thumb.width) // 2
        ty = y + 26 + (cell_h - 32 - thumb.height) // 2
        sheet.paste(thumb, (tx, ty))
        draw.text((x + 10, y + 7), f"{start + offset + 1:03d}", fill="white", font=font)
    end = start + len(batch)
    sheet.save(OUT_DIR / f"contact_{start + 1:03d}_{end:03d}.jpg", quality=90)

for page_number in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 35, 40,
                    45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115]:
    page = doc[page_number - 1]
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pix.save(OUT_DIR / f"page_{page_number:03d}.png")

print(json.dumps({"pages": len(doc), "out_dir": str(OUT_DIR)}, ensure_ascii=False))
