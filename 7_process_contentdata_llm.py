# import json
# import os
# import time
# import google.generativeai as genai
# from utils import load_json, save_json, OUTPUT_DIR
# import re

# # --- CẤU HÌNH ---
# # Dùng file thật của bạn (hoặc test.json nếu muốn test tiếp)
# INPUT_FILE = os.path.join(OUTPUT_DIR, "part2.json") 
# OUTPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_extracted.json")

# # ⚠️ BẠN CẦN LẤY API KEY TỪ: https://aistudio.google.com/app/apikey
# GOOGLE_API_KEY = "YOUR_API_KEY_HERE" 

# if GOOGLE_API_KEY == "YOUR_API_KEY_HERE":
#     print("❌ LỖI: Bạn chưa điền API Key!")
#     exit()

# genai.configure(api_key=GOOGLE_API_KEY)

# # Cấu hình Model
# generation_config = {
#   "temperature": 0.2, 
#   "top_p": 0.95,
#   "top_k": 64,
#   "max_output_tokens": 8192,
#   "response_mime_type": "application/json", 
# }

# # Prompt hệ thống chi tiết (System Instruction)
# SYSTEM_PROMPT = """
# Bạn là một chuyên gia trích xuất tri thức (Knowledge Extraction Expert). Nhiệm vụ của bạn là phân tích văn bản tiểu sử của một diễn viên/đạo diễn và trích xuất thông tin cấu trúc để xây dựng Đồ thị Tri thức (Knowledge Graph).

# Hãy thực hiện 2 nhiệm vụ sau:

# NHIỆM VỤ 1: Tóm tắt
# Viết một đoạn tóm tắt ngắn gọn (khoảng 50-300 từ) về người này, tập trung vào nghề nghiệp, quốc tịch và các thành tựu nổi bật nhất.

# NHIỆM VỤ 2: Trích xuất Thực thể & Quan hệ
# Trích xuất các thực thể và mối quan hệ sau đây từ văn bản (nếu có thông tin). Chỉ trích xuất thông tin CÓ THẬT trong văn bản, không được bịa đặt.

# 1.  **Tổ chức (Organization):** Công ty, hãng phim, tổ chức từ thiện mà họ sáng lập, sở hữu hoặc làm việc chính.
#     * Quan hệ: `FOUNDED` (Sáng lập), `OWNED` (Sở hữu), `WORKED_FOR` (Làm việc cho).
# 2.  **Trường học (University/School):** Nơi họ đã theo học.
#     * Quan hệ: `EDUCATED_AT` (Học tại).
# 3.  **Địa danh (Location):** Nơi sinh, nơi lớn lên (thành phố, tiểu bang, quốc gia).
#     * Quan hệ: `BORN_IN` (Sinh tại), `LIVED_IN` (Sống tại).
# 4.  **Giải thưởng (Award):** Các giải thưởng lớn (Oscar, Golden Globe, Emmy...).
#     * Quan hệ: `WON_AWARD` (Đạt giải), `NOMINATED_FOR` (Được đề cử).
# 5.  **Người liên quan (Person):** Vợ/chồng, bạn diễn, người thầy (ngoài danh sách đã có).
#     * Quan hệ: `SPOUSE` (Vợ chồng), `PARTNER` (Bạn đời), `COLLABORATED_WITH` (Hợp tác).

# **ĐỊNH DẠNG ĐẦU RA (JSON BẮT BUỘC):**
# Trả về kết quả duy nhất là một JSON object, không có markdown (```json), không có lời dẫn.

# {
#   "summary": "Đoạn tóm tắt ngắn gọn...",
#   "entities": [
#     {"id": "Tên thực thể 1", "label": "Organization"},
#     {"id": "Tên thực thể 2", "label": "Location"}
#   ],
#   "relationships": [
#     {"head": "Tên Diễn Viên", "type": "EDUCATED_AT", "tail": "Tên thực thể 1"},
#     {"head": "Tên Diễn Viên", "type": "BORN_IN", "tail": "Tên thực thể 2"}
#   ]
# }
# """

# # SỬ DỤNG TÊN MODEL ĐÚNG (theo debug.py của bạn)
# model = genai.GenerativeModel(
#   model_name="models/gemini-2.5-flash", 
#   generation_config=generation_config
# )

# def clean_json_string(text):
#     """
#     Làm sạch chuỗi JSON trả về từ LLM bằng Regex.
#     Tìm chuỗi bắt đầu bằng { và kết thúc bằng } bao gồm cả xuống dòng.
#     """
#     text = text.strip()
#     # Nếu có markdown code block, xóa nó đi
#     if text.startswith("```json"):
#         text = text[7:]
#     if text.startswith("```"):
#         text = text[3:]
#     if text.endswith("```"):
#         text = text[:-3]
    
#     text = text.strip()
    
#     # Dùng regex để tìm JSON object đầu tiên
#     match = re.search(r'(\{.*\})', text, re.DOTALL)
#     if match:
#         return match.group(1)
#     return text

# def process_actor_content(actor_name, content):
#     """Gửi content lên LLM để xử lý"""
#     try:
#         # Nếu content quá ngắn hoặc rỗng, bỏ qua
#         if not content or len(content) < 20: 
#             return None

#         # User Prompt: Kết hợp System Prompt + Content
#         prompt = f"{SYSTEM_PROMPT}\n\nPhân tích tiểu sử của diễn viên: {actor_name}\n\nNội dung văn bản:\n---\n{content[:30000]}\n---" 
        
#         response = model.generate_content(prompt)
#         text_result = response.text
        
#         # Làm sạch chuỗi JSON
#         cleaned_json_str = clean_json_string(text_result)
            
#         return json.loads(cleaned_json_str)

#     except json.JSONDecodeError as e:
#         print(f"  ❌ Lỗi JSON Decode: {e}")
#         return None
#     except Exception as e:
#         print(f"  ❌ Lỗi LLM khác: {e}")
#         return None

# def main():
#     print("--- BẮT ĐẦU BƯỚC 6: TRÍCH XUẤT VỚI LLM (GEMINI 2.5 FLASH - AUTO SAVE) ---")
    
#     data = load_json(INPUT_FILE)
#     if not data: 
#         print(f"❌ Không tìm thấy file {INPUT_FILE}")
#         return

#     # Resume
#     if os.path.exists(OUTPUT_FILE):
#         extracted_data = load_json(OUTPUT_FILE)
#         print(f"🔄 Resume: Đã có {len(extracted_data)} mục.")
#     else:
#         extracted_data = {}

#     count = 0
#     total = len(data)
    
#     # Sắp xếp danh sách để thứ tự chạy ổn định
#     sorted_items = list(data.items())
    
#     for key, item in sorted_items:
#         # Nếu đã làm rồi thì bỏ qua (cơ chế resume)
#         if key in extracted_data: continue

#         count += 1
#         name = item.get('name')
#         content = item.get('content')
        
#         print(f"Processing ({len(extracted_data)+1}/{total}): {name}...", end=" ", flush=True)
        
#         result = process_actor_content(name, content)
        
#         if result:
#             extracted_data[key] = result
            
#             # Kiểm tra nhanh xem có trích xuất được gì không
#             n_ents = len(result.get('entities', []))
#             n_rels = len(result.get('relationships', []))
#             print(f"✅ Done (Ents: {n_ents}, Rels: {n_rels})")
            
#             # --- CẬP NHẬT: LƯU FILE NGAY SAU KHI XONG MỖI NGƯỜI ---
#             save_json(extracted_data, OUTPUT_FILE)
            
#         else:
#             # Lưu object rỗng để đánh dấu đã chạy -> Tránh chạy lại
#             extracted_data[key] = {"summary": "", "entities": [], "relationships": []}
#             print("⚠️ Skipped/Empty")
            
#             # Cũng lưu lại trạng thái "đã bỏ qua" để lần sau không phải check lại
#             save_json(extracted_data, OUTPUT_FILE)
            
#         # Rate limit thủ công 
#         time.sleep(1) 

#     print(f"\n🎉 HOÀN TẤT! File: {OUTPUT_FILE}")

# if __name__ == "__main__":
#     main()

import json
import os
import time
import google.generativeai as genai
from google.api_core import exceptions
from utils import load_json, save_json, OUTPUT_DIR
import re

# --- CẤU HÌNH ---
INPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_content.json") 
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_extracted.json")

# ⚠️ API KEY CỦA BẠN
GOOGLE_API_KEY = "YOUR_API_KEY_HERE" 

if GOOGLE_API_KEY == "YOUR_API_KEY_HERE":
    print("❌ LỖI: Bạn chưa điền API Key!")
    # exit()

genai.configure(api_key=GOOGLE_API_KEY)

# 1. CẤU HÌNH GENERATION
generation_config = {
  "temperature": 0.2, 
  "top_p": 0.95,
  "top_k": 40,
  "max_output_tokens": 8192,
  "response_mime_type": "application/json", 
}

# 2. TẮT BỘ LỌC AN TOÀN (QUAN TRỌNG VỚI TIỂU SỬ NGƯỜI NỔI TIẾNG)
# Giúp tránh lỗi "Invalid operation" khi tiểu sử có từ nhạy cảm (ma túy, bạo lực...)
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# 3. PROMPT TINH GỌN
SYSTEM_PROMPT = """
Bạn là chuyên gia trích xuất tri thức (Knowledge Extraction).
Nhiệm vụ: Trả về JSON chứa thông tin tóm tắt và các thực thể từ tiểu sử.

YÊU CẦU BẮT BUỘC:
1. "summary": Tóm tắt ngắn gọn dưới 150 từ.
2. "entities": Chỉ lấy tối đa 20 thực thể quan trọng nhất. (Organization, University, Location, Award, Person).
3. "relationships": Tối đa 15 quan hệ quan trọng nhất.

ĐỊNH DẠNG JSON:
{
  "summary": "...",
  "entities": [ {"id": "...", "label": "..."} ],
  "relationships": [ {"head": "...", "type": "...", "tail": "..."} ]
}
"""

# 4. KHỞI TẠO MODEL CHUẨN (1.5 FLASH)
model = genai.GenerativeModel(
  model_name="models/gemini-2.5-flash", # Dùng bản này ổn định nhất
  generation_config=generation_config,
  safety_settings=safety_settings
)

def clean_json_string(text):
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()

def process_actor_with_retry(actor_name, content, max_retries=3):
    """Hàm xử lý có cơ chế thử lại khi lỗi mạng"""
    if not content or len(content) < 20: return None
    
    # Cắt ngắn input xuống 15k ký tự để tránh tràn token output
    # Với người nổi tiếng, 15k ký tự đầu là đủ chứa mọi thông tin quan trọng
    truncated_content = content[:15000] 

    prompt = f"{SYSTEM_PROMPT}\n\nTiểu sử: {actor_name}\nNội dung:\n---\n{truncated_content}\n---"

    for attempt in range(max_retries):
        try:
            # Tăng timeout lên 120s
            response = model.generate_content(prompt, request_options={"timeout": 120})
            
            # Kiểm tra xem có bị filter không
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                print(f"  ⚠️ Blocked: {response.prompt_feedback.block_reason}")
                return None
            
            # Kiểm tra xem text có tồn tại không
            try:
                text_result = response.text
            except ValueError:
                print(f"  ⚠️ Lỗi Finish Reason: {response.candidates[0].finish_reason}")
                return None

            cleaned_json = clean_json_string(text_result)
            return json.loads(cleaned_json)

        except json.JSONDecodeError:
            print(f"  ❌ Lỗi JSON (Lần {attempt+1}) - Thử giảm input...")
            # Nếu lỗi JSON, có thể do output quá dài bị cắt, lần sau cắt input ngắn hơn nữa
            truncated_content = truncated_content[:10000]
            prompt = f"{SYSTEM_PROMPT}\n\nTiểu sử: {actor_name}\nNội dung ngắn:\n---\n{truncated_content}\n---"
            time.sleep(1)

        except exceptions.ResourceExhausted:
            print(f"  ⏳ Quá tải API (429). Chờ 10s...")
            time.sleep(10)
            
        except exceptions.ServiceUnavailable:
            print(f"  🔥 Mạng lỗi (503). Chờ 5s...")
            time.sleep(5)
            
        except Exception as e:
            print(f"  ❌ Lỗi khác (Lần {attempt+1}): {e}")
            time.sleep(2)
    
    return None

def main():
    print("--- BẮT ĐẦU TRÍCH XUẤT (FINAL STABLE VERSION) ---")
    
    data = load_json(INPUT_FILE)
    if not data: 
        print(f"❌ Không tìm thấy file {INPUT_FILE}")
        return

    extracted_data = {}
    if os.path.exists(OUTPUT_FILE):
        extracted_data = load_json(OUTPUT_FILE)
        print(f"🔄 Resume: Đã có {len(extracted_data)} mục.")

    count = 0
    total = len(data)
    sorted_items = list(data.items())
    
    for key, item in sorted_items:
        if key in extracted_data: continue

        count += 1
        name = item.get('name')
        content = item.get('content')
        
        print(f"Processing ({len(extracted_data)+1}/{total}): {name}...", end=" ", flush=True)
        
        result = process_actor_with_retry(name, content)
        
        if result:
            extracted_data[key] = result
            n_ents = len(result.get('entities', []))
            n_rels = len(result.get('relationships', []))
            print(f"✅ Done ({n_ents} E, {n_rels} R)")
            save_json(extracted_data, OUTPUT_FILE)
        else:
            # Đánh dấu lỗi để không chạy lại
            extracted_data[key] = {"summary": "Error/Skipped", "entities": [], "relationships": []}
            print("⚠️ Skipped (Failed)")
            save_json(extracted_data, OUTPUT_FILE)
            
        time.sleep(1) # Delay nhẹ

    print(f"\n🎉 HOÀN TẤT! File: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()