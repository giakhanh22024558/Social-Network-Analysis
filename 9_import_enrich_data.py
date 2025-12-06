import os
import json
from neo4j import GraphDatabase
from utils import load_json, OUTPUT_DIR

# --- CẤU HÌNH ---
# File chứa dữ liệu đã trích xuất từ LLM
INPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_data_filtered.json")

# Thông tin kết nối Neo4j
NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

class EnrichedDataImporter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print("✅ Kết nối Neo4j thành công!")

    def close(self):
        self.driver.close()
        print("✅ Đã đóng kết nối.")

    def import_data(self, data):
        """Import dữ liệu làm giàu vào Neo4j"""
        print(f"🚀 Bắt đầu import {len(data)} hồ sơ diễn viên...")
        
        with self.driver.session() as session:
            count = 0
            for key, actor_data in data.items():
                count += 1
                
                # Trích xuất tên diễn viên và QID từ key (ví dụ: "David Lynch_Q2071")
                try:
                    actor_name = key.split('_')[0]
                    qid = key.split('_')[-1]
                except IndexError:
                    print(f"⚠️ Key không đúng định dạng: {key}. Bỏ qua.")
                    continue
                
                summary = actor_data.get('summary', '')
                entities = actor_data.get('entities', [])
                relationships = actor_data.get('relationships', [])
                
                print(f"Importing ({count}/{len(data)}): {actor_name}...", end=" ", flush=True)

                # 1. Cập nhật Summary cho Node Person (Tìm bằng QID)
                if summary:
                    session.run(
                        """
                        MATCH (p:Person {qid: $qid})
                        SET p.summary = $summary
                        """,
                        qid=qid, summary=summary
                    )

                # 2. Tạo các Node Thực thể mới (Organization, Location, Award...)
                for ent in entities:
                    ent_name = ent.get('id') or ent.get('name') 
                    ent_label = ent.get('label') or ent.get('type')
                    
                    if not ent_name or not ent_label: continue
                    
                    # Chuẩn hóa Label
                    valid_label = ent_label.title().replace(" ", "")
                    allowed_labels = ["Organization", "University", "School", "Location", "Award", "Person"]
                    
                    if valid_label not in allowed_labels and "Person" not in valid_label:
                        continue

                    # Tạo node mới (Dùng MERGE để không tạo trùng)
                    # Lưu ý: Label động trong Cypher cần xử lý chuỗi hoặc dùng thư viện hỗ trợ (apoc), 
                    # ở đây dùng f-string đơn giản nhưng cần đảm bảo label an toàn.
                    query_create_node = f"""
                    MERGE (n:{valid_label} {{name: $name}})
                    """
                    try:
                        session.run(query_create_node, name=ent_name)
                    except Exception:
                        pass

                # 3. Tạo Mối quan hệ mới
                for rel in relationships:
                    tail_name = rel.get('tail') or rel.get('target')
                    rel_type = rel.get('type')
                    
                    if not tail_name or not rel_type: continue
                    
                    valid_rel_type = rel_type.upper().replace(" ", "_")
                    
                    # Tạo quan hệ từ Person (QID) đến Node mới (Name)
                    query_create_rel = f"""
                    MATCH (p:Person {{qid: $qid}})
                    MATCH (t {{name: $tail_name}}) 
                    WHERE NOT t:Person OR t.qid IS NOT NULL OR t.name <> p.name 
                    MERGE (p)-[r:{valid_rel_type}]->(t)
                    """
                    
                    try:
                        session.run(query_create_rel, qid=qid, tail_name=tail_name)
                    except Exception:
                        pass
                
                print("✅ Done")

def main():
    print("--- BƯỚC 7: IMPORT DỮ LIỆU LÀM GIÀU VÀO NEO4J ---")
    
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Không tìm thấy file: {INPUT_FILE}")
        return
        
    data = load_json(INPUT_FILE)
    
    importer = None
    try:
        importer = EnrichedDataImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        importer.import_data(data)
    except Exception as e:
        print(f"❌ Lỗi: {e}")
    finally:
        if importer:
            importer.close()

if __name__ == "__main__":
    main()