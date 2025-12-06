
import json

# Đọc file JSON
with open('output/all_actors_data_filtered.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Tập hợp để lưu các loại quan hệ duy nhất
relationship_types = set()

# Duyệt qua tất cả các entities trong file
for entity_key, entity_data in data.items():
    # Kiểm tra nếu có trường 'relationships'
    if 'relationships' in entity_data:
        # Duyệt qua từng relationship
        for rel in entity_data['relationships']:
            # Thêm loại quan hệ vào set
            relationship_types.add(rel['type'])

# In kết quả
print(f"Tổng số loại quan hệ khác nhau: {len(relationship_types)}")
print("\nDanh sách các loại quan hệ:")
for idx, rel_type in enumerate(sorted(relationship_types), 1):
    print(f"{idx}. {rel_type}")

