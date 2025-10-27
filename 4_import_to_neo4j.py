import os
from neo4j import GraphDatabase
from utils import load_json, OUTPUT_DIR # Tái sử dụng hàm

# --- CẤU HÌNH NEO4J ---
# (Thay đổi nếu bạn cấu hình khác)
NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789" # Mật khẩu bạn đặt ở Bước 1

# --- CẤU HÌNH FILE ---
INPUT_FILE = os.path.join(OUTPUT_DIR, "all_actors_infoboxes_FILTERED.json")

# Định nghĩa các khóa liên kết trong JSON
KEY_MAP = {
    "P161": "ACTED_IN",
    "P57": "DIRECTED",
    "P162": "PRODUCED",
    "P22": "IS_CHILD_OF", # Cha
    "P25": "IS_CHILD_OF", # Mẹ
    "P26": "IS_SPOUSE_OF",
    "P451": "IS_PARTNER_OF",
    "P3373": "IS_SIBLING_OF",
    "P40": "IS_PARENT_OF", # Con cái
    # Thêm các P-ID khác nếu cần
    "P1038": "HAS_GRANDPARENT_OF"  # Ông/bà
}
# Các khóa liên quan đến Phim (để tạo Nút :Film)
FILM_KEYS = {"P161", "P57", "P162"}

class Neo4jImporter:
    def __init__(self, uri, user, password):
        # Kết nối tới cơ sở dữ liệu Neo4j
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print("✅ Kết nối tới Neo4j thành công!")

    def close(self):
        self.driver.close()

    def run_cypher(self, session, query, params=None):
        """Hàm trợ giúp để chạy một truy vấn Cypher"""
        try:
            session.run(query, params)
        except Exception as e:
            print(f"  ❌ Lỗi Cypher: {e}")

    def create_constraints(self):
        """
        Tạo các ràng buộc UNIQUE. Đây là điều CỰC KỲ QUAN TRỌNG.
        Nó giúp Neo4j tra cứu 'qid' siêu nhanh và đảm bảo không trùng.
        Chỉ cần chạy 1 lần duy nhất.
        """
        print("🔄 Đang tạo các ràng buộc (constraints)...")
        with self.driver.session() as session:
            # Tạo ràng buộc cho :Person
            query_person = "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.qid IS UNIQUE"
            self.run_cypher(session, query_person)
            
            # Tạo ràng buộc cho :Film
            query_film = "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Film) REQUIRE f.qid IS UNIQUE"
            self.run_cypher(session, query_film)
        print("✅ Các ràng buộc đã được đảm bảo.")

    def import_data(self, data):
        """
        Đọc dữ liệu JSON và nhập vào Neo4j
        """
        print(f"🔄 Bắt đầu nhập {len(data)} mục...")
        
        with self.driver.session() as session:
            count = 0
            for key, actor_data in data.items():
                count += 1
                actor_qid = actor_data.get("qid")
                actor_name = actor_data.get("name")
                
                if not actor_qid:
                    continue
                
                print(f"  ({count}/{len(data)}) Đang nhập: {actor_name} ({actor_qid})")

                # --- 1. Tạo hoặc cập nhật Nút :Person chính ---
                # MERGE tìm Nút (:Person {qid: $qid})
                # ON CREATE SET ... (chỉ chạy khi Nút được tạo MỚI)
                # ON MATCH SET ... (chạy khi Nút đã TỒN TẠI)
                query_person = """
                MERGE (p:Person {qid: $qid})
                ON CREATE SET
                    p.name = $name,
                    p.gender = $gender,
                    p.viwikiURL = $url
                ON MATCH SET
                    p.name = $name,
                    p.gender = $gender,
                    p.viwikiURL = $url
                """
                session.run(query_person, 
                            qid=actor_qid, 
                            name=actor_name, 
                            gender=actor_data.get("gender"), 
                            url=actor_data.get("viwikiURL")
                )

                # --- 2. Xử lý các quan hệ trong infobox ---
                infobox = actor_data.get("infobox", {})
                
                for key_label, entries in infobox.items():
                    # Lấy P-ID từ key (ví dụ: "Cha (P22)" -> "P22")
                    pid = key_label.split('(')[-1].replace(')', '')
                    
                    if pid not in KEY_MAP:
                        continue # Bỏ qua nếu không định nghĩa (vd: Ngày sinh)

                    rel_type = KEY_MAP[pid] # Lấy tên quan hệ (vd: "IS_CHILD_OF")

                    for entry in entries:
                        entry_qid = entry.get("qid")
                        entry_name = entry.get("name")
                        
                        if not entry_qid:
                            continue # Bỏ qua nếu giá trị không có QID (vd: ngày sinh)
                        
                        # Xác định xem Nút đích là :Person hay :Film
                        target_label = ":Film" if pid in FILM_KEYS else ":Person"
                        
                        # Tạo Nút đích và Mối quan hệ
                        query_rel = f"""
                        // Bước 1: Tìm Nút :Person gốc (diễn viên chính)
                        MATCH (p1:Person {{qid: $actor_qid}})
                        
                        // Bước 2: MERGE Nút đích (phim hoặc người)
                        MERGE (p2{target_label} {{qid: $entry_qid}})
                        ON CREATE SET p2.name = $entry_name
                        
                        // Bước 3: MERGE Mối quan hệ
                        // Dùng [r:{rel_type}] để tránh tạo trùng lặp quan hệ
                        MERGE (p1)-[r:{rel_type}]->(p2)
                        """
                        
                        # Chạy truy vấn với tham số
                        session.run(query_rel, 
                                    actor_qid=actor_qid, 
                                    entry_qid=entry_qid, 
                                    entry_name=entry_name
                        )
            
            print(f"🎉 Hoàn tất nhập {count} mục!")


def main():
    print("--- BẮT ĐẦU BƯỚC 4: NHẬP VÀO NEO4J ---")
    
    # Đọc file đã lọc
    data = load_json(INPUT_FILE)
    if not data:
        print(f"❌ Không tìm thấy file {INPUT_FILE} hoặc file rỗng.")
        return

    # Khởi tạo Importer
    importer = Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    # 1. Tạo constraints (Rất quan trọng, chỉ chạy 1 lần)
    importer.create_constraints()
    
    # 2. Nhập dữ liệu
    importer.import_data(data)
    
    # 3. Đóng kết nối
    importer.close()
    print("✅ Quy trình nhập đã hoàn tất.")

if __name__ == "__main__":
    main()