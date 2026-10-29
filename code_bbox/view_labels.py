from pathlib import Path
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "image_14-1_fall"
LABEL_DIR = BASE_DIR / "image_14-1_fall"/"auto_bbox"/"fall_20261020"/"20261027_164953_407972"/"labels"
CLASS_NAMES = {0: "fall", 1: "not_fall"}


def file_key(path, folder):
    # 확장자를 제외한 상대 경로로 이미지와 TXT를 연결합니다.
    return path.relative_to(folder).with_suffix("").as_posix().casefold()


def draw_boxes(image_path, label_path, max_size):
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    image.thumbnail(max_size)
    width, height = image.size
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)

    for line in label_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        class_id, x, y, w, h = map(float, line.split())
        class_id = int(class_id)
        # 정규화된 중심/너비/높이를 화면의 좌상단/우하단 픽셀로 되돌립니다.
        x1, y1 = (x - w / 2) * width, (y - h / 2) * height
        x2, y2 = (x + w / 2) * width, (y + h / 2) * height
        color = "lime" if class_id == 1 else "red"
        text = f"{class_id} {CLASS_NAMES.get(class_id, 'unknown')}"
        draw.rectangle((x1, y1, x2, y2), outline=color, width=3)
        text_y = max(0, y1 - 24)
        draw.rectangle((x1, text_y, x1 + 140, text_y + 24), fill="black")
        draw.text((x1 + 3, text_y + 2), text, font=font, fill=color)
    return image


def main():
    images = {
        file_key(path, IMAGE_DIR): path
        for path in IMAGE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    }
    pairs = []
    for label in sorted(LABEL_DIR.rglob("*.txt")):
        image = images.get(file_key(label, LABEL_DIR))
        if image is not None:
            pairs.append((image, label))
    if not pairs:
        raise SystemExit("이름이 일치하는 이미지와 TXT가 없습니다. 상단 경로를 확인하세요.")

    window = tk.Tk()
    window.title("바운딩박스 라벨 확인")
    max_size = (min(1600, window.winfo_screenwidth() - 80),
                min(900, window.winfo_screenheight() - 180))
    header = tk.Label(window, font=("맑은 고딕", 11), pady=8)
    header.pack()
    picture = tk.Label(window, background="#202020")
    picture.pack()
    controls = tk.Frame(window, pady=8)
    controls.pack()
    index = 0

    def show(step=0):
        nonlocal index
        index = (index + step) % len(pairs)
        image_path, label_path = pairs[index]
        preview = draw_boxes(image_path, label_path, max_size)
        picture.image = ImageTk.PhotoImage(preview)
        picture.configure(image=picture.image)
        header.configure(text=f"{index + 1} / {len(pairs)}   {image_path.name}")

    tk.Button(controls, text="◀ 이전", width=12, command=lambda: show(-1)).pack(side="left")
    tk.Label(controls, text="  초록: not_fall / 빨강: fall  ").pack(side="left")
    tk.Button(controls, text="다음 ▶", width=12, command=lambda: show(1)).pack(side="left")
    window.bind("<Left>", lambda event: show(-1))
    window.bind("<Right>", lambda event: show(1))
    window.bind("<Escape>", lambda event: window.destroy())
    show()
    window.mainloop()


if __name__ == "__main__":
    main()
