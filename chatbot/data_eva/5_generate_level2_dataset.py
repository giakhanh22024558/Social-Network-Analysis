import csv
import random
from neo4j import GraphDatabase
from tqdm import tqdm

# --- CẤU HÌNH ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789" # <--- Thay mật khẩu của bạn
OUTPUT_FILE = "eval_level2_1000.csv"
TARGET_TOTAL = 1000

class Level2Generator:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        with self.driver.session() as session:
            return session.run(query, params).data()

    def create_question(self, question, answer, explanation, rel_type):
        return {
            "level": 2,
            "rel_type": rel_type,
            "question": question,
            "option_a": "Đúng",
            "option_b": "Sai",
            "answer": answer, # "A" (Đúng) hoặc "B" (Sai)
            "ground_truth": explanation
        }

    # --- 1. CO-ACTOR: X và Y có cùng tham gia phim Z không? ---
    def gen_co_actor_specific(self, count):
        print(f"Generating {count} Co-Actor Specific questions...")
        data = []
        
        # [TRUE CASE]: Lấy 3 node (A)-[:ACTED_IN]->(M)<-[:ACTED_IN]-(B)
        query_true = """
        MATCH (p1:Person)-[:ACTED_IN]->(m:Film)<-[:ACTED_IN]-(p2:Person)
        WHERE elementId(p1) < elementId(p2)
        RETURN p1.name as p1, p2.name as p2, m.name as m
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"{row['p1']} và {row['p2']} có cùng tham gia vào bộ phim '{row['m']}' không?",
                "A", # Đúng
                f"Đúng, cả hai đều đóng trong phim '{row['m']}'.",
                "CO_ACTOR"
            )
            data.append(q)

        # [FALSE CASE]: Lấy A, B đóng chung phim M1, nhưng hỏi về phim M2 (mà họ không đóng chung hoặc chỉ 1 người đóng)
        query_false = """
        MATCH (p1:Person), (m:Film)
        WHERE NOT (p1)-[:ACTED_IN]->(m) 
        WITH p1, m LIMIT $limit
        MATCH (p2:Person)-[:ACTED_IN]->(m) // P2 đóng M, nhưng P1 thì không
        RETURN p1.name as p1, p2.name as p2, m.name as m
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"{row['p1']} và {row['p2']} có cùng tham gia vào bộ phim '{row['m']}' không?",
                "B", # Sai
                f"Sai, {row['p1']} không tham gia phim '{row['m']}'.",
                "CO_ACTOR"
            )
            data.append(q)
            
        return data

    # --- 2. DIRECTOR-ACTOR: X có phải đạo diễn phim Y đóng? ---
    def gen_director_actor(self, count):
        print(f"Generating {count} Director-Actor questions...")
        data = []
        
        # [TRUE]
        query_true = """
        MATCH (d:Person)-[:DIRECTED]->(m:Film)<-[:ACTED_IN]-(a:Person)
        RETURN d.name as d, a.name as a, m.name as m
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"{row['d']} có phải là đạo diễn của bộ phim mà {row['a']} tham gia là '{row['m']}' không?",
                "A",
                f"Đúng, {row['d']} đạo diễn phim '{row['m']}' và {row['a']} diễn xuất trong đó.",
                "DIRECTOR_ACTOR"
            )
            data.append(q)
            
        # [FALSE] - Lấy ông đạo diễn khác
        query_false = """
        MATCH (d:Person)-[:DIRECTED]->(m:Film)<-[:ACTED_IN]-(a:Person)
        MATCH (d2:Person) WHERE d2 <> d AND NOT (d2)-[:DIRECTED]->(m)
        RETURN d2.name as d_fake, a.name as a, m.name as m, d.name as real_d
        LIMIT $limit
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"{row['d_fake']} có phải là đạo diễn của bộ phim '{row['m']}' mà {row['a']} tham gia không?",
                "B",
                f"Sai, đạo diễn của phim '{row['m']}' là {row['real_d']}, không phải {row['d_fake']}.",
                "DIRECTOR_ACTOR"
            )
            data.append(q)
            
        return data

    # --- 3. FAMILY VERIFICATION: X có phải [Quan hệ] của Y? ---
    def gen_family_verify(self, count):
        print(f"Generating {count} Family Verification questions...")
        data = []
        
        # List các quan hệ gia đình cần test
        rels = ["IS_CHILD_OF", "IS_SPOUSE_OF", "IS_SIBLING_OF"]
        
        for rel in rels:
            # [TRUE]
            query_true = f"""
            MATCH (a:Person)-[r:{rel}]->(b:Person)
            RETURN a.name as a, b.name as b
            LIMIT $limit
            """
            true_samples = self.run_query(query_true, params={"limit": (count // len(rels)) // 2})
            
            for row in true_samples:
                label = "con" if rel == "IS_CHILD_OF" else "vợ/chồng" if rel == "IS_SPOUSE_OF" else "anh/chị em"
                q = self.create_question(
                    f"{row['a']} có phải là {label} của {row['b']} không?",
                    "A",
                    f"Đúng, {row['a']} là {label} của {row['b']}.",
                    rel
                )
                data.append(q)
                
            # [FALSE] - Tìm người có quan hệ khác nhưng KHÔNG phải quan hệ này (gây nhiễu tốt hơn random)
            # Ví dụ: Là bạn diễn nhưng hỏi có phải vợ chồng không
            query_false = f"""
            MATCH (a:Person)-[:ACTED_IN]->(:Film)<-[:ACTED_IN]-(b:Person)
            WHERE NOT (a)-[:{rel}]-(b) AND elementId(a) < elementId(b)
            RETURN a.name as a, b.name as b
            LIMIT $limit
            """
            false_samples = self.run_query(query_false, params={"limit": (count // len(rels)) // 2})
            
            for row in false_samples:
                label = "con" if rel == "IS_CHILD_OF" else "vợ/chồng" if rel == "IS_SPOUSE_OF" else "anh/chị em"
                q = self.create_question(
                    f"{row['a']} có phải là {label} của {row['b']} không?",
                    "B",
                    f"Sai, họ không có quan hệ {label} (có thể chỉ là đồng nghiệp).",
                    rel
                )
                data.append(q)
                
        return data

    # --- 4. GENERAL CONNECTION: X và Y có quen nhau không? (ShortestPath) ---
    def gen_general_connection(self, count):
        print(f"Generating {count} General Connection questions...")
        data = []
        
        # [TRUE] - Có đường đi ngắn (<= 3 hops)
        query_true = """
        MATCH (a:Person), (b:Person)
        WHERE elementId(a) < elementId(b)
        MATCH p = shortestPath((a)-[*..3]-(b))
        WHERE length(p) > 0
        RETURN a.name as a, b.name as b, length(p) as dist
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"{row['a']} và {row['b']} có mối liên hệ nào với nhau không?",
                "A",
                f"Đúng, họ có liên kết gián tiếp hoặc trực tiếp (khoảng cách {row['dist']} bước).",
                "CONNECTION"
            )
            data.append(q)
            
        # [FALSE] - Không có đường đi hoặc đường rất xa
        # Để đơn giản và chính xác, ta lấy 2 người từ 2 cụm khác nhau hoặc random
        # Ở đây dùng random 2 người và check shortestPath is null (hoặc > 6)
        query_false = """
        MATCH (a:Person), (b:Person)
        WHERE elementId(a) < elementId(b) AND NOT (a)-[*..4]-(b)
        RETURN a.name as a, b.name as b
        LIMIT $limit
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"{row['a']} và {row['b']} có quen biết hoặc liên quan gì nhau không?",
                "B",
                "Sai (hoặc Không), không tìm thấy mối liên hệ gần gũi nào giữa họ trong dữ liệu.",
                "CONNECTION"
            )
            data.append(q)
            
        return data

    # --- 5. 3-NODE CHAIN: X, Y, Z có liên kết không? ---
    def gen_triple_connection(self, count):
        print(f"Generating {count} Triple Connection questions...")
        data = []
        
        # [TRUE] - Chuỗi A-B-C (Ví dụ: A đóng phim B, B được sx bởi C)
        # Hoặc A cha B, B đóng phim C
        query_true = """
        MATCH (a:Person)-[:IS_CHILD_OF]->(b:Person)-[:ACTED_IN]->(c:Film)
        RETURN a.name as a, b.name as b, c.name as c
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"{row['a']}, {row['b']} và bộ phim '{row['c']}' có mối liên hệ chuỗi nào không?",
                "A",
                f"Đúng, {row['a']} là con của {row['b']}, và {row['b']} đã đóng phim '{row['c']}'.",
                "TRIPLE_LINK"
            )
            data.append(q)
            
        # [FALSE] - Lấy 3 thực thể rời rạc
        query_false = """
        MATCH (a:Person), (b:Person), (c:Film)
        WHERE NOT (a)-->(b) AND NOT (b)-->(c)
        RETURN a.name as a, b.name as b, c.name as c
        LIMIT $limit
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"{row['a']}, {row['b']} và bộ phim '{row['c']}' có mối liên kết chặt chẽ với nhau không?",
                "B",
                "Sai, không tìm thấy chuỗi liên kết trực tiếp giữa 3 thực thể này.",
                "TRIPLE_LINK"
            )
            data.append(q)
            
        return data

    def save(self, data):
        random.shuffle(data)
        final_data = data[:TARGET_TOTAL]
        print(f"\n💾 Saving {len(final_data)} questions to {OUTPUT_FILE}...")
        
        fieldnames = ["level", "rel_type", "question", "option_a", "option_b", "answer", "ground_truth"]
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_data)
        print("✅ Done!")

# --- MAIN ---
if __name__ == "__main__":
    gen = Level2Generator(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    all_data = []
    
    # Phân bổ 1000 câu
    all_data.extend(gen.gen_co_actor_specific(200)) # 200 câu
    all_data.extend(gen.gen_director_actor(200))    # 200 câu
    all_data.extend(gen.gen_family_verify(200))     # 200 câu
    all_data.extend(gen.gen_general_connection(200)) # 200 câu
    all_data.extend(gen.gen_triple_connection(200))  # 200 câu
    
    gen.save(all_data)
    gen.close()