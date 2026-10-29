
from pathlib import Path
import logging
import tkinter as tk
from tkinter import filedialog

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR.parent / "models" / "yolo11s-pose.pt"

# 신뢰도 기준은 임시값입니다. 실제 관절을 확인하면서 조정하세요.
DET_CONF = 0.25
KP_CONF = 0.5
IMGSZ = 640
DEVICE = "cpu"
EDGES = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11),
         (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
         (0, 1), (0, 2), (1, 3), (2, 4)]


def make_label(box, points, scores):
    """모델 좌표를 YOLO Pose 한 줄로 바꾸고 사용할 관절을 표시합니다."""
    usable = ((scores >= KP_CONF) & np.isfinite(points).all(axis=1)
              & (points >= 0).all(axis=1) & (points <= 1).all(axis=1)
              & (points != 0).any(axis=1))
    fields = ["0"] + [f"{value:.8f}" for value in box]
    for (x, y), ok in zip(points, usable):
        fields.extend([f"{x:.8f}", f"{y:.8f}", "2"] if ok else ["0", "0", "0"])
    return " ".join(fields), usable


def choose_image_dir():
    """이미지 폴더만 선택합니다. 모델은 코드 상단 MODEL_PATH에서 지정합니다."""
    window = tk.Tk()
    window.withdraw()
    try:
        image_dir = filedialog.askdirectory(parent=window, initialdir=str(BASE_DIR),
                                            title="포즈 라벨링할 이미지 폴더 선택")
        if not image_dir:
            return None
        return Path(image_dir).resolve()
    finally:
        window.destroy()


def label_images(logger, image_dir, label_dir, preview_dir, model_path):
    if not model_path.is_file():
        raise SystemExit(f"모델이 없습니다: {model_path}\n코드 상단 MODEL_PATH를 확인하세요.")
    images = sorted(p for p in image_dir.glob("*")
                    if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"})
    if not images:
        raise SystemExit(f"이미지가 없습니다: {image_dir}")
    if len({p.stem.casefold() for p in images}) != len(images):
        raise SystemExit("확장자만 다르고 이름이 같은 이미지가 있습니다. TXT 이름이 겹치므로 나누어 처리하세요.")
    from ultralytics import YOLO  # GUI 선택을 마친 후에만 모델 환경을 불러옵니다.
    model = YOLO(str(model_path))
    if model.task != "pose":
        raise SystemExit("MODEL_PATH에 COCO 17관절 포즈 모델(.pt)을 지정하세요.")
    label_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    saved = skipped = missing = errors = 0
    for number, path in enumerate(images, 1):
        label_path = label_dir / (path.stem + ".txt")
        if label_path.exists():
            skipped += 1
            print(f"[{number}/{len(images)}] 기존 TXT 유지: {path.name}")
            continue
        try:
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"이미지를 읽지 못했습니다: {path}")
            result = model.predict(image, conf=DET_CONF, imgsz=IMGSZ, device=DEVICE, verbose=False)[0]
            preview, lines = image.copy(), []
            height, width = image.shape[:2]
            if result.keypoints is not None and len(result.keypoints):
                points = result.keypoints.xyn.cpu().numpy()
                scores = result.keypoints.conf.cpu().numpy()
                if points.shape[1:] != (17, 2):
                    raise RuntimeError("COCO 17관절 포즈 모델을 사용하세요.")
                for index, box in enumerate(result.boxes.xywhn.cpu().numpy()):
                    line, usable = make_label(box, points[index], scores[index])
                    lines.append(line)
                    xy = np.rint(points[index] * [width, height]).astype(int)
                    x1, y1, x2, y2 = result.boxes.xyxy[index].cpu().numpy().astype(int)
                    cv2.rectangle(preview, (x1, y1), (x2, y2), (255, 255, 0), 2)
                    cv2.putText(preview, f"person {index + 1} | kp={usable.sum()}/17",
                                (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                    for a, b in EDGES:
                        if usable[a] and usable[b]:
                            cv2.line(preview, tuple(xy[a]), tuple(xy[b]), (255, 255, 0), 2)
                    for joint, ((x, y), ok) in enumerate(zip(xy, usable)):
                        if ok:
                            cv2.circle(preview, (x, y), 3, (0, 255, 0), -1)
                            cv2.putText(preview, str(joint), (x + 4, y - 4),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
            if not lines:
                cv2.putText(preview, "NO POSE - MANUAL REVIEW", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            ok, encoded = cv2.imencode(".jpg", preview)
            if not ok:
                raise RuntimeError(f"확인용 이미지 인코딩 실패: {path}")
            encoded.tofile(str(preview_dir / (path.stem + ".jpg")))
            if lines:
                # x 모드: 사용자가 이미 만든 라벨을 덮어쓰지 않습니다.
                with label_path.open("x", encoding="utf-8") as output:
                    output.write("\n".join(lines) + "\n")
                saved += 1
                print(f"[{number}/{len(images)}] {path.name} | 사람 초안 {len(lines)}개")
            else:
                missing += 1
                print(f"[{number}/{len(images)}] {path.name} | 포즈 미검출: TXT 미생성, 직접 확인 필요")
                logger.warning("미검출 | %s | 포즈 없음, TXT 미생성", path)
        except Exception as error:
            errors += 1
            logger.exception("이미지 오류 | %s", path)
            print(f"[{number}/{len(images)}] 오류: {path.name} | {type(error).__name__}: {error}")
    summary = f"완료: TXT 생성 {saved}장 / 기존 TXT 유지 {skipped}장 / 미검출 {missing}장 / 오류 {errors}장"
    print(summary)
    logger.info(summary)
    print(f"라벨 TXT: {label_dir}")
    print(f"확인용 이미지: {preview_dir}")


def main():
    image_dir = choose_image_dir()
    if image_dir is None:
        print("선택을 취소했습니다.")
        return
    model_path = MODEL_PATH
    # 선택한 이미지 폴더 안에 저장합니다. 기존 폴더는 재사용합니다.
    label_dir, preview_dir = image_dir / "p_label", image_dir / "p_review"
    log_path = image_dir / "pose_labeling_log.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pose_labeling")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # a 모드로 이전 실행 기록을 보존합니다. 라벨 TXT의 저장 방식은 바꾸지 않습니다.
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    try:
        logger.info("실행 시작 | 이미지=%s | 라벨=%s | 모델=%s", image_dir, label_dir, model_path)
        label_images(logger, image_dir, label_dir, preview_dir, model_path)
    except (Exception, SystemExit):
        logger.exception("실행 중단")
        raise
    finally:
        logger.removeHandler(handler)
        handler.close()
        print(f"미검출·오류 기록: {log_path}")


if __name__ == "__main__":
    main()
