
from pathlib import Path
import math
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

BASE_DIR = Path(__file__).resolve().parent
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_CLASS_ID = 0
JOINTS = ["코", "왼쪽 눈", "오른쪽 눈", "왼쪽 귀", "오른쪽 귀",
          "왼쪽 어깨", "오른쪽 어깨", "왼쪽 팔꿈치", "오른쪽 팔꿈치",
          "왼쪽 손목", "오른쪽 손목", "왼쪽 엉덩이", "오른쪽 엉덩이",
          "왼쪽 무릎", "오른쪽 무릎", "왼쪽 발목", "오른쪽 발목"]
EDGES = [(0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9),
         (6, 8), (8, 10), (5, 11), (6, 12), (11, 12), (11, 13),
         (13, 15), (12, 14), (14, 16)]


def label_for(image, label_dir=None):
    """GUI에서 고른 폴더를 우선 사용하고, 미선택이면 이미지 경로에서 기본 위치를 정합니다."""
    if label_dir is not None:
        return Path(label_dir) / (image.stem + ".txt")
    for i in range(len(image.parts) - 2, -1, -1):
        if image.parts[i].lower() == "images":
            return (Path(*image.parts[:i]) / "labels" / Path(*image.parts[i + 1:])).with_suffix(".txt")
    if image.parent.name.endswith("_img"):
        return image.parent.with_name(image.parent.name[:-4] + "_pose_labels") / (image.stem + ".txt")
    return image.parent / "labels" / (image.stem + ".txt")


def read_labels(path):
    """잘못된 형식은 무시하지 않고 알려서 기존 파일을 실수로 덮어쓰지 않게 합니다."""
    people = []
    if not path.exists():
        return people
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        values = list(map(float, line.split()))
        if len(values) != 56 or not all(math.isfinite(v) for v in values):
            raise ValueError(f"{number}줄: COCO 17관절 형식(숫자 56개)이 필요합니다.")
        class_id, x, y, w, h = values[:5]
        points = [values[i:i + 3] for i in range(5, 56, 3)]
        if class_id < 0 or class_id != int(class_id):
            raise ValueError(f"{number}줄: 클래스 번호는 0 이상의 정수여야 합니다.")
        if not (0 < w <= 1 and 0 < h <= 1 and x - w / 2 >= -1e-6
                and y - h / 2 >= -1e-6 and x + w / 2 <= 1 + 1e-6 and y + h / 2 <= 1 + 1e-6):
            raise ValueError(f"{number}줄: 박스 좌표 범위를 확인하세요.")
        if any(not (0 <= px <= 1 and 0 <= py <= 1 and v in (0, 1, 2)) for px, py, v in points):
            raise ValueError(f"{number}줄: 관절 좌표 또는 v 값이 잘못됐습니다.")
        people.append({"class_id": int(class_id), "box": [x, y, w, h], "points": points})
    return people


def save_labels(path, people):
    lines = []
    for person in people:
        fields = [str(person["class_id"])] + [f"{v:.8f}" for v in person["box"]]
        for x, y, visible in person["points"]:
            fields.extend([f"{x:.8f}", f"{y:.8f}", str(int(visible))] if visible else ["0", "0", "0"])
        lines.append(" ".join(fields))
    path.parent.mkdir(parents=True, exist_ok=True)
    # write_text는 파일이 있으면 전체 내용을 덮어씁니다. 저장 버튼에서만 호출합니다.
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


class PoseEditor:
    def __init__(self, window):
        self.window = window
        self.images, self.people = [], []
        self.index = self.person_index = self.joint = 0
        self.path = None
        self.image_dir, self.label_dir = BASE_DIR, None
        self.dirty = False
        self.box_mode = self.drag_start = None
        self.class_id = tk.StringVar(value=str(DEFAULT_CLASS_ID))
        self.visibility = tk.IntVar(value=2)
        self.advance = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="이미지를 선택하세요.")
        window.title("17관절 라벨 편집")
        top = tk.Frame(window)
        top.pack(fill="x")
        for text, command in [("이미지 선택", self.choose), ("폴더 선택", self.choose_folder),
                              ("라벨 폴더 선택", self.choose_labels), ("이전", lambda: self.move(-1)),
                              ("다음", lambda: self.move(1)), ("저장(TXT 덮어쓰기)", self.save),
                              ("저장된 상태로 되돌리기", lambda: self.load(self.index))]:
            tk.Button(top, text=text, command=command).pack(side="left", padx=3, pady=5)
        body = tk.Frame(window)
        body.pack()
        self.canvas = tk.Canvas(body, width=640, height=640, bg="#222222", highlightthickness=0)
        self.canvas.pack(side="left", anchor="n")
        side = tk.Frame(body)
        side.pack(side="left", fill="y", padx=10)
        tk.Label(side, text="사람 선택 (박스별)").pack(anchor="w")
        self.person_list = tk.Listbox(side, height=4, width=29, exportselection=False)
        self.person_list.pack()
        self.person_list.bind("<<ListboxSelect>>", self.select_person)
        row = tk.Frame(side)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="클래스 번호").pack(side="left")
        tk.Entry(row, textvariable=self.class_id, width=6).pack(side="left")
        tk.Button(row, text="적용", command=self.apply_class).pack(side="left")
        for text, mode in [("사람 추가: 박스 드래그", "add"), ("선택 사람 박스 수정", "replace")]:
            tk.Button(side, text=text, command=lambda m=mode: self.start_box(m)).pack(fill="x")
        tk.Button(side, text="선택 사람 삭제", command=self.delete_person).pack(fill="x")
        tk.Label(side, text="관절 선택 → 이미지에서 위치 클릭").pack(anchor="w", pady=(8, 0))
        self.joint_list = tk.Listbox(side, height=17, width=29, exportselection=False)
        self.joint_list.pack()
        self.joint_list.bind("<<ListboxSelect>>", self.select_joint)
        for value, text in [(2, "보임 (v=2)"), (1, "가렸지만 위치 지정 가능 (v=1)")]:
            tk.Radiobutton(side, text=text, variable=self.visibility, value=value,
                           command=self.change_visibility).pack(anchor="w")
        tk.Button(side, text="선택 관절 지우기 (v=0)", command=self.clear_joint).pack(fill="x")
        tk.Checkbutton(side, text="점을 찍은 뒤 다음 관절 선택", variable=self.advance).pack(anchor="w")
        tk.Label(window, textvariable=self.status, anchor="w", wraplength=1000).pack(fill="x", padx=5, pady=5)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        window.bind("<Control-s>", lambda event: self.save())
        window.bind("<Left>", lambda event: self.move(-1))
        window.bind("<Right>", lambda event: self.move(1))
        window.bind("<Escape>", lambda event: self.cancel_box())
        window.protocol("WM_DELETE_WINDOW", self.close)

    def selected_person(self):
        return self.people[self.person_index] if self.people else None

    def can_leave(self):
        # 클래스 입력 후 적용 버튼을 누르지 않았어도 이동 전에 반영합니다.
        if self.path is not None and not self.apply_class():
            return False
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("미저장 변경", "변경 내용을 저장할까요?\n아니요: 변경 버리기 / 취소: 편집 계속")
        return self.save() if answer is True else answer is False

    def choose(self):
        if not self.can_leave():
            return
        files = filedialog.askopenfilenames(parent=self.window, initialdir=str(self.image_dir), title="편집할 이미지 선택",
                                           filetypes=[("이미지", "*.jpg *.jpeg *.png *.bmp *.webp")])
        self.open_images(files)

    def open_images(self, files):
        if not files:
            return
        paths = sorted(set(Path(p).resolve() for p in files))
        # 이름이 같은 이미지가 한 라벨 폴더의 TXT를 서로 덮어쓰지 않도록 합니다.
        if len({p.stem.casefold() for p in paths}) != len(paths):
            messagebox.showerror("파일명 중복", "이름이 같은 이미지는 나누어 선택하세요.")
            return
        self.images = paths
        self.image_dir = paths[0].parent
        self.load(0)

    def choose_folder(self):
        if not self.can_leave():
            return
        folder = filedialog.askdirectory(parent=self.window, initialdir=str(self.image_dir), title="이미지 폴더 선택")
        if folder:
            paths = [p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
            if not paths:
                messagebox.showinfo("이미지 없음", "선택한 폴더 바로 아래에 이미지가 없습니다.")
                return
            self.open_images(paths)

    def choose_labels(self):
        if not self.can_leave():
            return
        initial_dir = self.label_dir if self.label_dir and self.label_dir.is_dir() else self.image_dir
        folder = filedialog.askdirectory(parent=self.window, initialdir=str(initial_dir), mustexist=False,
                                         title="17관절 TXT를 읽고 저장할 폴더 선택")
        if folder:
            self.label_dir = Path(folder).resolve()
            if self.images:
                self.load(self.index)
            else:
                self.status.set(f"라벨 폴더: {self.label_dir} | 이미지를 선택하세요.")

    def load(self, index):
        if not self.images:
            return
        self.index = index
        path = self.images[index]
        label_path = label_for(path, self.label_dir)
        try:
            people = read_labels(label_path)
            with Image.open(path) as source:
                image = source.convert("RGB")
            image.thumbnail((min(1000, max(320, self.window.winfo_screenwidth() - 370)),
                             min(820, max(320, self.window.winfo_screenheight() - 160))))
        except (OSError, ValueError) as error:
            # 실패한 파일은 저장 대상으로 잡지 않습니다.
            self.path, self.people, self.dirty = None, [], False
            self.canvas.delete("all")
            self.person_list.delete(0, "end")
            self.joint_list.delete(0, "end")
            self.status.set(f"불러오기 실패: {path.name} | TXT: {label_path}")
            messagebox.showerror("불러오기 실패", f"{path.name}\n{error}\nTXT: {label_path}\n'라벨 폴더 선택'에서 위치를 확인하세요.")
            return
        self.index, self.path, self.label_path = index, path, label_path
        self.people, self.person_index, self.joint, self.dirty = people, 0, 0, False
        self.box_mode = self.drag_start = None
        self.width, self.height = image.size
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.config(width=self.width, height=self.height)
        self.class_id.set(str(people[0]["class_id"] if people else DEFAULT_CLASS_ID))
        self.redraw()

    def redraw(self):
        if self.path is None:
            return
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.person_list.delete(0, "end")
        for index, person in enumerate(self.people):
            selected = index == self.person_index
            color = "cyan" if selected else "gray"
            self.person_list.insert("end", f"사람 {index + 1} / 클래스 {person['class_id']}")
            x, y, w, h = person["box"]
            self.canvas.create_rectangle((x - w / 2) * self.width, (y - h / 2) * self.height,
                                         (x + w / 2) * self.width, (y + h / 2) * self.height, outline=color, width=2)
            points = person["points"]
            for a, b in EDGES:
                if points[a][2] and points[b][2]:
                    self.canvas.create_line(points[a][0] * self.width, points[a][1] * self.height,
                                            points[b][0] * self.width, points[b][1] * self.height, fill=color, width=2)
            for joint, (x, y, visible) in enumerate(points):
                if not visible:
                    continue
                x, y = x * self.width, y * self.height
                dot = "red" if selected and joint == self.joint else ("lime" if visible == 2 else "yellow")
                self.canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=dot, outline="black")
                self.canvas.create_text(x + 7, y - 7, text=str(joint), fill=dot, anchor="w")
        if self.people:
            self.person_list.selection_set(self.person_index)
        self.joint_list.delete(0, "end")
        person = self.selected_person()
        for index, name in enumerate(JOINTS):
            visible = int(person["points"][index][2]) if person else 0
            self.joint_list.insert("end", f"{index:2d} {name}  [v={visible}]")
        self.joint_list.selection_set(self.joint)
        self.joint_list.see(self.joint)
        if person and person["points"][self.joint][2]:
            self.visibility.set(int(person["points"][self.joint][2]))
        self.status.set(f"{self.index + 1}/{len(self.images)} {self.path.name} | "
                        f"{'미저장 변경 있음' if self.dirty else '변경 없음'} | 저장: {self.label_path}")

    def select_person(self, event=None):
        selected = self.person_list.curselection()
        if selected and selected[0] != self.person_index:
            if not self.apply_class():
                self.redraw()
                return
            self.person_index = selected[0]
            self.class_id.set(str(self.people[self.person_index]["class_id"]))
            self.cancel_box()

    def select_joint(self, event=None):
        selected = self.joint_list.curselection()
        if selected and selected[0] != self.joint:
            self.joint = selected[0]
            self.redraw()

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
        value = self.get_class()
        person = self.selected_person()
        if value is None:
            return False
        if person and person["class_id"] != value:
            person["class_id"], self.dirty = value, True
            self.redraw()
        return True

    def start_box(self, mode):
        if self.path is not None and (mode == "add" or self.people):
            self.box_mode, self.drag_start = mode, None
            self.status.set("사람 전체를 둘러싸는 박스를 드래그하세요. Esc: 취소")

    def cancel_box(self):
        self.box_mode = self.drag_start = None
        self.redraw()

    def position(self, event):
        return max(0, min(event.x, self.width)), max(0, min(event.y, self.height))

    def press(self, event):
        if self.path is None:
            return
        x, y = self.position(event)
        if self.box_mode:
            self.drag_start = (x, y)
        elif self.people:
            self.selected_person()["points"][self.joint] = [x / self.width, y / self.height, self.visibility.get()]
            self.dirty = True
            if self.advance.get():
                self.joint = min(16, self.joint + 1)
            self.redraw()
        else:
            self.status.set("먼저 '사람 추가'를 눌러 박스를 드래그하세요.")

    def drag(self, event):
        if self.drag_start:
            self.canvas.delete("drag")
            self.canvas.create_rectangle(*self.drag_start, *self.position(event), outline="red", width=2, tags="drag")

    def release(self, event):
        if not self.drag_start:
            return
        x1, x2 = sorted([self.drag_start[0], self.position(event)[0]])
        y1, y2 = sorted([self.drag_start[1], self.position(event)[1]])
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            box = [(x1 + x2) / (2 * self.width), (y1 + y2) / (2 * self.height),
                   (x2 - x1) / self.width, (y2 - y1) / self.height]
            if self.box_mode == "add":
                class_id = self.get_class()
                if class_id is not None:
                    self.people.append({"class_id": class_id, "box": box, "points": [[0, 0, 0] for _ in JOINTS]})
                    self.person_index, self.joint, self.dirty = len(self.people) - 1, 0, True
            else:
                self.selected_person()["box"], self.dirty = box, True
        self.cancel_box()

    def delete_person(self):
        if self.people:
            self.people.pop(self.person_index)
            self.person_index, self.dirty = max(0, self.person_index - 1), True
            self.class_id.set(str(self.people[self.person_index]["class_id"]) if self.people else str(DEFAULT_CLASS_ID))
            self.cancel_box()

    def clear_joint(self):
        if self.people:
            self.selected_person()["points"][self.joint] = [0, 0, 0]
            self.dirty = True
            self.redraw()

    def change_visibility(self):
        if self.people and self.selected_person()["points"][self.joint][2]:
            self.selected_person()["points"][self.joint][2] = self.visibility.get()
            self.dirty = True
            self.redraw()

    def save(self):
        if self.path is None or not self.apply_class():
            return False
        try:
            save_labels(self.label_path, self.people)
        except OSError as error:
            messagebox.showerror("저장 실패", str(error))
            return False
        self.dirty = False
        self.redraw()
        self.status.set(f"저장 완료 (TXT 덮어쓰기): {self.label_path}")
        return True

    def move(self, direction):
        if self.images and self.can_leave():
            self.load((self.index + direction) % len(self.images))

    def close(self):
        if self.can_leave():
            self.window.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    editor = PoseEditor(window)
    window.after(100, editor.choose)
    window.mainloop()
