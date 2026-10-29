"""NAS 비낙상 이미지에 대응하는 JSON을 YOLO 탐지용 TXT로 변환합니다.

사용법 (이 파일이 있는 폴더에서 실행):
    python json_to_not_fall_txt.py --dry-run  # 저장하지 않고 확인
    python json_to_not_fall_txt.py            # TXT 저장

기본 입력: nas/비낙상데이터/ 안의 이미지 + 이 파일 아래의 기존 JSON
기본 출력: labels/not_fall/이미지이름.txt (이미지의 하위 폴더 구조 유지)
출력 한 줄: 1 중심x 중심y 너비 높이 (좌표는 모두 0~1)

별도 패키지나 모델은 필요하지 않습니다. 원본 JSON과 이미지는 수정하지 않습니다.
JSON의 bbox_location은 왼쪽 위 x,y / 오른쪽 아래 x,y라고 가정합니다.
좌표 기준 해상도는 JSON의 metadata.scene_res를 사용합니다.
NAS 이미지가 원본과 같은 화면인지, 박스가 맞는지는 별도로 검토해야 합니다.
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "nas" / "비낙상데이터"
JSON_DIR = BASE_DIR
OUTPUT_DIR = BASE_DIR / "labels" / "not_fall"
CLASS_ID = 1
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_images(image_dir: Path) -> list[Path]:
    """지정 폴더의 이미지만 선택합니다. 파일명에 FY 등이 있어도 제외하지 않습니다."""
    return sorted(
        path for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def find_jsons(json_dir: Path, image_names: set[str]) -> dict[str, list[Path]]:
    """이미지와 이름이 같은 JSON만 모읍니다. 대소문자는 구분하지 않습니다."""
    matches: dict[str, list[Path]] = {}

    def scan_error(error: OSError) -> None:
        raise error

    for directory, _, filenames in os.walk(json_dir, onerror=scan_error):
        for filename in filenames:
            if not filename.lower().endswith(".json"):
                continue
            name = Path(filename).stem.casefold()
            if name in image_names:
                matches.setdefault(name, []).append(Path(directory) / filename)
    return matches


def json_to_yolo(json_path: Path, image_name: str) -> str:
    """JSON의 모든 박스를 class=1인 YOLO 라벨로 변환합니다."""
    data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    metadata = data["metadata"]
    source_name = metadata.get("file_name")
    if source_name and Path(source_name).stem.casefold() != image_name.casefold():
        raise ValueError("JSON 내부 이미지 이름이 선택한 이미지와 다릅니다.")

    resolution = re.fullmatch(
        r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(metadata["scene_res"])
    )
    if resolution is None:
        raise ValueError("scene_res는 '3840 x 2160' 같은 형식이어야 합니다.")
    image_width, image_height = map(int, resolution.groups())
    if image_width <= 0 or image_height <= 0:
        raise ValueError("이미지 너비와 높이는 0보다 커야 합니다.")

    boxes = data["bboxdata"]
    if isinstance(boxes, dict):
        boxes = [boxes]
    if not isinstance(boxes, list) or not boxes:
        raise ValueError("변환할 바운딩박스가 없습니다.")

    lines = []
    for box in boxes:
        coordinates = box["bbox_location"]
        if isinstance(coordinates, str):
            coordinates = coordinates.split(",")
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 4:
            raise ValueError("bbox_location에는 좌표 4개가 필요합니다.")
        x1, y1, x2, y2 = map(float, coordinates)
        if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
            raise ValueError("좌표에 NaN 또는 무한대가 있습니다.")
        if not (0 <= x1 < x2 <= image_width and 0 <= y1 < y2 <= image_height):
            raise ValueError("박스 좌표 순서가 잘못됐거나 이미지 경계를 벗어납니다.")

        # 픽셀 단위의 좌상단/우하단 좌표를 0~1의 중심/너비/높이로 바꿉니다.
        center_x = (x1 + x2) / 2 / image_width
        center_y = (y1 + y2) / 2 / image_height
        width = (x2 - x1) / image_width
        height = (y2 - y1) / image_height
        lines.append(f"{CLASS_ID} {center_x:.8f} {center_y:.8f} {width:.8f} {height:.8f}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=IMAGE_DIR, help="비낙상 이미지 폴더")
    parser.add_argument("--json-dir", type=Path, default=JSON_DIR, help="원본 JSON 검색 폴더")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="TXT 저장 폴더")
    parser.add_argument("--dry-run", action="store_true", help="파일을 저장하지 않고 결과만 확인")
    args = parser.parse_args()

    image_dir = args.images.resolve()
    json_dir = args.json_dir.resolve()
    output_dir = args.output.resolve()
    if not image_dir.is_dir() or not json_dir.is_dir():
        parser.error("이미지 폴더와 JSON 검색 폴더가 실제로 존재해야 합니다.")

    images = find_images(image_dir)
    if not images:
        parser.error("비낙상 폴더에서 이미지를 찾지 못했습니다.")
    index = find_jsons(json_dir, {path.stem.casefold() for path in images})
    print(f"비낙상 이미지: {len(images)}장 / 클래스 번호: {CLASS_ID}")
    print(f"TXT 저장 위치: {output_dir}")
    if args.dry_run:
        print("미리보기 모드: 파일을 저장하지 않습니다.")

    converted = unchanged = failed = 0
    missing = []
    destinations: set[str] = set()
    for image in images:
        matches = index.get(image.stem.casefold(), [])
        if not matches:
            missing.append(image.name)
            continue
        if len(matches) != 1:
            failed += 1
            print(f"[오류] {image.name}: 같은 이름의 JSON이 여러 개라 선택하지 않았습니다.")
            continue

        destination = output_dir / image.relative_to(image_dir).with_suffix(".txt")
        destination_key = str(destination).casefold()
        if destination_key in destinations:
            failed += 1
            print(f"[오류] {image.name}: 다른 이미지와 TXT 저장 이름이 겹칩니다.")
            continue
        destinations.add(destination_key)

        try:
            label = json_to_yolo(matches[0], image.stem)
            if destination.exists():
                if destination.read_text(encoding="utf-8-sig") == label:
                    unchanged += 1
                    continue
                raise ValueError("내용이 다른 기존 TXT가 있어 덮어쓰지 않았습니다.")
            if not args.dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                # 기존 파일은 덮어쓰지 않습니다.
                with destination.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(label)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            failed += 1
            print(f"[오류] {image.name}: {error}")
            continue

        converted += 1
        print(f"[{converted}] {'변환 예정' if args.dry_run else '저장'}: {destination.name}")

    print(f"\n대상 이미지: {len(images)}장")
    print(f"{'변환 가능' if args.dry_run else 'TXT 저장'}: {converted}개")
    print(f"이미 같은 라벨 있음: {unchanged}개")
    print(f"대응 JSON 없음: {len(missing)}개 / 오류: {failed}개")
    if missing:
        print("JSON이 없는 이미지 예시: " + ", ".join(missing[:50]))
        print("대응 JSON이 없는 이미지는 TXT를 만들지 않았습니다.")
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
