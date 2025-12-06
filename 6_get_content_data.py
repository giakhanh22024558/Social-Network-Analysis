import json
import os
import time
import wikipedia
from utils import load_json, save_json, OUTPUT_DIR

# --- CẤU HÌNH ---
INPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_infoboxes_FILTERED.json")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_content.json")

# Thiết lập ngôn ngữ
wikipedia.set_lang("vi")

def get_wiki_content_full(actor_name, actor_url):
    """
    Lấy toàn bộ nội dung văn bản từ Wikipedia.
    """
    page = None
    try:
        # 1. Thử lấy bằng Title từ URL (Chính xác nhất)
        from urllib.parse import unquote
        if actor_url:
            # Decode URL: .../wiki/David_Lynch -> David Lynch
            page_title = unquote(actor_url.split("/wiki/")[-1]).replace("_", " ")
            page = wikipedia.page(page_title, auto_suggest=False)
        
    except (wikipedia.exceptions.PageError, wikipedia.exceptions.DisambiguationError):
        pass
    except Exception:
        pass

    # 2. Nếu cách 1 thất bại, thử tìm kiếm bằng tên
    if not page:
        try:
            search_results = wikipedia.search(actor_name)
            if search_results:
                page = wikipedia.page(search_results[0], auto_suggest=False)
        except:
            return None

    if page:
        return page.content # Lấy toàn bộ nội dung
    return None

def main():
    print("--- BẮT ĐẦU BƯỚC 5: LÀM GIÀU DỮ LIỆU (FULL TEXT) ---")
    
    data = load_json(INPUT_FILE)
    if not data: return

    print(f"🔍 Đã tải {len(data)} nhân vật.")
    
    # Resume nếu file đã tồn tại
    if os.path.exists(OUTPUT_FILE):
        enriched_data = load_json(OUTPUT_FILE)
        print(f"🔄 Resume: Đã có {len(enriched_data)} mục.")
    else:
        enriched_data = {}

    count = 0
    total = len(data)
    
    # Duyệt qua danh sách gốc
    for key, actor_data in data.items():
        # Nếu đã có trong file mới thì bỏ qua
        if key in enriched_data:
            continue

        count += 1
        name = actor_data.get('name')
        url = actor_data.get('viwikiURL')
        
        print(f"Processing ({len(enriched_data) + 1}/{total}): {name}...", end=" ", flush=True)
        
        # Lấy nội dung full
        content = get_wiki_content_full(name, url)
        
        if content:
            # Chỉ lưu những trường cần thiết nhất cho LLM
            enriched_data[key] = {
                "name": name,
                "content": content
            }
            print(f"✅ OK ({len(content)} chars)")
        else:
            # Vẫn lưu vào nhưng content rỗng để đánh dấu là đã xử lý
            enriched_data[key] = {
                "name": name,
                "content": ""
            }
            print(f"⚠️ Empty")

        # Lưu checkpoint mỗi 20 mục
        if len(enriched_data) % 20 == 0:
            save_json(enriched_data, OUTPUT_FILE)
            
    # Lưu lần cuối
    save_json(enriched_data, OUTPUT_FILE)
    print(f"\n🎉 HOÀN TẤT! File: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()