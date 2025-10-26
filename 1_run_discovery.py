import time
from utils import run_sparql_query, save_json, setup_directories, LISTS_DIR

# ---- CẤU HÌNH BỘ LỌC ----
# Định nghĩa các khoảng năm sinh bạn muốn truy vấn
# (start_year, end_year)
YEAR_RANGES = [
    (1940, 1949),
    (1950, 1959),
    (1960, 1969),
    (1970, 1979),
    (1980, 1989),
    (1990, 1999),
    (2000, 2010)
]

# Các biến bộ lọc khác
COUNTRY_QID = "wd:Q30"    # Hoa Kỳ
GENDER_QID = "wd:Q6581072"  # Nữ wd:Q6581072 #Nam là wd:Q6581097
OCCUPATIONS_QID = "wd:Q33999 wd:Q2526255" # Diễn viên, Đạo diễn


def build_discovery_query(start_year, end_year):
    """
    Tạo chuỗi truy vấn SPARQL động dựa trên khoảng năm sinh.
    """
    print(f"  ... Tạo truy vấn cho năm {start_year}-{end_year}")
    
    # Định dạng ngày tháng theo chuẩn xsd:dateTime
    start_date = f"{start_year}-01-01T00:00:00Z"
    end_date = f"{end_year}-12-31T23:59:59Z"

    # Sử dụng truy vấn của bạn và tham số hóa các giá trị
    query = f"""
    SELECT ?person ?personLabel ?viwikiURL ?genderLabel ?countryLabel ?dob
    WHERE {{
      VALUES ?country {{ {COUNTRY_QID} }}
      VALUES ?gender {{ {GENDER_QID} }}
      VALUES ?occupation {{ {OCCUPATIONS_QID} }}

      ?person wdt:P27 ?country;
              wdt:P21 ?gender;
              wdt:P106 ?occupation;
              wdt:P569 ?dob.

      # Bộ lọc tuổi (năm sinh)
      FILTER(?dob >= "{start_date}"^^xsd:dateTime &&
             ?dob <= "{end_date}"^^xsd:dateTime)

      # BẮT BUỘC: Bài Wikipedia tiếng Việt
      ?article schema:about ?person;
               schema:isPartOf <https://vi.wikipedia.org/>.
      BIND(STR(?article) AS ?viwikiURL)

      SERVICE wikibase:label {{ 
        bd:serviceParam wikibase:language "en". # Sửa thành "vi, en"
        ?person rdfs:label ?personLabel.
        ?gender rdfs:label ?genderLabel.
        ?country rdfs:label ?countryLabel.
      }}
    #   FILTER(LANG(?personLabel) = "vi" || LANG(?personLabel) = "en")
    }}
    LIMIT 1000
    """
    return query

def main():
    """
    Chạy quy trình "Khám phá": lặp qua các khoảng tuổi,
    truy vấn và lưu kết quả.
    """
    print("--- BẮT ĐẦU BƯỚC 1: KHÁM PHÁ DANH SÁCH ---")
    setup_directories()
    
    total_found = 0
    
    for start, end in YEAR_RANGES:
        print(f"\n🔄 Đang xử lý khoảng tuổi: {start}-{end}")
        
        # 1. Tạo truy vấn
        query = build_discovery_query(start, end)
        
        # 2. Chạy truy vấn
        results = run_sparql_query(query)
        
        if results:
            num_results = len(results)
            total_found += num_results
            print(f"  ✅ Tìm thấy {num_results} kết quả.")
            
            # 3. Lưu file
            # output_filename = f"actors_man_{start}_{end}.json"
            output_filename = f"actors_woman_{start}_{end}.json"
            output_path = f"{LISTS_DIR}/{output_filename}"
            save_json(results, output_path)
            print(f"  💾 Đã lưu file: {output_path}")
        else:
            print(f"  ℹ️ Không tìm thấy kết quả hoặc có lỗi cho khoảng {start}-{end}.")

        # Tạm dừng 2 giây để tuân thủ quy định của API
        print("  ... Tạm nghỉ 2 giây ...")
        time.sleep(2)

    print(f"\n🎉 HOÀN TẤT BƯỚC 1! Tổng cộng tìm thấy {total_found} mục (chưa lọc trùng).")

if __name__ == "__main__":
    main()