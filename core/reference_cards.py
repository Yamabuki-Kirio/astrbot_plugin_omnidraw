"""Render saved reference images into a local contact sheet."""

import io


def render_reference_card(images):
    from PIL import Image, ImageDraw, ImageOps

    columns = min(3, len(images))
    tile, gap = 248, 16
    rows = (len(images) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * tile + (columns + 1) * gap, rows * (tile + 23) + (rows + 1) * gap), "#10141f")
    draw = ImageDraw.Draw(canvas)
    for index, (_, payload) in enumerate(images):
        left = gap + (index % columns) * (tile + gap)
        top = gap + (index // columns) * (tile + 23 + gap)
        draw.rounded_rectangle((left, top, left + tile, top + tile + 22), radius=10, fill="#222b3a")
        with Image.open(io.BytesIO(payload)) as source:
            if source.width * source.height > 24_000_000:
                raise ValueError("参考图像素过大，无法生成预览")
            source.draft("RGB", (tile, tile))
            preview = ImageOps.exif_transpose(source)
            preview.thumbnail((tile - 12, tile - 12), Image.Resampling.LANCZOS)
            preview = preview.convert("RGBA")
            canvas.paste(preview, (left + (tile - preview.width) // 2, top + (tile - preview.height) // 2), preview)
        draw.text((left + 10, top + tile + 3), f"{index + 1:02d}", fill="#dbeafe")
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()
