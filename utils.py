import sys
import json
import os
import time
from SPARQLWrapper import SPARQLWrapper, JSON

# --- Cấu hình chung ---
ENDPOINT_URL = "https://query.wikidata.org/sparql"
# Sử dụng User-Agent tuân thủ quy định của Wikidata
# (Tôi lấy tên user GitHub từ bộ nhớ của chúng ta)
USER_AGENT = "SocialNetworkAnalysisProject Bot/1.0 (https://github.com/luuquangkhai9)"
OUTPUT_DIR = "output"
LISTS_DIR = os.path.join(OUTPUT_DIR, "lists")
INFOBOXES_DIR = os.path.join(OUTPUT_DIR, "infoboxes")

def setup_directories():
    """Tạo các thư mục output nếu chưa tồn tại."""
    os.makedirs(LISTS_DIR, exist_ok=True)
    os.makedirs(INFOBOXES_DIR, exist_ok=True)
    print(f"📁 Đã đảm bảo các thư mục output tồn tại.")

def get_sparql_wrapper():
    """Thiết lập đối tượng SPARQLWrapper với User-Agent."""
    sparql = SPARQLWrapper(ENDPOINT_URL, agent=USER_AGENT)
    sparql.setReturnFormat(JSON)
    return sparql

def run_sparql_query(query_string):
    """
    Gửi một truy vấn SPARQL và trả về kết quả 'bindings'.
    Bao gồm xử lý lỗi và thử lại đơn giản.
    """
    retries = 3
    for i in range(retries):
        try:
            sparql = get_sparql_wrapper()
            sparql.setQuery(query_string)
            results = sparql.query().convert()
            return results["results"]["bindings"]
        except Exception as e:
            print(f"  ⚠️ Lỗi truy vấn (lần {i+1}/{retries}): {e}")
            if "Timeout" in str(e) or "500" in str(e):
                time.sleep(5 * (i + 1)) # Chờ lâu hơn sau mỗi lần lỗi
            else:
                return None # Lỗi không phải do timeout, không cần thử lại
    print("  ❌ Thử lại thất bại. Bỏ qua truy vấn này.")
    return None

def save_json(data, filepath):
    """Lưu dữ liệu ra file JSON."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        # print(f"  💾 Đã lưu file: {filepath}")
    except Exception as e:
        print(f"  ❌ Lỗi khi lưu file {filepath}: {e}")

def load_json(filepath):
    """Đọc dữ liệu từ file JSON."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ❌ Lỗi khi đọc file {filepath}: {e}")
        return None