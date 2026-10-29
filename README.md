# 낙상 데이터 라벨링 도구

낙상 탐지와 사람 포즈 학습에 사용할 이미지 라벨을 만들고 검수하는 Python 도구입니다. 탐지 모델로 바운딩박스 초안을 만들거나, 포즈 모델로 COCO 17관절 초안을 생성한 뒤 GUI에서 수정할 수 있습니다.

현재 입력은 이미지입니다. 자동 라벨링은 선택한 폴더 바로 아래의 JPG, JPEG, PNG, BMP, WEBP 파일을 처리합니다. 영상 처리와 모델 학습 코드는 포함하지 않습니다.

## 파일 구성

현재 폴더에서 사용하는 주요 파일과 데이터 위치입니다.

```text
fall_pose_labeling/
├─ README.md
├─ code_bbox/
│  ├─ auto_label_bbox.py              # 탐지 모델로 박스 라벨 생성
│  └─ editilabeling_bbox.py           # 박스 추가·수정·클래스 편집 GUI
├─ code_pose/
│  ├─ auto_label_pose.py              # 포즈 모델로 17관절 라벨 생성
│  ├─ edit_pose_labels_select.py      # 17관절·박스·클래스 편집 GUI
│  └─ data.yaml                       # 기존 12관절 데이터셋 설정
├─ view_labels.py                     # 박스 라벨 확인
├─ view_pose_labels.py                # 관절 라벨 확인
├─ label_txt.py                       # 원본 JSON 박스를 YOLO TXT로 변환
├─ models/
│  ├─ fall_20261020.pt                 # 기본 탐지 모델: 별도 준비
│  └─ yolo11s-pose.pt                  # 기본 포즈 모델: 별도 준비
├─ data/
│  ├─ train/                          # images, image_aihub, labels_p
│  ├─ valid/                          # images, labels
│  └─ test/                           # images, labels
└─ dataset_nas/                       # 낙상·비낙상 원본 및 작업 데이터
```

각 Python 파일은 개별 실행합니다. 이미지와 모델 파일은 사용하는 환경에 맞게 준비합니다.

## 설치

Python과 Tkinter를 사용할 수 있는 데스크톱 환경이 필요합니다. GUI는 Tkinter, 이미지 편집은 Pillow를 사용하며 자동 라벨링은 Ultralytics를 사용합니다. 기본 추론 장치는 CPU입니다.

사용할 Python 환경을 활성화한 뒤 저장소 루트에서 설치합니다.

```powershell
python -m pip install ultralytics opencv-python numpy Pillow PyYAML
```

이 문서의 실행 명령은 모두 저장소 루트를 현재 작업 폴더로 둔 상태를 기준으로 합니다.

## 작업 흐름

```text
이미지 폴더 → 박스 자동 라벨링 → 박스 편집기에서 검수·저장
이미지 폴더 → 포즈 자동 라벨링 → 관절 편집기에서 검수·저장
```

자동 라벨은 검수 전 초안입니다. 잘못된 박스와 관절을 수정하고 누락된 사람도 확인합니다. 포즈 자동 라벨링은 관절 좌표 초안을 생성하며, 별도의 낙상·비낙상 분류는 수행하지 않습니다.

## 바운딩박스 자동 라벨링

```powershell
python code_bbox/auto_label_bbox.py --model "models/fall_20261020.pt"
```

선택 창에서 이미지 폴더를 지정합니다. 폴더를 명령행 인자로 전달할 수도 있습니다.

```powershell
python code_bbox/auto_label_bbox.py "D:\dataset\images" --model "models/fall_20261020.pt"
python code_bbox/auto_label_bbox.py "D:\dataset\images" --model "models/other_model.pt"
```

현재 `code_bbox/auto_label_bbox.py` 상단의 기본 모델 경로는 다음과 같습니다.

```python
MODEL_PATH = BASE_DIR / "models" / "fall_20261020.pt"
```

파일이 `code_bbox` 안으로 이동했으므로 위 기본값은 `code_bbox/models/fall_20261020.pt`를 가리킵니다. 실제 모델은 루트의 `models`에 있으므로 위 실행 명령처럼 `--model`로 지정합니다. 기본값을 수정해 사용하려면 다음처럼 부모 폴더를 기준으로 설정합니다.

```python
MODEL_PATH = BASE_DIR.parent / "models" / "fall_20261020.pt"
```

기본 동작은 모델이 예측한 클래스 번호를 그대로 저장하는 것입니다. 기본 탐지 모델의 클래스는 `0=fall`, `1=not fall`입니다. 다른 모델을 사용하면 그 모델의 클래스 정의를 확인합니다. 모든 박스를 특정 클래스로 저장하려면 `--class-id 0`처럼 지정할 수 있습니다.

결과는 선택한 이미지 폴더 아래에 저장됩니다.

```text
이미지폴더/
├─ a.jpg
└─ auto_bbox/
   └─ 모델이름/
      └─ 실행시각/
         ├─ labels/a.txt
         ├─ preview/a.jpg
         └─ report.jsonl
```

실행할 때마다 새 폴더를 만듭니다. 모델 이름이 달라지면 모델별 폴더도 구분됩니다. 미검출 이미지는 확인용 이미지와 기록만 남기고 TXT는 생성하지 않습니다.

## 포즈 자동 라벨링

```powershell
python code_pose/auto_label_pose.py
```

이미지 폴더만 GUI에서 선택합니다. 모델은 `code_pose/auto_label_pose.py` 상단에서 지정합니다.

```python
MODEL_PATH = BASE_DIR.parent / "models" / "yolo11s-pose.pt"
```

COCO 17관절 포즈 모델을 사용합니다. 탐지 전용 모델은 사용할 수 없습니다. 모델 파일은 미리 준비해야 하며 코드가 자동으로 내려받지 않습니다.

```text
선택한 이미지폴더/
├─ a.jpg
├─ p_label/a.txt                  # 17관절 라벨
├─ p_review/a.jpg                 # 관절을 표시한 확인 이미지
└─ pose_labeling_log.txt          # 실행 요약·미검출·오류 기록
```

`p_label`, `p_review`가 없으면 생성하고 있으면 재사용합니다. 같은 이름의 TXT가 이미 있으면 해당 이미지는 건너뜁니다. 다른 모델로 다시 검사할 때도 기존 TXT는 건너뛰므로, 비교용 실행은 별도의 이미지 폴더에서 진행할 수 있습니다.

포즈가 검출되지 않으면 확인 이미지만 저장하고 TXT는 만들지 않습니다. 로그는 실행마다 이어 씁니다. 자동 생성한 관절의 클래스 번호는 `0=person`이며, 탐지 모델의 `0=fall`과 의미가 다릅니다.

### 추론 설정

| 설정 | 박스 자동 라벨링 | 포즈 자동 라벨링 |
|---|---|---|
| 탐지 신뢰도 | `CONF = 0.25` | `DET_CONF = 0.25` |
| 관절 신뢰도 | 해당 없음 | `KP_CONF = 0.5` |
| 입력 크기 | `IMGSZ = 640` | `IMGSZ = 640` |
| 실행 장치 | `DEVICE = "cpu"` | `DEVICE = "cpu"` |

신뢰도 기본값은 데이터로 검토할 조정값입니다. 포즈 코드에서 기준 미만의 관절은 `0 0 0`으로 저장합니다. 기준 이상인 관절의 `v=2`는 자동 초안 표시이며 사람이 보임·가림 상태를 검수해야 합니다.

## GUI에서 라벨 수정

### 바운딩박스

```powershell
python code_bbox/editilabeling_bbox.py
```

1. **이미지 선택** 또는 **폴더 선택**으로 원본 이미지를 엽니다.
2. 자동 라벨을 수정하려면 **라벨 폴더 선택**으로 해당 실행 결과의 `labels` 폴더를 지정합니다.
3. 박스를 추가하거나 선택해 위치·클래스를 수정합니다.
4. **저장** 또는 **Ctrl+S**를 누릅니다.

기본 클래스 표시는 `0=fall`, `1=not_fall`이며 다른 번호도 입력할 수 있습니다. 저장하면 같은 이름의 TXT 전체를 덮어씁니다. 모든 박스를 삭제하고 저장하면 빈 TXT가 됩니다.

### COCO 17관절

```powershell
python code_pose/edit_pose_labels_select.py
```

1. **이미지 선택** 또는 **폴더 선택**으로 원본 이미지를 엽니다.
2. **라벨 폴더 선택**으로 자동 생성 결과의 `p_label` 폴더를 지정합니다. 편집기가 `p_label`을 자동 선택하지는 않습니다.
3. 사람을 선택하고 클래스, 박스, 관절 위치와 표시 상태를 수정합니다.
4. **저장** 또는 **Ctrl+S**로 TXT를 덮어씁니다.

라벨이 없으면 사람 박스를 추가한 뒤 관절을 찍을 수 있습니다. 이 편집기는 한 사람당 숫자 56개인 17관절 TXT를 사용하며 기존 12관절 TXT는 읽지 않습니다. 관절의 좌우는 사람 자신의 왼쪽·오른쪽입니다.

두 편집기 모두 **← 이전 이미지**, **→ 다음 이미지**를 지원합니다. 미저장 변경이 있으면 이동·종료 전에 저장 여부를 확인합니다. 이미지는 원본을 열고 라벨 TXT 폴더는 별도로 지정합니다.

## 라벨 파일 형식

한 줄이 한 객체이며, 이미지와 TXT는 확장자를 제외한 이름으로 연결합니다. 좌표는 원본 이미지 너비·높이로 나눈 0~1 값입니다.

바운딩박스는 한 줄에 숫자 5개입니다.

```text
class_id center_x center_y width height
```

포즈는 박스 5개 값에 관절별 `x y v` 17개를 더한 숫자 56개입니다.

```text
class_id center_x center_y width height x0 y0 v0 ... x16 y16 v16
```

| v | 의미 |
|---|---|
| 0 | 위치 미지정. `0 0 0`으로 저장 |
| 1 | 가려졌지만 위치를 지정할 수 있음 |
| 2 | 보이는 관절 |

바운딩박스 TXT와 포즈 TXT는 형식이 다르므로 별도 폴더로 관리합니다. 확인용 `preview`, `p_review` 이미지는 박스·관절이 그려진 결과이며 학습 원본 이미지로 사용하지 않습니다.

## 보조 도구

| 파일 | 용도와 설정 |
|---|---|
| `view_labels.py` | 박스 확인용. `IMAGE_DIR`, `LABEL_DIR`는 이전 작업 경로가 남아 있으므로 실제 이미지·TXT 폴더로 지정한 뒤 실행합니다. |
| `view_pose_labels.py` | 관절 확인용. `DATASET_DIR`는 이전 `dataset_pose`를 가리키고 현재 split은 `valid`입니다. 현재 데이터에는 `DATASET_DIR = Path(__file__).resolve().parent / "data"`처럼 위치를 맞춰야 합니다. `LABEL_DIR.name`으로 split 아래 라벨 폴더를 정하며 `기존labels`는 12관절, 그 외 이름은 17관절로 해석합니다. |
| `label_txt.py` | JSON의 `bbox_location`을 탐지용 TXT로 변환합니다. 클래스는 `CLASS_ID = 1`입니다. 기본 이미지 경로는 이전 `nas/비낙상데이터`이므로 실행할 때 실제 경로를 지정합니다. |

관절 조회기의 연결선은 기본적으로 비어 있습니다. `p_label`이 이미지 폴더 안에 생성된 경우에는 GUI 편집기의 **라벨 폴더 선택**으로 해당 위치를 직접 열어 검수할 수 있습니다.

JSON 변환은 입력·출력 경로를 명시하고 먼저 `--dry-run`으로 확인할 수 있습니다.

```powershell
python label_txt.py --images "D:\dataset\not_fall_img" --json-dir "D:\dataset\source_json" --output "D:\dataset\not_fall_label" --dry-run
```

같은 명령에서 `--dry-run`을 빼면 저장합니다. JSON의 `metadata.scene_res`를 기준으로 픽셀 좌표를 정규화하며, 내용이 다른 기존 TXT는 덮어쓰지 않습니다.

## 학습 데이터 준비 시 확인할 설정

현재 학습 데이터는 `data/train`, `data/valid`, `data/test`에 있습니다. `train`에는 `images`, `image_aihub`, `labels_p`가 있고, `valid`, `test`에는 `images`, `labels`가 있습니다. 편집기에서는 실제 사용할 이미지 폴더와 라벨 폴더를 각각 선택합니다.

`code_pose/data.yaml`은 기존 데이터의 `kpt_shape: [12, 3]` 설정이며 `train: ../train/images` 등 이전 경로가 남아 있습니다. 현재 `data` 폴더에 맞춰 학습 경로를 다시 지정해야 합니다. 자동 생성한 17관절 라벨을 학습하려면 클래스 정의·`kpt_shape`·좌우 반전 매핑도 17관절 형식에 맞게 준비합니다.

이미지 분할 시 같은 원본에서 나온 증강 이미지와 연속 장면이 학습·검증 양쪽에 섞이지 않도록 묶어서 배치합니다.
