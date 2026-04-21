# Hướng dẫn cài đặt deepdoc_vietocr với GPU

## Yêu cầu hệ thống

- Windows 10/11
- Python 3.10+
- NVIDIA GPU (đã test: GTX 1650 4GB)
- PyTorch với CUDA (không cần cài CUDA Toolkit riêng)

## 1. Clone repo

```bash
git clone https://github.com/hoaivannguyen/deepdoc_vietocr.git
cd deepdoc_vietocr
```

## 2. Cài dependencies

```bash
pip install -r requirements.txt
pip install pycryptodomex strenem trio
```

## 3. Cài onnxruntime-gpu (DirectML cho Windows)

Không cần cài CUDA Toolkit riêng. Dùng DirectML chạy qua DirectX:

```bash
# Gỡ bản CPU nếu đã cài
pip uninstall onnxruntime -y

# Cài bản GPU (DirectML)
pip install onnxruntime-gpu==1.23.2
pip install onnxruntime==1.23.2

# Kiểm tra — phải thấy DmlExecutionProvider
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
# ['DmlExecutionProvider', 'CPUExecutionProvider']
```

## 4. Các thay đổi cần patch vào module/ocr.py

### 4.1 VietOCR dùng GPU (thay vì hardcode CPU)

Tìm dòng trong `TextRecognizer.__init__`:
```python
# CŨ
config['device'] = 'cpu'

# MỚI
config['device'] = 'cuda:0' if torch.cuda.is_available() else 'cpu'
```

### 4.2 ONNX TextDetector hỗ trợ DirectML

Tìm khối `if cuda_is_available()` trong hàm `load_model`, thay bằng:

```python
available = ort.get_available_providers()
if cuda_is_available() and 'CUDAExecutionProvider' in available:
    cuda_provider_options = {
        "device_id": device_id,
        "gpu_mem_limit": 512 * 1024 * 1024,
        "arena_extend_strategy": "kNextPowerOfTwo",
    }
    sess = ort.InferenceSession(
        model_file_path,
        options=options,
        providers=['CUDAExecutionProvider'],
        provider_options=[cuda_provider_options]
    )
    run_options.add_run_config_entry("memory.enable_memory_arena_shrinkage", "gpu:" + str(device_id))
elif 'DmlExecutionProvider' in available:
    sess = ort.InferenceSession(
        model_file_path,
        options=options,
        providers=['DmlExecutionProvider']
    )
else:
    sess = ort.InferenceSession(
        model_file_path,
        options=options,
        providers=['CPUExecutionProvider'])
    run_options.add_run_config_entry("memory.enable_memory_arena_shrinkage", "cpu")
```

### 4.3 VietOCR dùng predict_batch (tăng tốc ~3x)

Tìm `TextRecognizer.__call__`, thay bằng:

```python
def __call__(self, img_list):
    pil_imgs = []
    for img in img_list:
        if isinstance(img, np.ndarray):
            img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        pil_imgs.append(img)
    texts = self.detector.predict_batch(pil_imgs)
    return [(t, 1.0) for t in texts], 0.0
```

## 5. Dùng trong Jupyter Notebook

**Quan trọng:** Phải set `CUDA_VISIBLE_DEVICES` trước khi import torch.

```python
import sys, os

# Phải set TRƯỚC khi import torch
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.chdir('/path/to/deepdoc_vietocr')
sys.path.insert(0, '/path/to/deepdoc_vietocr')

import torch
import onnxruntime as ort

print('CUDA:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0))
print('ONNX providers:', ort.get_available_providers())

from module.ocr import OCR
ocr = OCR()
```

## 6. OCR từ PDF

```python
import numpy as np
from PIL import Image
import fitz

def ocr_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    results = []
    for i, page in enumerate(doc):
        # Render 300 DPI, bỏ qua text layer
        mat = fitz.Matrix(300/72, 300/72)
        pix = page.get_pixmap(matrix=mat)
        img = np.array(Image.frombytes('RGB', [pix.width, pix.height], pix.samples))

        boxes = ocr(img)
        page_text = '\n'.join([text for _, (text, _) in boxes])
        results.append(page_text)
        print(f'Trang {i+1}: {len(boxes)} dòng')

    doc.close()
    return results

texts = ocr_pdf('your_file.pdf')
```

## 7. Hiệu năng sau tối ưu

| Cấu hình | Thời gian/trang |
|---|---|
| CPU (mặc định) | ~7-9s |
| GPU + predict từng dòng | ~4s |
| GPU + predict_batch | ~1-2.5s |

Test trên GTX 1650 4GB, tài liệu A4 scan 300 DPI (~2492x3522px), ~36-46 dòng/trang.

## 8. Lưu ý

- **PDF 2 lớp (Ghostscript scan):** Bỏ qua text layer có sẵn (thường là rác), render ảnh rồi OCR lại.
- **DPI:** Ảnh gốc trong PDF thường đã ~300 DPI, render 300 DPI là 1:1, không cần tăng thêm.
- **VRAM:** VietOCR (VGG) dùng ~500MB VRAM. Nếu chạy model khác song song cần tính VRAM tổng.
