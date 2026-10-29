"""실행: python view_pose_labels.py   /   필요 패키지: Pillow, PyYAML
pose_dataset의 기존 TXT를 이미지 위에 표시하는 읽기 전용 확인 프로그램입니다.
이전/다음 버튼 또는 좌우 방향키로 이동하고, 이미지 선택 버튼으로 직접 고를 수 있습니다.
관절 번호는 TXT의 순서(0부터)입니다. 초록: v=2, 노랑: v=1, v=0은 표시하지 않습니다.
이 데이터셋의 관절 정의는 제공되지 않아 연결선은 비워 두었습니다.
"""

import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import yaml
from PIL import Image, ImageDraw, ImageFont, ImageTk

DATASET_DIR = Path(__file__).resolve().parent / "dataset_pose"
LABEL_DIR = DATASET_DIR / "labels"

# 관절 의미를 확인한 뒤 번호 쌍을 넣으세요. 예: [(0, 1), (1, 2)]
EDGES = []


def draw_labels(image_path, label_path, config, max_size):
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    image.thumbnail(max_size)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=16)
    width, height = image.size
    count, dimensions = config["kpt_shape"]
    names = config["names"]
    if not label_path.is_file():
        return image, "TXT 없음"
    lines = label_path.read_text(encoding="utf-8-sig").splitlines()
    errors, people = [], 0

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            values = list(map(float, line.split()))
            if len(values) != 5 + count * dimensions or not all(math.isfinite(v) for v in values):
                raise ValueError(f"유효한 숫자 {5 + count * dimensions}개가 필요합니다.")
            c, x, y, w, h = values[:5]
            if c != int(c) or c < 0:
                raise ValueError("클래스 번호가 잘못됐습니다.")
            name = names.get(int(c), "")
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                raise ValueError("박스 좌표 범위가 잘못됐습니다.")
            if min(x - w / 2, y - h / 2) < -1e-7 or max(x + w / 2, y + h / 2) > 1 + 1e-7:
                raise ValueError("박스가 이미지 밖으로 나갑니다.")
            points = []
            for offset in range(5, len(values), dimensions):
                px, py = values[offset:offset + 2]
                visible = values[offset + 2] if dimensions == 3 else 2
                if visible not in (0, 1, 2) or not (0 <= px <= 1 and 0 <= py <= 1):
                    raise ValueError("관절 좌표 또는 표시 상태가 잘못됐습니다.")
                points.append((px * width, py * height, visible))
        except (ValueError, KeyError, IndexError) as error:
            errors.append(f"{line_number}줄: {error}")
            continue

        people += 1
        x1, y1 = (x - w / 2) * width, (y - h / 2) * height
        draw.rectangle((x1, y1, (x + w / 2) * width, (y + h / 2) * height), outline="cyan", width=2)
        draw.text((x1, max(0, y1 - 20)), f"{int(c)} {name}", font=font, fill="cyan", stroke_width=1, stroke_fill="black")
        for first, second in EDGES:
            if points[first][2] > 0 and points[second][2] > 0:
                draw.line((*points[first][:2], *points[second][:2]), fill="cyan", width=2)
        for number, (px, py, visible) in enumerate(points):
            if visible == 0:
                continue
            color = "lime" if visible == 2 else "yellow"
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color)
            draw.text((px + 4, py - 12), str(number), font=font, fill=color, stroke_width=1, stroke_fill="black")
    details = f"객체 {people}개 / 관절 {count}개" if lines else "빈 TXT (객체 없음)"
    return image, " | ".join(errors) if errors else details


def main():
    count = 12 if LABEL_DIR.name == "기존labels" else 17
    config = {"kpt_shape": [count, 3], "names": {}} #labels의 관절을 표시합니다
    
    if config["kpt_shape"][1] not in (2, 3):
        raise SystemExit("관절 형식은 [관절 개수, 2 또는 3]이어야 합니다.")
    pairs = []
    for split in ["valid"]:
        image_dir, label_dir = DATASET_DIR / split / "images", DATASET_DIR / split / LABEL_DIR.name
        for image in sorted(image_dir.rglob("*")):
            if image.is_file() and image.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                pairs.append((image, (label_dir / image.relative_to(image_dir)).with_suffix(".txt")))
    if not pairs:
        raise SystemExit("dataset의 train/valid/test 안에서 이미지를 찾지 못했습니다.")

    window = tk.Tk()
    window.title("관절 라벨 확인")
    max_size = (min(1600, window.winfo_screenwidth() - 80), min(900, window.winfo_screenheight() - 220))
    header = tk.Label(window, pady=6)
    header.pack()
    picture = tk.Label(window, background="#202020")
    picture.pack()
    details = tk.Label(window, wraplength=max_size[0], pady=4)
    details.pack()
    controls = tk.Frame(window, pady=6)
    controls.pack()
    index = 0

    def show(step=0):
        nonlocal index
        index = (index + step) % len(pairs)
        image_path, label_path = pairs[index]
        try:
            preview, message = draw_labels(image_path, label_path, config, max_size)
            picture.image = ImageTk.PhotoImage(preview)
            picture.configure(image=picture.image)
        except (OSError, ValueError) as error:
            picture.configure(image="")
            message = f"읽기 오류: {error}"
        header.configure(text=f"{index + 1}/{len(pairs)}  {image_path.relative_to(DATASET_DIR)}")
        details.configure(text=message)

    def select_image():
        nonlocal index
        selected = filedialog.askopenfilename(parent=window, initialdir=str(DATASET_DIR),
                    filetypes=[("이미지", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if selected:
            position = next((i for i, pair in enumerate(pairs) if pair[0].resolve() == Path(selected).resolve()), None)
            if position is None:
                details.configure(text="dataset 안에 있는 이미지를 선택하세요.")
            else:
                index = position
                show()

    for title, command in (("◀ 이전", lambda: show(-1)), ("이미지 선택", select_image), ("다음 ▶", lambda: show(1))):
        tk.Button(controls, text=title, width=12, command=command).pack(side="left", padx=4)
    window.bind("<Left>", lambda event: show(-1))
    window.bind("<Right>", lambda event: show(1))
    window.bind("<Escape>", lambda event: window.destroy())
    show()
    window.mainloop()


if __name__ == "__main__":
    main()
