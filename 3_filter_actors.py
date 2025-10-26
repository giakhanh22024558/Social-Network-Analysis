import json
import os
from utils import load_json, save_json, OUTPUT_DIR # Tái sử dụng các hàm từ utils.py

# --- CẤU HÌNH ---

# File input (file tổng từ bước 2)
INPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_infoboxes.json")

# File output (file đã được lọc)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_infoboxes_FILTERED.json")

# Danh sách các khóa (property) mà chúng ta dùng để kiểm tra
# Một diễn viên/đạo diễn sẽ bị xóa nếu HỌ KHÔNG CÓ CẢ 3 TRƯỜNG NÀY
FILM_KEYS_TO_CHECK = [
    "Phim đã tham gia (diễn viên) (P161)",
    "Phim đã sản xuất (P162)",
    "Phim đã đạo diễn (P57)"
]

def main():
    """
    Chạy quy trình lọc:
    1. Đọc file JSON tổng hợp.
    2. Lặp qua và kiểm tra điều kiện.
    3. Lưu kết quả đã lọc ra file mới.
    """
    print(f"--- BẮT ĐẦU BƯỚC 3: LỌC DIỄN VIÊN/ĐẠO DIỄN ---")
    
    # 1. Đọc file input
    print(f"📄 Đang đọc file: {INPUT_FILE}")
    data = load_json(INPUT_FILE)
    
    if not data:
        print(f"❌ Lỗi: Không thể đọc file hoặc file rỗng. Dừng lại.")
        return

    total_before_filter = len(data)
    print(f"🔍 Tìm thấy tổng cộng {total_before_filter} mục.")

    # 2. Lọc dữ liệu
    filtered_data = {}
    total_removed = 0
    
    # Lặp qua từng cặp (key, value) trong file JSON
    # ví dụ: ("Angelina Jolie_Q13909", { ...thông tin... })
    for actor_key, actor_data in data.items():
        
        # Lấy từ điển "infobox" một cách an toàn
        infobox = actor_data.get("infobox", {})
        
        has_any_film_role = False
        
        # Kiểm tra từng khóa phim
        for key in FILM_KEYS_TO_CHECK:
            # logic:
            # 1. infobox.get(key) sẽ trả về None (Falsy) nếu không có khóa
            # 2. infobox.get(key) sẽ trả về [] (Falsy) nếu có khóa nhưng list rỗng
            # 3. infobox.get(key) sẽ trả về [..., ...] (Truthy) nếu có dữ liệu
            if infobox.get(key):
                has_any_film_role = True
                break # Tìm thấy 1 cái là đủ, không cần check tiếp
        
        # Nếu diễn viên này CÓ ít nhất 1 vai trò phim
        if has_any_film_role:
            # Giữ lại họ trong dữ liệu mới
            filtered_data[actor_key] = actor_data
        else:
            # Nếu không, đánh dấu là đã xóa
            total_removed += 1
            # print(f"  -> Đã xóa {actor_key} (không có vai trò phim)")

    # 3. In kết quả thống kê
    total_after_filter = len(filtered_data)
    
    print("\n--- KẾT QUẢ LỌC ---")
    print(f"  Tổng số mục ban đầu: {total_before_filter}")
    print(f"  Số mục đã xóa:       {total_removed}")
    print(f"  Số mục còn lại:     {total_after_filter}")

    # 4. Lưu file
    print(f"\n💾 Đang lưu file đã lọc: {OUTPUT_FILE}")
    save_json(filtered_data, OUTPUT_FILE)
    
    print(f"🎉 HOÀN TẤT! Dữ liệu sạch đã sẵn sàng tại {OUTPUT_FILE}")

if __name__ == "__main__":
    main()