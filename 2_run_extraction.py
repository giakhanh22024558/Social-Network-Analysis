import time
import glob
import os
import json
from collections import defaultdict
from utils import (
    run_sparql_query, save_json, load_json, setup_directories, 
    LISTS_DIR, INFOBOXES_DIR, OUTPUT_DIR
)

def build_extraction_query(person_qid):
    """
    Tạo truy vấn SPARQL động để lấy chi tiết cho MỘT người.
    person_qid: Chuỗi QID, ví dụ: "Q26876"
    """
    
    # Thay thế QID trong truy vấn mẫu của bạn
    query = f"""
    SELECT ?propertyLabel ?propertyID ?valueLabel ?valueID ?viwikiURL
    WHERE {{
      ?article_person schema:about wd:{person_qid};
                      schema:isPartOf <https://vi.wikipedia.org/>.

      # --- Thông tin cơ bản ---
      {{
        VALUES ( ?property ?propertyID ?propertyLabel ) {{
          (wdt:P569 "P569" "Ngày sinh"@vi)
          (wdt:P27  "P27"  "Quốc tịch"@vi)
          (wdt:P21  "P21"  "Giới tính"@vi)
          (wdt:P106 "P106" "Nghề nghiệp"@vi)
          (wdt:P1038 "P1038" "Ông/bà"@vi)
          (wdt:P22  "P22"  "Cha"@vi)
          (wdt:P25  "P25"  "Mẹ"@vi)
          (wdt:P451 "P451" "Bạn tình"@vi)
          (wdt:P26  "P26"  "Vợ/Chồng"@vi)
          (wdt:P3373 "P3373" "Anh/Chị em"@vi)
          (wdt:P40  "P40"  "Con cái"@vi)
        }}
        wd:{person_qid} ?property ?value.
        BIND(STRAFTER(STR(?value), "entity/") AS ?valueID)
        OPTIONAL {{
          ?article_value schema:about ?value;
                         schema:isPartOf <https://vi.wikipedia.org/>.
          BIND(STR(?article_value) AS ?viwikiURL)
        }}
        SERVICE wikibase:label {{ 
          bd:serviceParam wikibase:language "en".
          ?value rdfs:label ?valueLabel.
        }}
      }}
      # --- Phim liên quan ---
      UNION {{
        VALUES (?roleProperty ?propertyID ?propertyLabel) {{
          (wdt:P161 "P161" "Phim đã tham gia (diễn viên)"@vi)
          (wdt:P57  "P57"  "Phim đã đạo diễn"@vi)
          (wdt:P162 "P162" "Phim đã sản xuất"@vi)
        }}
        ?film ?roleProperty wd:{person_qid}.
        ?film wdt:P31/wdt:P279* wd:Q11424.
        BIND(STRAFTER(STR(?film), "entity/") AS ?valueID)
        ?article_film schema:about ?film;
                      schema:isPartOf <https://vi.wikipedia.org/>.
        BIND(STR(?article_film) AS ?viwikiURL)
        SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "en".
            ?film rdfs:label ?valueLabel.
        }}
      }}
    }}
    ORDER BY ?propertyLabel ?valueLabel
    """
    return query

def format_infobox(raw_bindings, actor_name, actor_qid, actor_url):
    """
    Chuyển đổi kết quả SPARQL thô thành cấu trúc infobox sạch.
    """
    # Cấu trúc cơ sở cho mỗi diễn viên
    infobox = {
        "name": actor_name,
        "qid": actor_qid,
        "viwikiURL": actor_url,
        "gender": None,
        "infobox": defaultdict(list)
    }
    
    processed_entries = set() # Dùng để tránh trùng lặp

    for item in raw_bindings:
        # Lấy các giá trị từ kết quả query
        prop_label = item.get("propertyLabel", {}).get("value", "")
        prop_id = item.get("propertyID", {}).get("value", "")
        val_label = item.get("valueLabel", {}).get("value", "")
        val_id = item.get("valueID", {}).get("value", "")
        val_url = item.get("viwikiURL", {}).get("value", "")

        # Nếu là thuộc tính Giới tính (P21), lưu vào cấp cao nhất và bỏ qua
        if prop_id == "P21":
            if val_label:
                infobox["gender"] = val_label
            continue # Không thêm "Giới tính" vào bên trong "infobox"

        if not prop_label or not val_label:
            continue # Bỏ qua nếu thiếu thông tin cơ bản

        # Tạo key (ví dụ: "Cha (P22)")
        key = f"{prop_label} ({prop_id})"
        
        # Tạo đối tượng giá trị
        value_entry = {"name": val_label}
        if val_id:
            value_entry["qid"] = val_id # Thêm QID của giá trị (rất quan trọng)
        if val_url:
            value_entry["url"] = val_url

        # Kiểm tra trùng lặp trước khi thêm
        entry_signature = (key, val_label, val_id, val_url)
        if entry_signature not in processed_entries:
            infobox["infobox"][key].append(value_entry)
            processed_entries.add(entry_signature)
            
    # Chuyển defaultdict thành dict thường để lưu JSON
    infobox["infobox"] = dict(infobox["infobox"])
    return infobox

def main():
    """
    Chạy quy trình "Trích xuất":
    1. Đọc tất cả các file từ 'output/lists/'.
    2. Lọc trùng các diễn viên.
    3. Lặp qua từng diễn viên, chạy truy vấn chi tiết.
    4. Định dạng và lưu kết quả.
    """
    print("--- BẮT ĐẦU BƯỚC 2: TRÍCH XUẤT CHI TIẾT ---")
    setup_directories()

    # 1. Đọc tất cả các file danh sách và lọc trùng
    actor_files = glob.glob(f"{LISTS_DIR}/*.json")
    if not actor_files:
        print(f"❌ Không tìm thấy file danh sách nào trong {LISTS_DIR}.")
        print("Vui lòng chạy '1_run_discovery.py' trước.")
        return

    all_actors = {} # Dùng dict để tự động lọc trùng bằng QID
    print(f"🌍 Đang tổng hợp danh sách từ {len(actor_files)} file...")

    for f in actor_files:
        actor_list = load_json(f)
        if not actor_list:
            continue
        
        for actor in actor_list:
            try:
                person_uri = actor['person']['value']
                person_qid = person_uri.split('/')[-1]
                
                if person_qid not in all_actors:
                    all_actors[person_qid] = {
                        "name": actor['personLabel']['value'],
                        "url": actor['viwikiURL']['value']
                    }
            except KeyError:
                print(f"  ⚠️ Bỏ qua mục bị lỗi trong file {f}")

    total_actors = len(all_actors)
    print(f"✅ Đã tổng hợp. Có {total_actors} diễn viên/đạo diễn (đã lọc trùng).")

    # 2. Lặp qua danh sách đã lọc trùng và trích xuất
    print("\n--- Bắt đầu trích xuất chi tiết ---")
    
    # Nơi lưu tất cả infobox (để tạo 1 file tổng)
    final_combined_data = {} 
    
    for i, (qid, info) in enumerate(all_actors.items(), 1):
        actor_name = info['name']
        actor_url = info['url']
        print(f"\n🔄 ({i}/{total_actors}) Đang xử lý: {actor_name} ({qid})")


        combined_key = f"{actor_name}_{qid}"
        
        # Kiểm tra xem file đã tồn tại chưa để bỏ qua
        output_path = f"{INFOBOXES_DIR}/{qid}.json"
        if os.path.exists(output_path):
            print(f"  ℹ️ Đã tồn tại file. Bỏ qua.")
            # Đọc file cũ để thêm vào file tổng
            # final_combined_data[qid] = load_json(output_path)
            final_combined_data[combined_key] = load_json(output_path)
            continue

        # 1. Tạo truy vấn trích xuất
        query = build_extraction_query(qid)
        
        # 2. Chạy truy vấn
        raw_bindings = run_sparql_query(query)
        
        if raw_bindings:
            # 3. Chuyển đổi
            structured_data = format_infobox(raw_bindings, actor_name, qid, actor_url)
            print(f"  📊 Đã chuyển đổi {len(raw_bindings)} dòng thành infobox.")
            
            # 4. Lưu file cá nhân
            save_json(structured_data, output_path)
            print(f"  💾 Đã lưu file: {output_path}")
            
            # 5. Thêm vào file tổng
            # final_combined_data[qid] = structured_data
            final_combined_data[combined_key] = structured_data
        else:
            print(f"  ℹ️ Không có dữ liệu chi tiết trả về cho {actor_name}.")

        # Tạm dừng 1 giây để tuân thủ API
        time.sleep(1)

    # 3. Lưu file tổng hợp tất cả
    final_combined_file = f"{OUTPUT_DIR}/all_actors_infoboxes.json"
    print(f"\n💾 Đang lưu file tổng hợp tất cả ({total_actors} mục)...")
    save_json(final_combined_data, final_combined_file)
    print(f"\n🎉 HOÀN TẤT BƯỚC 2! Đã lưu file tổng hợp: {final_combined_file}")

if __name__ == "__main__":
    main()