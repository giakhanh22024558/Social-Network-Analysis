import csv
import random
from neo4j import GraphDatabase
from tqdm import tqdm

# --- CẤU HÌNH ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789" # <--- Thay mật khẩu của bạn
OUTPUT_FILE = "eval_level3_625.csv"
TARGET_TOTAL = 625

class Level3Generator:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        with self.driver.session() as session:
            return session.run(query, params).data()

    def create_question(self, question, answer, explanation, rel_type):
        return {
            "level": 3,
            "rel_type": rel_type,
            "question": question,
            "option_a": "Đúng",
            "option_b": "Sai",
            "answer": answer, # "A" (Đúng) hoặc "B" (Sai)
            "ground_truth": explanation
        }

    # --- 1. FAMILY IN MOVIE: Người thân của X có đóng phim Y không? ---
    # Logic: (Person A) -[Gia đình]-> (Person B [ẨN]) -[ACTED_IN]-> (Phim M)
    def gen_family_in_movie(self, count):
        print(f"Generating {count} Family-in-Movie questions...")
        data = []
        
        # [TRUE CASE]
        query_true = """
        MATCH (a:Person)-[r:IS_CHILD_OF|IS_SPOUSE_OF]-(b:Person)-[:ACTED_IN]->(m:Film)
        RETURN a.name as a, type(r) as rel, startNode(r) = a as is_child, b.name as hidden_b, m.name as m
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            # Xác định danh xưng người ẩn
            if row['rel'] == 'IS_SPOUSE_OF': relation = "Vợ/Chồng"
            elif row['rel'] == 'IS_CHILD_OF':
                # Nếu a là con (a -> b) thì b là cha/mẹ
                relation = "Cha/Mẹ" if row['is_child'] else "Con"
            
            q = self.create_question(
                f"{relation} của {row['a']} có tham gia vào bộ phim '{row['m']}' không?",
                "A",
                f"Đúng, {relation} của {row['a']} là {row['hidden_b']}, và người này có đóng trong phim '{row['m']}'.",
                "IMPLICIT_FAMILY_MOVIE"
            )
            data.append(q)

        # [FALSE CASE] - Người thân B KHÔNG đóng phim M
        query_false = """
        MATCH (a:Person)-[r:IS_CHILD_OF|IS_SPOUSE_OF]-(b:Person)
        MATCH (m:Film) 
        WHERE NOT (b)-[:ACTED_IN]->(m)
        WITH a, r, b, m, (startNode(r) = a) as is_child LIMIT $limit
        RETURN a.name as a, type(r) as rel, is_child, b.name as hidden_b, m.name as m
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            if row['rel'] == 'IS_SPOUSE_OF': relation = "Vợ/Chồng"
            elif row['rel'] == 'IS_CHILD_OF':
                relation = "Cha/Mẹ" if row['is_child'] else "Con"
                
            q = self.create_question(
                f"{relation} của {row['a']} có tham gia vào bộ phim '{row['m']}' không?",
                "B",
                f"Sai, {relation} của {row['a']} là {row['hidden_b']}, và người này KHÔNG tham gia phim '{row['m']}'.",
                "IMPLICIT_FAMILY_MOVIE"
            )
            data.append(q)
        return data

    # --- 2. DIRECTOR CONNECTION: Đạo diễn phim X có quen Y không? ---
    # Logic: (Phim M) <-[DIRECTED]- (Director D [ẨN]) -[liên_kết]- (Person Y)
    def gen_director_connection(self, count):
        print(f"Generating {count} Director-Connection questions...")
        data = []
        
        # [TRUE CASE] - Có liên kết ngắn
        query_true = """
        MATCH (m:Film)<-[:DIRECTED]-(d:Person)-[*1..2]-(y:Person)
        WHERE m <> y AND d <> y
        RETURN m.name as m, d.name as hidden_d, y.name as y
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"Đạo diễn của bộ phim '{row['m']}' có mối liên hệ nào với {row['y']} không?",
                "A",
                f"Đúng, đạo diễn của phim '{row['m']}' là {row['hidden_d']}, và họ có mối liên hệ với {row['y']}.",
                "IMPLICIT_DIRECTOR_CONN"
            )
            data.append(q)

        # [FALSE CASE] - Không có liên kết (hoặc xa)
        query_false = """
        MATCH (m:Film)<-[:DIRECTED]-(d:Person), (y:Person)
        WHERE NOT (d)-[*1..3]-(y) AND d <> y
        RETURN m.name as m, d.name as hidden_d, y.name as y
        LIMIT $limit
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"Đạo diễn của bộ phim '{row['m']}' có mối liên hệ nào với {row['y']} không?",
                "B",
                f"Sai (hoặc Không), đạo diễn là {row['hidden_d']} và không tìm thấy liên hệ trực tiếp nào với {row['y']}.",
                "IMPLICIT_DIRECTOR_CONN"
            )
            data.append(q)
        return data

    # --- 3. SPOUSE JOB: Vợ/Chồng của X có phải là Đạo diễn/Diễn viên không? ---
    # Logic: (Person A) -[IS_SPOUSE_OF]-> (Person B [ẨN]) -[HAS_OCCUPATION/Role]-> ...
    def gen_spouse_job(self, count):
        print(f"Generating {count} Spouse-Job questions...")
        data = []
        
        # [TRUE CASE] - Vợ/Chồng là Đạo diễn (Có quan hệ DIRECTED với bất kỳ phim nào)
        query_true = """
        MATCH (a:Person)-[:IS_SPOUSE_OF]-(b:Person)-[:DIRECTED]->(:Film)
        RETURN DISTINCT a.name as a, b.name as hidden_b
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"Vợ/Chồng của {row['a']} có phải là một đạo diễn không?",
                "A",
                f"Đúng, vợ/chồng của {row['a']} là {row['hidden_b']}, và người này là một đạo diễn.",
                "IMPLICIT_JOB"
            )
            data.append(q)

        # [FALSE CASE] - Vợ/Chồng KHÔNG phải đạo diễn (Chỉ đóng phim, không đạo diễn)
        query_false = """
        MATCH (a:Person)-[:IS_SPOUSE_OF]-(b:Person)
        WHERE NOT (b)-[:DIRECTED]->(:Film) AND (b)-[:ACTED_IN]->(:Film)
        RETURN DISTINCT a.name as a, b.name as hidden_b
        LIMIT $limit
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"Vợ/Chồng của {row['a']} có phải là một đạo diễn không?",
                "B",
                f"Sai, vợ/chồng của {row['a']} là {row['hidden_b']}, người này là diễn viên nhưng không có thông tin là đạo diễn.",
                "IMPLICIT_JOB"
            )
            data.append(q)
        return data

    # --- 4. CO-ACTOR OF PARENT: Cha/Mẹ của X có từng đóng chung với Y không? ---
    # Logic: (X) -> (Cha/Mẹ [ẨN]) -> (Y)
    def gen_parent_coactor(self, count):
        print(f"Generating {count} Parent-CoActor questions...")
        data = []
        
        # [TRUE CASE]
        query_true = """
        MATCH (child:Person)-[:IS_CHILD_OF]->(parent:Person)-[:ACTED_IN]->(:Film)<-[:ACTED_IN]-(y:Person)
        WHERE elementId(parent) <> elementId(y)
        RETURN DISTINCT child.name as child, parent.name as hidden_p, y.name as y
        LIMIT $limit
        """
        true_samples = self.run_query(query_true, params={"limit": count // 2})
        
        for row in true_samples:
            q = self.create_question(
                f"Cha/Mẹ của {row['child']} có từng đóng phim chung với {row['y']} không?",
                "A",
                f"Đúng, Cha/Mẹ của {row['child']} là {row['hidden_p']}, họ đã đóng chung với {row['y']}.",
                "IMPLICIT_COACTOR"
            )
            data.append(q)
            
        # [FALSE CASE] - Có cha mẹ, có Y, nhưng cha mẹ KHÔNG đóng chung Y
        query_false = """
        MATCH (child:Person)-[:IS_CHILD_OF]->(parent:Person), (y:Person)
        WHERE NOT (parent)-[:ACTED_IN]->(:Film)<-[:ACTED_IN]-(y) AND parent <> y
        RETURN DISTINCT child.name as child, parent.name as hidden_p, y.name as y
        LIMIT $limit
        """
        false_samples = self.run_query(query_false, params={"limit": count // 2})
        
        for row in false_samples:
            q = self.create_question(
                f"Cha/Mẹ của {row['child']} có từng đóng phim chung với {row['y']} không?",
                "B",
                f"Sai, Cha/Mẹ của {row['child']} là {row['hidden_p']}, và không tìm thấy phim chung nào với {row['y']}.",
                "IMPLICIT_COACTOR"
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
    gen = Level3Generator(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    all_data = []
    
    # Chia đều 625 câu (khoảng 156 câu/loại)
    all_data.extend(gen.gen_family_in_movie(160))
    all_data.extend(gen.gen_director_connection(160))
    all_data.extend(gen.gen_spouse_job(150))
    all_data.extend(gen.gen_parent_coactor(160))
    
    gen.save(all_data)
    gen.close()