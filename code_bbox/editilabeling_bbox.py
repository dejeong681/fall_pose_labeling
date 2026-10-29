import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

BASE_DIR = Path(__file__).resolve().parent
INITIAL_WINDOW_SIZE = (1200, 800)
DEFAULT_CLASS_ID = 0
CLASS_NAMES = {0: "fall", 1: "not_fall"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def label_for(image, label_dir=None):
    if label_dir is not None:
        return Path(label_dir) / (image.stem + ".txt")
    # images가 여러 번 나오면 이미지에 가장 가까운 images 폴더를 사용합니다.
    for i in range(len(image.parts) - 2, -1, -1):
        if image.parts[i].lower() == "images":
            return (Path(*image.parts[:i]) / "labels" / Path(*image.parts[i + 1:])).with_suffix(".txt")
    if image.parent.name.endswith("_img"):
        return image.parent.with_name(image.parent.name[:-4] + "_label") / (image.stem + ".txt")
    if image.with_suffix(".txt").is_file():
        return image.with_suffix(".txt")
    return image.parent / "labels" / (image.stem + ".txt")


def read_labels(path):
    if not path.is_file():
        return []
    boxes = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        row = list(map(float, line.split()))
        if len(row) != 5 or not all(math.isfinite(v) for v in row):
            raise ValueError(f"{number}줄: 박스 라벨은 숫자 5개여야 합니다. 관절 라벨은 사용할 수 없습니다.")
        c, x, y, w, h = row
        if c < 0 or c != int(c) or not (0 < w <= 1 and 0 < h <= 1):
            raise ValueError(f"{number}줄: 클래스 번호 또는 박스 크기가 잘못됐습니다.")
        if min(x - w / 2, y - h / 2) < -1e-6 or max(x + w / 2, y + h / 2) > 1 + 1e-6:
            raise ValueError(f"{number}줄: 박스가 이미지 범위를 벗어났습니다.")
        boxes.append([int(c), x, y, w, h])
    return boxes


def save_labels(path, boxes):
    text = "".join(f"{int(c)} {x:.8f} {y:.8f} {w:.8f} {h:.8f}\n" for c, x, y, w, h in boxes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")  # 기존 TXT 전체 덮어쓰기


class BoxEditor:
    def __init__(self, window):
        self.window = window
        self.images, self.boxes = [], []
        self.index = 0
        self.path = self.label_dir = self.selected = self.editing = self.start = None
        self.original_image = None
        self.offset_x = self.offset_y = 0
        self.dirty = False
        self.class_id = tk.StringVar(value=str(DEFAULT_CLASS_ID))
        self.status = tk.StringVar(value="이미지를 선택하세요. 저장할 TXT 경로가 여기에 표시됩니다.")
        window.title("바운딩박스 라벨링")
        # 창 크기는 시작할 때만 정합니다. 사진을 읽을 때는 바꾸지 않습니다.
        width = min(INITIAL_WINDOW_SIZE[0], window.winfo_screenwidth() - 60)
        height = min(INITIAL_WINDOW_SIZE[1], window.winfo_screenheight() - 100)
        window.geometry(f"{width}x{height}")
        top = tk.Frame(window)
        top.pack(fill="x")
        for name, command in [("이미지 선택", self.choose_files), ("폴더 선택", self.choose_folder),
                              ("라벨 폴더 선택", self.choose_labels), ("이전", lambda: self.move(-1)),
                              ("다음", lambda: self.move(1)), ("저장 / Ctrl+S", self.save)]:
            tk.Button(top, text=name, command=command).pack(side="left", padx=3, pady=4)
        body = tk.Frame(window)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, width=1, height=1, bg="#222222", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        side = tk.Frame(body)
        side.pack(side="left", padx=8, fill="y")
        tk.Label(side, text="기본 클래스: 0 fall / 1 not_fall").pack(anchor="w")
        tk.Label(side, text="클래스 번호 (새 박스 / 선택 박스)").pack(anchor="w")
        tk.Entry(side, textvariable=self.class_id, width=12).pack(anchor="w", pady=4)
        tk.Label(side, text="기존 박스 선택").pack(anchor="w")
        self.box_list = tk.Listbox(side, width=28, height=12, exportselection=False)
        self.box_list.pack()
        self.box_list.bind("<<ListboxSelect>>", self.select_box)
        for name, command in [("선택 박스에 클래스 적용", self.apply_class), ("박스 추가", self.add_mode),
                              ("선택 박스 다시 그리기", self.replace_mode), ("선택 박스 삭제", self.delete_box),
                              ("저장된 상태로 되돌리기", lambda: self.load(self.index))]:
            tk.Button(side, text=name, command=command).pack(fill="x", pady=2)
        tk.Label(side, text="이미지에서 드래그하면 박스 추가\nEsc: 다시 그리기 취소", justify="left").pack(anchor="w", pady=8)
        tk.Label(window, textvariable=self.status, wraplength=1100, justify="left", anchor="w").pack(fill="x", padx=5, pady=5)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Configure>", self.fit_image)
        window.bind("<Control-s>", lambda event: self.save())
        window.bind("<Left>", lambda event: self.move(-1))
        window.bind("<Right>", lambda event: self.move(1))
        window.bind("<Escape>", lambda event: self.add_mode())
        window.protocol("WM_DELETE_WINDOW", self.close)

    def can_leave(self):
        if self.path is not None and self.selected is not None and not self.apply_class():
            return False
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("미저장 변경", "저장할까요?\n아니요: 변경 버리기 / 취소: 편집 계속")
        return self.save() if answer is True else answer is False

    def open_images(self, paths):
        if not paths:
            return
        images = sorted(set(Path(p).resolve() for p in paths))
        # 지정한 한 폴더에 저장할 때 같은 파일명끼리 충돌하지 않도록 합니다.
        if len({p.stem for p in images}) != len(images):
            messagebox.showerror("파일명 중복", "이름이 같은 이미지는 나누어 선택하세요.")
            return
        self.images = images
        self.load(0)

    def choose_files(self):
        if self.can_leave():
            self.open_images(filedialog.askopenfilenames(initialdir=str(BASE_DIR), title="라벨링할 이미지 선택",
                             filetypes=[("이미지", "*.jpg *.jpeg *.png *.bmp *.webp")]))

    def choose_folder(self):
        if not self.can_leave():
            return
        folder = filedialog.askdirectory(initialdir=str(BASE_DIR), title="이미지 폴더 선택")
        if folder:
            paths = [p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
            if not paths:
                messagebox.showinfo("이미지 없음", "선택한 폴더 바로 아래에 이미지가 없습니다.")
            self.open_images(paths)

    def choose_labels(self):
        if not self.can_leave():
            return
        folder = filedialog.askdirectory(initialdir=str(self.label_dir or BASE_DIR), mustexist=False, title="TXT를 읽고 저장할 폴더 선택")
        if folder:
            self.label_dir = Path(folder).resolve()
            self.load(self.index)
            if not self.images:
                self.status.set(f"라벨 저장 폴더: {self.label_dir}")

    def load(self, index):
        if not self.images:
            return
        self.index, self.path = index, None
        self.original_image = None
        self.boxes, self.selected, self.editing, self.start, self.dirty = [], None, None, None, False
        self.canvas.delete("all")
        self.box_list.delete(0, "end")
        path = self.images[index]
        self.label_path = label_for(path, self.label_dir)
        try:
            boxes = read_labels(self.label_path)
            with Image.open(path) as original:
                image = original.convert("RGB")
        except (OSError, ValueError) as error:
            self.status.set(f"불러오기 실패: {path.name} | TXT: {self.label_path}")
            messagebox.showerror("불러오기 실패", str(error))
            return
        self.path, self.boxes = path, boxes
        self.original_image = image
        self.fit_image()

    def fit_image(self, event=None):
        """창이 제공한 영역 안에 사진을 맞춥니다. 검은 여백은 좌표 계산에서 제외합니다."""
        if self.path is None or self.original_image is None:
            return
        canvas_width = max(1, event.width if event else self.canvas.winfo_width())
        canvas_height = max(1, event.height if event else self.canvas.winfo_height())
        image = self.original_image.copy()
        image.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        self.width, self.height = image.size
        self.offset_x = (canvas_width - self.width) // 2
        self.offset_y = (canvas_height - self.height) // 2
        self.photo = ImageTk.PhotoImage(image, master=self.window)
        self.start = None  # 드래그 중 창 크기가 바뀌면 해당 드래그만 취소합니다.
        self.redraw()

    def redraw(self):
        if self.path is None:
            return
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.photo, anchor="nw")
        self.box_list.delete(0, "end")
        for index, (c, x, y, w, h) in enumerate(self.boxes):
            name = CLASS_NAMES.get(int(c), "class")
            self.box_list.insert("end", f"{index + 1}: {int(c)} {name}")
            color = "yellow" if index == self.selected else ("red" if c == 0 else "lime")
            x1 = self.offset_x + (x - w / 2) * self.width
            y1 = self.offset_y + (y - h / 2) * self.height
            self.canvas.create_rectangle(x1, y1, self.offset_x + (x + w / 2) * self.width,
                                         self.offset_y + (y + h / 2) * self.height, outline=color, width=2)
            self.canvas.create_text(x1 + 3, max(10, y1 - 10), text=f"{index + 1}: {int(c)} {name}", fill=color, anchor="w")
        if self.selected is not None:
            self.box_list.selection_set(self.selected)
        self.status.set(f"{self.index + 1}/{len(self.images)} {self.path.name} | 박스 {len(self.boxes)}개 | "
                        f"{'미저장 변경 있음' if self.dirty else '변경 없음'}\nTXT: {self.label_path}")

    def get_class(self):
        try:
            value = int(self.class_id.get())
            if value < 0:
                raise ValueError
            return value
        except ValueError:
            messagebox.showerror("클래스 번호", "0 이상의 정수를 입력하세요.")
            return None

    def apply_class(self):
        if self.selected is None:
            return True
        value = self.get_class()
        if value is None:
            return False
        if self.boxes[self.selected][0] != value:
            self.boxes[self.selected][0], self.dirty = value, True
            self.redraw()
        return True

    def select_box(self, event=None):
        selection = self.box_list.curselection()
        if selection and selection[0] != self.selected:
            if not self.apply_class():
                self.redraw()
                return
            self.selected = selection[0]
            self.class_id.set(str(self.boxes[self.selected][0]))
            self.add_mode()

    def add_mode(self):
        self.editing = self.start = None
        self.redraw()

    def replace_mode(self):
        if self.selected is not None:
            self.editing = self.selected
            self.status.set("선택한 박스의 새 범위를 드래그하세요. Esc: 취소")

    def position(self, event):
        return (max(0, min(event.x - self.offset_x, self.width)),
                max(0, min(event.y - self.offset_y, self.height)))

    def press(self, event):
        if (self.path is not None and self.offset_x <= event.x < self.offset_x + self.width
                and self.offset_y <= event.y < self.offset_y + self.height):
            self.start = self.position(event)

    def drag(self, event):
        if self.start:
            self.canvas.delete("drag")
            x, y = self.position(event)
            self.canvas.create_rectangle(self.start[0] + self.offset_x, self.start[1] + self.offset_y,
                                         x + self.offset_x, y + self.offset_y,
                                         outline="cyan", width=2, tags="drag")

    def release(self, event):
        if not self.start:
            return
        x1, x2 = sorted((self.start[0], self.position(event)[0]))
        y1, y2 = sorted((self.start[1], self.position(event)[1]))
        class_id = self.get_class()
        if class_id is not None and x2 - x1 >= 2 and y2 - y1 >= 2:
            box = [class_id, (x1 + x2) / (2 * self.width), (y1 + y2) / (2 * self.height),
                   (x2 - x1) / self.width, (y2 - y1) / self.height]
            if self.editing is None:
                self.boxes.append(box)
                self.selected = len(self.boxes) - 1
            else:
                self.boxes[self.editing] = box
                self.selected = self.editing
            self.dirty = True
        self.add_mode()

    def delete_box(self):
        if self.selected is not None:
            self.boxes.pop(self.selected)
            self.selected, self.dirty = None, True
            self.add_mode()

    def save(self):
        if self.path is None or not self.apply_class():
            return False
        try:
            save_labels(self.label_path, self.boxes)
        except OSError as error:
            messagebox.showerror("저장 실패", str(error))
            return False
        self.dirty = False
        self.redraw()
        self.status.set(f"저장 완료: {self.label_path}")
        return True

    def move(self, direction):
        if self.images and self.can_leave():
            self.load((self.index + direction) % len(self.images))

    def close(self):
        if self.can_leave():
            self.window.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    editor = BoxEditor(window)
    window.after(100, editor.choose_files)
    window.mainloop()
