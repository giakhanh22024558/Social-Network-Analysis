import sys
from neo4j import GraphDatabase

# --- CẤU HÌNH KẾT NỐI ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

class GraphPathFinder:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def find_shortest_path_bfs(self, source_name, target_name):
        """
        Tìm đường đi ngắn nhất (Unweighted Shortest Path) giữa 2 người
        sử dụng thuật toán BFS tích hợp sẵn trong Cypher.
        """
        print(f"\n🔍 Đang tìm đường ngắn nhất từ '{source_name}' đến '{target_name}'...")

        query = """
        MATCH (p1:Person {name: $source_name})
        MATCH (p2:Person {name: $target_name})
        
        // shortestPath trong Neo4j sử dụng BFS cho đồ thị không trọng số
        // [*] nghĩa là tìm bất kỳ mối quan hệ nào, độ sâu không giới hạn (hoặc có thể giới hạn *..10)
        MATCH path = shortestPath((p1)-[*]-(p2))
        
        RETURN path
        """

        with self.driver.session() as session:
            result = session.run(query, source_name=source_name, target_name=target_name)
            record = result.single()

            if record:
                path = record["path"]
                self.print_path_visual(path)
            else:
                print(f"❌ Không tìm thấy đường đi nào kết nối giữa hai người này (hoặc tên bị sai).")

    def print_path_visual(self, path):
        """Hàm in đường đi ra màn hình một cách trực quan"""
        print(f"✅ Đã tìm thấy! Độ dài đường đi: {len(path)} mối quan hệ.")
        print("-" * 60)
        
        # path trong Neo4j gồm các Nodes và Relationships xen kẽ
        # StartNode -> Rel -> Node -> Rel -> EndNode
        
        nodes = path.nodes
        relationships = path.relationships
        
        # In node bắt đầu
        start_node = nodes[0]
        labels = list(start_node.labels)
        label_display = "ActorDirector" if "ActorDirector" in labels else "Person"
        print(f"🟢 [BẮT ĐẦU]: {start_node.get('name')} ({label_display})")

        # Lặp qua các bước
        for i, rel in enumerate(relationships):
            next_node = nodes[i + 1]
            rel_type = rel.type
            
            # Xác định hướng mũi tên (để hiển thị cho đẹp)
            # Neo4j path luôn có hướng thực tế, nhưng ta vẽ tượng trưng
            arrow = f"--[{rel_type}]-->"
            
            node_labels = list(next_node.labels)
            if "Film" in node_labels:
                node_type = "🎬 PHIM"
                color_code = "" 
            elif "ActorDirector" in node_labels:
                node_type = "⭐ DIỄN VIÊN"
            else:
                node_type = "👤 NGƯỜI"

            print(f"     |\n     | {arrow}\n     v")
            print(f"   {node_type}: {next_node.get('name')}")

        print("-" * 60)

# --- HÀM MAIN ĐỂ CHẠY ---
def main():
    finder = GraphPathFinder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    # Sửa tên trực tiếp ở đây để test
    source = "Leonardo DiCaprio"
    target = "Tom Hanks" 
    
    # Hoặc nhập từ bàn phím nếu chạy terminal
    if len(sys.argv) >= 3:
        source = sys.argv[1]
        target = sys.argv[2]

    try:
        finder.find_shortest_path_bfs(source, target)
    except Exception as e:
        print(f"Lỗi: {e}")
    finally:
        finder.close()

if __name__ == "__main__":
    main()