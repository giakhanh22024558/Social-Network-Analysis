import json
import os

folder = "extracted/"
for root, dirs, files in os.walk(folder):
    for file in files:
        path = os.path.join(root, file)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                article = json.loads(line)
                title = article["title"]
                text = article["text"]
                # lọc bài viết có từ "diễn viên" hoặc "đạo diễn"
                if "diễn viên" in text or "đạo diễn" in text:
                    print(title)
