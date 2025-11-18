import os
from neo4j import GraphDatabase
from utils import load_json, OUTPUT_DIR # Tái sử dụng hàm từ utils.py

# --- CẤU HÌNH NEO4J ---
# Sử dụng lại cấu hình từ file 4_import_to_neo4j.py
NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789" # Mật khẩu bạn đặt ở Bước 1

class Neo4jGraphAnalysis:
    def __init__(self, uri, user, password):
        # Kết nối tới cơ sở dữ liệu Neo4j
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print("✅ Kết nối tới Neo4j thành công!")

    def close(self):
        self.driver.close()

    def find_shortest_path(self, name1, name2):
        """
        Tìm đường đi ngắn nhất (shortest path) giữa 2 nút Person
        sử dụng hàm shortestPath() sẵn có của Cypher.
        
        Hàm này không yêu cầu cài đặt thư viện GDS mà chạy trực tiếp,
        rất phù hợp cho bài toán tìm đường đi đơn giản.
        """
        print(f"\n🔄 Đang tìm đường đi ngắn nhất giữa '{name1}' và '{name2}'...")
        
        # Câu truy vấn Cypher sử dụng shortestPath()
        # MATCH p = shortestPath(...) tìm một đường đi ngắn nhất
        # (a:Person {name: $name1}) - [*] - (b:Person {name: $name2})
        #   - (a:Person {name: $name1}): Tìm nút Person 1 có tên khớp
        #   - (b:Person {name: $name2}): Tìm nút Person 2 có tên khớp
        #   - [*]: Dấu sao [*] nghĩa là đi theo BẤT KỲ mối quan hệ nào, 
        #          BẤT KỲ hướng nào (không quan tâm là ACTED_IN, IS_CHILD_OF,...)
        # RETURN p: Trả về đường đi đó
        
        query = """
        MATCH p = shortestPath((a:Person {name: $name1})-[*]-(b:Person {name: $name2}))
        RETURN p
        """
        
        with self.driver.session() as session:
            result = session.run(query, name1=name1, name2=name2)
            path_record = result.single() # Lấy một kết quả (nếu có)
            
            if not path_record:
                print(f"❌ Không tìm thấy đường đi nào giữa '{name1}' và '{name2}'.")
                return

            # Xử lý và in kết quả
            path = path_record['p']
            print(f"✅ Đã tìm thấy đường đi! (Độ dài: {len(path)})")
            
            nodes = path.nodes
            relationships = path.relationships

            output = []
            for i, node in enumerate(nodes):
                # In tên nút
                # Cố gắng lấy nhãn :ActorDirector trước, nếu không có thì lấy :Person, ...
                labels = list(node.labels)
                node_label = "ActorDirector" if "ActorDirector" in labels else labels[0]
                node_name = node['name']
                output.append(f"({node_name}: {node_label})")
                
                # In mối quan hệ (nếu chưa phải nút cuối)
                if i < len(relationships):
                    rel_type = relationships[i].type
                    
                    # --- SỬA LỖI ---
                    # Lỗi: 'relationship' object không có 'start_node_id'
                    # Sửa: Dùng 'relationship.start_node.id'
                    if relationships[i].start_node.id == node.id:
                        output.append(f"-[{rel_type}]->")
                    else:
                        output.append(f"<-[{rel_type}]-")

            print("\n--- CHI TIẾT ĐƯỜNG ĐI ---")
            print(" ".join(output))
            print("--------------------------\n")

def main():
    print("--- BẮT ĐẦU BÀI TẬP PHÂN TÍCH ĐỒ THỊ ---")
    
    # Khởi tạo lớp phân tích
    analysis = Neo4jGraphAnalysis(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    # --- CHẠY THỬ THUẬT TOÁN TÌM ĐƯỜNG ĐI NGẮN NHẤT ---
    
    # Sử dụng tên bạn đã thử nghiệm
    actor1 = "David Lynch"
    actor2 = "Frances Conroy"
    
    # Chạy thuật toán
    analysis.find_shortest_path(actor1, actor2)
    
    # Thử một cặp khác (ví dụ 2 diễn viên có thể cùng đóng 1 phim)
    actor3 = "Angelina Jolie" 
    actor4 = "Brad Pitt" 
    if actor3 != actor4:
        analysis.find_shortest_path(actor3, actor4)

    # Đóng kết nối
    analysis.close()
    print("✅ Phân tích hoàn tất.")

if __name__ == "__main__":
    main()