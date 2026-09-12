import os
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_REGULAR = os.path.join(FONT_DIR, "NotoSans-Regular.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "NotoSans-Bold.ttf")

COLORS = {
    "bg": "#1a1a2e",
    "header_bg": "#16213e",
    "row_even": "#0f3460",
    "row_odd": "#162040",
    "text": "#e6e6e6",
    "accent": "#e94560",
    "border": "#533483",
    "day_header": "#533483",
}

ITEM_PADDING = 10
LINE_HEIGHT = 18


def get_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(path, size)


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def draw_rounded_rect(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def generate_schedule_image(week_schedule, week_number, weekdays):
    cell_w = 200
    cell_h = 48
    header_h = 56
    day_header_h = 44
    padding = 20
    num_cols = 6
    num_rows = 8

    img_w = cell_w * num_cols + padding * 2
    img_h = header_h + day_header_h + cell_h * num_rows + padding * 2

    img = Image.new("RGB", (img_w, img_h), COLORS["bg"])
    draw = ImageDraw.Draw(img)

    font_title = get_font(22, bold=True)
    font_header = get_font(16, bold=True)
    font_cell = get_font(15)
    font_num = get_font(14, bold=True)

    x_start = padding
    y = padding

    draw_rounded_rect(draw, (x_start, y, x_start + img_w - padding * 2, y + header_h), 10, COLORS["header_bg"])
    title = f"Расписание - Неделя {week_number}"
    tw = text_width(draw, title, font_title)
    draw.text((x_start + (img_w - padding * 2 - tw) // 2, y + 14), title, fill=COLORS["text"], font=font_title)
    y += header_h + 4

    col_x = [x_start + i * cell_w for i in range(num_cols)]

    for i, day in enumerate(weekdays):
        draw_rounded_rect(draw, (col_x[i], y, col_x[i] + cell_w - 4, y + day_header_h), 8, COLORS["day_header"])
        dw = text_width(draw, day, font_header)
        draw.text((col_x[i] + (cell_w - 4 - dw) // 2, y + 12), day, fill=COLORS["text"], font=font_header)
    y += day_header_h + 4

    for row in range(num_rows):
        fill = COLORS["row_even"] if row % 2 == 0 else COLORS["row_odd"]
        for col in range(num_cols):
            x = col_x[col]
            draw_rounded_rect(draw, (x, y, x + cell_w - 4, y + cell_h - 2), 6, fill)

            num_text = str(row + 1)
            draw.text((x + 8, y + 14), num_text, fill=COLORS["accent"], font=font_num)

            subjects = week_schedule.get(col, [])
            if row < len(subjects):
                subj = subjects[row]
                draw.text((x + 28, y + 14), subj, fill=COLORS["text"], font=font_cell)
        y += cell_h

    return img


def generate_hw_image(hw_by_day, title="Д/з на неделю"):
    cell_w = 280
    header_h = 50
    day_header_h = 42
    padding = 20

    font_title = get_font(20, bold=True)
    font_header = get_font(15, bold=True)
    font_cell = get_font(13)

    cleaned_title = title.replace("📅 ", "").replace("📚 ", "")

    num_cols = len(hw_by_day) if hw_by_day else 1

    filtered_by_day = {}
    for day_key, items in hw_by_day.items():
        cleaned = []
        for hw in items:
            task = hw["task"]
            if task == "—" or "отсутствует" in task.lower():
                cleaned.append({"subject": hw["subject"], "task": "—"})
            else:
                cleaned.append(hw)
        filtered_by_day[day_key] = cleaned

    if not filtered_by_day:
        filtered_by_day = hw_by_day

    temp_img = Image.new("RGB", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)

    col_lines = {}
    for col, (day_key, items) in enumerate(filtered_by_day.items()):
        lines_per_item = []
        for hw in items:
            display = f"{hw['subject']}: {hw['task']}"
            lines = wrap_text(temp_draw, display, font_cell, cell_w - ITEM_PADDING * 2)
            lines_per_item.append(lines)
        col_lines[col] = lines_per_item

    max_items = max((len(v) for v in filtered_by_day.values()), default=0)
    max_lines_per_row = []
    for row in range(max_items):
        mx = 1
        for col in range(num_cols):
            items = list(filtered_by_day.values())[col]
            if row < len(items):
                mx = max(mx, len(col_lines[col][row]))
        max_lines_per_row.append(mx)

    total_content_h = 0
    for lines_count in max_lines_per_row:
        total_content_h += lines_count * LINE_HEIGHT + ITEM_PADDING * 2

    img_w = cell_w * num_cols + padding * 2
    img_h = header_h + 4 + day_header_h + 4 + total_content_h + padding

    img = Image.new("RGB", (img_w, img_h), COLORS["bg"])
    draw = ImageDraw.Draw(img)

    x_start = padding
    y = padding

    draw_rounded_rect(draw, (x_start, y, x_start + img_w - padding * 2, y + header_h), 10, COLORS["header_bg"])
    tw = text_width(draw, cleaned_title, font_title)
    draw.text((x_start + (img_w - padding * 2 - tw) // 2, y + 12), cleaned_title, fill=COLORS["text"], font=font_title)
    y += header_h + 4

    col_x = [x_start + i * cell_w for i in range(num_cols)]

    show_day_headers = num_cols > 1
    if show_day_headers:
        for i, (day_key, items) in enumerate(filtered_by_day.items()):
            draw_rounded_rect(draw, (col_x[i], y, col_x[i] + cell_w - 4, y + day_header_h), 8, COLORS["day_header"])
            clean_key = day_key.replace("📅 ", "")
            dw = text_width(draw, clean_key, font_header)
            draw.text((col_x[i] + (cell_w - 4 - dw) // 2, y + 10), clean_key, fill=COLORS["text"], font=font_header)
        y += day_header_h + 4

    for row in range(max_items):
        lines_count = max_lines_per_row[row]
        row_h = lines_count * LINE_HEIGHT + ITEM_PADDING * 2
        fill = COLORS["row_even"] if row % 2 == 0 else COLORS["row_odd"]
        for col, (day_key, items) in enumerate(filtered_by_day.items()):
            x = col_x[col]
            draw_rounded_rect(draw, (x, y, x + cell_w - 4, y + row_h - 4), 6, fill)
            if row < len(items):
                lines = col_lines[col][row]
                for li, line in enumerate(lines):
                    draw.text((x + ITEM_PADDING, y + ITEM_PADDING + li * LINE_HEIGHT), line, fill=COLORS["text"], font=font_cell)
        y += row_h

    return img
