"""YOLO 바운딩박스 자동 라벨링. 단독 파일이며 포즈 라벨은 만들지 않습니다.

설치: pip install ultralytics Pillow
현재 PC에서 모델 로드를 확인한 환경: conda activate auto-labeling
실행: python auto_label_bbox.py               # 이미지 폴더 선택 창
      python auto_label_bbox.py 이미지폴더경로
      python auto_label_bbox.py 이미지폴더경로 --class-id 0
      python auto_label_bbox.py 이미지폴더경로 --model models/다른모델.pt

기본 모델: models/fall_20261020.pt (MODEL_PATH에서 변경)
기본 저장 클래스: 모델 예측 그대로. 현재 모델은 0=fall, 1=not fall입니다.
--class-id 0 또는 1을 지정하면 모든 검출 박스를 그 번호로 저장합니다.
이 옵션은 낙상 판단이 아니라 사용자가 지정한 클래스의 일괄 적용입니다.
다른 탐지 모델을 쓰면 모델 클래스 정의와 SOURCE_CLASSES도 확인하세요.

입력 폴더 바로 아래 이미지만 처리합니다. 모델은 한 번만 불러와 재사용합니다.
출력: 입력폴더/auto_bbox/모델이름/실행시각/{labels, preview, report.jsonl}
TXT 한 줄: 클래스 중심x 중심y 너비 높이 (원본 크기로 나눈 0~1, 숫자 5개).
신뢰도는 TXT에 넣지 않고 사진과 report.jsonl에 표시합니다.
기존 이미지와 수동 라벨은 보존하고 실행마다 새 폴더를 만듭니다.
MODEL_PATH 또는 --model로 모델을 바꾸면 그 모델 이름의 폴더에 저장합니다.
같은 모델로 다시 실행해도 새 실행시각 폴더에 저장합니다. 기존 결과를 건너뛰지 않습니다.
미검출은 사람이 없다는 정답이 아니므로 TXT를 만들지 않고 사진과 기록만 남깁니다.

결과는 검토 전 초안입니다. label_bbox.py에서 원본 이미지를 연 다음,
'라벨 폴더 선택'으로 이번 결과의 labels 폴더를 지정해 수정할 수 있습니다.
preview는 표시가 그려진 확인용 사진이므로 학습 이미지로 쓰지 마세요.
"""

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "fall_20261020.pt"
CONF = 0.25  # 검수하면서 조정할 탐지 신뢰도 기준입니다.
IMGSZ = 640
DEVICE = "cpu"
SOURCE_CLASSES = None  # None: 모든 모델 클래스. COCO 모델에서 사람만 사용하려면 [0].
OUTPUT_CLASS_NAMES = {0: "fall", 1: "not_fall"}  # --class-id 사용 시 표시 이름
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def detections_from_result(result, output_class_id=None):
    """모델 출력에서 박스만 가져옵니다. 수동 편집기와 같은 5개 숫자로 저장합니다."""
    if result.boxes is None or len(result.boxes) == 0:
        return []
    boxes = result.boxes.xywhn.cpu().tolist()
    classes = result.boxes.cls.cpu().tolist()
    scores = result.boxes.conf.cpu().tolist()
    if not len(boxes) == len(classes) == len(scores):
        raise ValueError("모델 출력의 박스·클래스·신뢰도 개수가 다릅니다.")
    detections = []
    for box, source_class, score in zip(boxes, classes, scores):
        if len(box) != 4 or not all(math.isfinite(v) for v in [*box, source_class, score]):
            raise ValueError("모델이 유효하지 않은 박스 값을 반환했습니다.")
        x, y, w, h = box
        if source_class < 0 or source_class != int(source_class) or not 0 <= score <= 1:
            raise ValueError("모델 클래스 번호 또는 신뢰도가 잘못됐습니다.")
        if not (0 < w <= 1 and 0 < h <= 1) or min(x - w / 2, y - h / 2) < -1e-6 or max(x + w / 2, y + h / 2) > 1 + 1e-6:
            raise ValueError("모델 박스가 이미지 범위를 벗어났습니다.")
        class_id = int(source_class) if output_class_id is None else output_class_id
        detections.append({"class_id": class_id, "source_class_id": int(source_class),
                           "box": box, "confidence": score})
    return detections


def save_labels(path, detections):
    lines = [str(d["class_id"]) + " " + " ".join(f"{v:.8f}" for v in d["box"]) for d in detections]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def draw_preview(image, detections, names, output_class_id):
    width, height = image.size
    font_size = max(14, min(32, min(width, height) // 45))
    preview = Image.new("RGB", (width, height + font_size * 2 + 20), "#202020")
    preview.paste(image, (0, 0))
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default(size=font_size)
    for item in detections:
        c, (x, y, w, h) = item["class_id"], item["box"]
        name = (names if output_class_id is None else OUTPUT_CLASS_NAMES).get(c, f"class_{c}")
        color = "red" if c == 0 else "lime"
        x1, y1 = (x - w / 2) * width, (y - h / 2) * height
        draw.rectangle((x1, y1, (x + w / 2) * width, (y + h / 2) * height), outline=color, width=2)
        draw.text((x1 + 2, max(0, y1 - 18)), f"{c} {name} | det {item['confidence']:.2f}",
                  font=font, fill=color, stroke_width=1, stroke_fill="black")
    mode = "model classes" if output_class_id is None else f"manual class {output_class_id}"
    draw.text((6, height + 4), f"DRAFT | boxes: {len(detections)} | {mode}", fill="white", font=font)
    if not detections:
        draw.text((6, height + font_size + 12), "NO DETECTION - MANUAL REVIEW / NO TXT", fill="orange", font=font)
    return preview


def auto_label_folder(image_dir, model_path=MODEL_PATH, output_class_id=None, model=None):
    """폴더 하나를 처리하고 결과 경로와 집계를 반환합니다. model 인자는 저장 동작 테스트용입니다."""
    image_dir = Path(image_dir).resolve()
    if not image_dir.is_dir():
        raise ValueError(f"이미지 폴더가 없습니다: {image_dir}")
    if output_class_id is not None and (type(output_class_id) is not int or output_class_id < 0):
        raise ValueError("지정할 클래스 번호는 0 이상의 정수여야 합니다.")
    images = sorted(p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    if not images:
        raise ValueError(f"이미지가 없습니다: {image_dir}")
    if len({p.stem for p in images}) != len(images):
        raise ValueError("확장자만 다르고 이름이 같은 이미지가 있어 TXT 이름이 겹칩니다.")
    if model is None:
        if not Path(model_path).is_file():
            raise FileNotFoundError(f"모델 경로를 확인하세요: {model_path}")
        from ultralytics import YOLO  # 실제 실행할 때만 모델 환경을 불러옵니다.
        model = YOLO(str(model_path))
    if model.task != "detect":
        raise ValueError("바운딩박스 탐지 모델(.pt)을 지정하세요. 포즈 모델은 사용하지 않습니다.")
    names = {int(k): v for k, v in model.names.items()}
    output = image_dir / "auto_bbox" / Path(model_path).stem / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    label_dir, preview_dir = output / "labels", output / "preview"
    label_dir.mkdir(parents=True)
    preview_dir.mkdir()
    summary = {"images": len(images), "labeled_images": 0, "boxes": 0, "no_detections": 0,
               "errors": 0, "output_dir": str(output)}
    with (output / "report.jsonl").open("w", encoding="utf-8") as report:
        settings = {"type": "settings", "model": str(model_path), "model_names": names,
                    "confidence": CONF, "imgsz": IMGSZ, "device": DEVICE,
                    "source_classes": SOURCE_CLASSES, "output_class_id": output_class_id}
        report.write(json.dumps(settings, ensure_ascii=False) + "\n")
        print(f"모델 클래스: {names} / 저장 클래스: {output_class_id if output_class_id is not None else '모델 예측 유지'}")
        for number, path in enumerate(images, 1):
            record = {"type": "image", "image": path.name}
            try:
                with Image.open(path) as source:
                    image = source.convert("RGB")
                result = model.predict(source=image, conf=CONF, imgsz=IMGSZ, device=DEVICE,
                                       classes=SOURCE_CLASSES, verbose=False)[0]
                detections = detections_from_result(result, output_class_id)
                preview_path = preview_dir / (path.stem + ".jpg")
                draw_preview(image, detections, names, output_class_id).save(preview_path, quality=95)
                record.update(detections=detections, preview=str(preview_path))
                if detections:
                    label_path = label_dir / (path.stem + ".txt")
                    save_labels(label_path, detections)
                    record.update(status="draft", label=str(label_path))
                    summary["labeled_images"] += 1
                    summary["boxes"] += len(detections)
                else:
                    record["status"] = "no_detection_review_required"
                    summary["no_detections"] += 1
                print(f"[{number}/{len(images)}] {path.name} | 박스 {len(detections)}개" + ("" if detections else " / TXT 미생성, 직접 확인"))
            except Exception as error:
                summary["errors"] += 1
                record.update(status="error", error=f"{type(error).__name__}: {error}")
                print(f"[{number}/{len(images)}] 오류: {path.name} | {error}")
            report.write(json.dumps(record, ensure_ascii=False) + "\n")
            report.flush()
        report.write(json.dumps({"type": "summary", **summary}, ensure_ascii=False) + "\n")
    print(f"완료: TXT {summary['labeled_images']}개 / 박스 {summary['boxes']}개 / 미검출 {summary['no_detections']}장 / 오류 {summary['errors']}장")
    print(f"결과 폴더: {output}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="YOLO 바운딩박스 자동 라벨링")
    parser.add_argument("images", nargs="?", help="이미지 폴더. 생략하면 선택 창을 엽니다.")
    parser.add_argument("--model", type=Path, default=MODEL_PATH, help="탐지 모델 경로")
    parser.add_argument("--class-id", type=int, default=None, help="생략: 모델 클래스 유지. 지정: 모든 박스에 이 번호 적용")
    args = parser.parse_args()
    folder = args.images
    if not folder:
        window = tk.Tk()
        window.withdraw()
        folder = filedialog.askdirectory(parent=window, initialdir=str(BASE_DIR), title="자동 라벨링할 이미지 폴더 선택")
        window.destroy()
    if folder:
        auto_label_folder(folder, args.model, args.class_id)


if __name__ == "__main__":
    main()
