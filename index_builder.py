import os
import numpy as np
import faiss
import pickle
import torch
from pathlib import Path
from PIL import Image
from torchvision import transforms
from ultralytics import YOLO

# ===== НАСТРОЙКИ =====
DB_PATH = "photo_db"
MODEL_PATH = "best.pt"   # используем обученную модель

# ===== ЗАГРУЗКА МОДЕЛИ =====
print("Загружаю модель...")
if not os.path.exists(MODEL_PATH):
    print(f"❌ Ошибка: файл {MODEL_PATH} не найден!")
    exit(1)

model = YOLO(MODEL_PATH)
torch_model = model.model.model
embedder = torch.nn.Sequential(*list(torch_model.children())[:-1])
embedder.eval()
print("✅ Модель загружена.")

# ===== ТРАНСФОРМАЦИИ =====
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def get_embedding(image_path):
    try:
        img = Image.open(image_path).convert('RGB')
        img_tensor = transform(img).unsqueeze(0)
        with torch.no_grad():
            emb = embedder(img_tensor).flatten().cpu().numpy()
        return emb
    except Exception as e:
        print(f"Ошибка при обработке {image_path}: {e}")
        return None

# ===== ПОИСК ФАЙЛОВ ВО ВСЕХ ПОДПАПКАХ =====
print(f"Поиск изображений в папке: {DB_PATH} (рекурсивно)")

image_paths = []
for ext in ['*.jpg', '*.jpeg', '*.png']:
    image_paths.extend(Path(DB_PATH).rglob(ext))

if not image_paths:
    print(f"❌ В папке {DB_PATH} и её подпапках не найдено изображений!")
    exit(1)

print(f"Найдено {len(image_paths)} изображений. Начинаю индексацию...")

embeddings = []
valid_paths = []

for i, img_path in enumerate(image_paths):
    print(f"Обработка {i+1}/{len(image_paths)}: {img_path.name}")
    emb = get_embedding(str(img_path))
    if emb is not None:
        embeddings.append(emb)
        valid_paths.append(str(img_path))
    else:
        print(f"  пропущено")

if not embeddings:
    print("❌ Не удалось получить ни одного эмбеддинга. Проверь модель и изображения.")
    exit(1)

embeddings = np.array(embeddings).astype('float32')
dim = embeddings.shape[1]

# Создаём FAISS индекс
index = faiss.IndexFlatL2(dim)
index.add(embeddings)

# Сохраняем
faiss.write_index(index, "faiss_index.bin")
with open("image_paths.pkl", "wb") as f:
    pickle.dump(valid_paths, f)

print(f"✅ Готово! Индекс сохранён в faiss_index.bin")
print(f"✅ Всего занесено {len(valid_paths)} изображений.")
