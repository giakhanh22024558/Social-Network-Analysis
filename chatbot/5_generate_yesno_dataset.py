import csv
import random
from neo4j import GraphDatabase
from tqdm import tqdm

# --- CẤU HÌNH ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"  # <--- Thay mật khẩu của bạn
OUTPUT_FILE = "yesno_evaluation_dataset.csv"

# Tỷ lệ và Số lượng
TOTAL_QUESTIONS = 2500
COUNT_L1 = int(TOTAL_QUESTIONS * 0.35)  # 875 câu
COUNT_L2 = int(TOTAL_QUESTIONS * 0.40)  # 1000 câu
COUNT_L3 = int(TOTAL_QUESTIONS * 0.25)  # 625 câu

class YesNoDataGenerator:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        with self.driver.session() as session:
            return session.run(query, params).data()

    # =========================================================================
    # MỨC 1: TRUY XUẤT CƠ BẢN (1-HOP) - 35%
    # Logic: Kiểm tra quan hệ trực tiếp (A có quan hệ r với B không?)
    # =========================================================================
    def generate_level_1(self, count):
        print(f"Generating {count} Level 1 questions...")
        dataset = []
        half = count // 2

        # --- 1. POSITIVE (ĐÚNG) ---
        query_pos = """
        MATCH (n)-[r]->(m)
        WHERE type(r) IN ['ACTED_IN', 'DIRECTED', 'PRODUCED', 'IS_CHILD_OF', 'IS_SPOUSE_OF']
        RETURN n.name as sub, type(r) as rel, m.name as obj, labels(n) as n_labels
        ORDER BY rand() LIMIT $limit
        """
        pos_results = self.run_query(query_pos, params={"limit": half})
        
        for row in pos_results:
            q = self.create_question_text(row['sub'], row['rel'], row['obj'], True)
            dataset.append({"level": 1, "type": "1-Hop", "question": q, "answer": "Yes", "ground_truth": f"{row['sub']} --[{row['rel']}]--> {row['obj']}"})

        # --- 2. NEGATIVE (SAI) ---
        # Lấy cặp node ngẫu nhiên KHÔNG có quan hệ
        query_neg = """
        MATCH (n:Person), (m)
        WHERE (m:Film OR m:Person) AND n <> m AND NOT (n)-->(m)
        WITH n, m ORDER BY rand() LIMIT $limit
        RETURN n.name as sub, m.name as obj, labels(m) as m_labels
        """
        neg_results = self.run_query(query_neg, params={"limit": count - len(dataset)})
        
        for row in neg_results:
            # Random một loại quan hệ để hỏi (nhưng thực tế là sai)
            fake_rel = "ACTED_IN" if "Film" in row['m_labels'] else "IS_SPOUSE_OF"
            q = self.create_question_text(row['sub'], fake_rel, row['obj'], True) # True here just formats the text
            dataset.append({"level": 1, "type": "1-Hop", "question": q, "answer": "No", "ground_truth": "Không có mối quan hệ này."})

        return dataset

    # =========================================================================
    # MỨC 2: TÌM ĐƯỜNG TƯỜNG MINH (EXPLICIT MULTI-HOP) - 40%
    # Logic: A và B có quan hệ chung (qua trung gian) không?
    # =========================================================================
    def generate_level_2(self, count):
        print(f"Generating {count} Level 2 questions...")
        dataset = []
        half = count // 2

        # --- 1. POSITIVE (Có đóng chung phim / Có quan hệ gia đình bắc cầu) ---
        query_pos = """
        MATCH (p1:Person)-[:ACTED_IN]->(m:Film)<-[:ACTED_IN]-(p2:Person)
        WHERE elementId(p1) < elementId(p2)
        RETURN p1.name as a, p2.name as b, m.name as via
        ORDER BY rand() LIMIT $limit
        """
        pos_results = self.run_query(query_pos, params={"limit": half})
        
        for row in pos_results:
            dataset.append({
                "level": 2, 
                "type": "Explicit_Path", 
                "question": f"{row['a']} và {row['b']} có từng đóng chung bộ phim nào không?", 
                "answer": "Yes", 
                "ground_truth": f"Có, họ đóng chung phim {row['via']}."
            })

        # --- 2. NEGATIVE (Không liên quan) ---
        query_neg = """
        MATCH (p1:Person), (p2:Person)
        WHERE elementId(p1) < elementId(p2) 
        AND NOT (p1)-[:ACTED_IN]->()<-[:ACTED_IN]-(p2) 
        AND NOT (p1)-[:IS_CHILD_OF|IS_SPOUSE_OF*1..2]-(p2)
        WITH p1, p2 ORDER BY rand() LIMIT $limit
        RETURN p1.name as a, p2.name as b
        """
        neg_results = self.run_query(query_neg, params={"limit": count - len(dataset)})
        
        for row in neg_results:
            dataset.append({
                "level": 2, 
                "type": "Explicit_Path", 
                "question": f"{row['a']} và {row['b']} có từng đóng chung bộ phim nào không?", 
                "answer": "No", 
                "ground_truth": "Không tìm thấy phim chung."
            })

        return dataset

    # =========================================================================
    # MỨC 3: SUY LUẬN ẨN (IMPLICIT MULTI-HOP) - 25%
    # Logic: Hỏi về thuộc tính/quan hệ của một người KHÔNG được nhắc tên (Node ẩn)
    # =========================================================================
    def generate_level_3(self, count):
        print(f"Generating {count} Level 3 questions...")
        dataset = []
        half = count // 2

        # --- 1. POSITIVE (ĐÚNG) ---
        # VD: Bố của A có phải là diễn viên không? (Tìm Bố -> Check nghề nghiệp/đóng phim)
        query_pos = """
        MATCH (start:Person)-[:IS_CHILD_OF]->(hidden:Person)
        WHERE (hidden:ActorDirector OR (hidden)-[:ACTED_IN]->(:Film))
        RETURN start.name as s_name, hidden.name as h_name
        ORDER BY rand() LIMIT $limit
        """
        pos_results = self.run_query(query_pos, params={"limit": half})
        
        for row in pos_results:
            dataset.append({
                "level": 3,
                "type": "Implicit_Entity",
                "question": f"Cha/Mẹ của {row['s_name']} có phải là một diễn viên không?",
                "answer": "Yes",
                "ground_truth": f"Đúng, Cha/Mẹ của {row['s_name']} là {row['h_name']}, và người này là diễn viên."
            })

        # --- 2. NEGATIVE (SAI) ---
        # VD: Đạo diễn của phim X có đóng phim Y không? (Mà thực tế là không)
        # Tìm Đạo diễn (Hidden) -> Lấy một phim ngẫu nhiên mà Hidden KHÔNG đóng
        query_neg = """
        MATCH (p:Person)-[:DIRECTED]->(f_start:Film)
        MATCH (f_random:Film)
        WHERE NOT (p)-[:ACTED_IN]->(f_random) AND f_start <> f_random
        WITH p, f_start, f_random ORDER BY rand() LIMIT $limit
        RETURN f_start.name as start_film, p.name as hidden_person, f_random.name as random_film
        """
        neg_results = self.run_query(query_neg, params={"limit": count - len(dataset)})
        
        for row in neg_results:
            dataset.append({
                "level": 3,
                "type": "Implicit_Entity",
                "question": f"Đạo diễn của phim '{row['start_film']}' có tham gia diễn xuất trong phim '{row['random_film']}' không?",
                "answer": "No",
                "ground_truth": f"Sai. Đạo diễn là {row['hidden_person']}, ông ấy không đóng phim {row['random_film']}."
            })

        return dataset

    # --- HÀM PHỤ TRỢ: TẠO CÂU HỎI TỰ NHIÊN DỰA TRÊN QUAN HỆ ---
    def create_question_text(self, sub, rel, obj, is_forward):
        # Dựa trên logic get_relationship_action của bạn
        if rel == "ACTED_IN":
            return f"{sub} có đóng trong phim '{obj}' không?"
        elif rel == "DIRECTED":
            return f"{sub} có phải là đạo diễn của phim '{obj}' không?"
        elif rel == "PRODUCED":
            return f"{sub} có sản xuất phim '{obj}' không?"
        elif rel == "IS_CHILD_OF":
            return f"{sub} có phải là con của {obj} không?"
        elif rel == "IS_SPOUSE_OF":
            return f"{sub} có phải là vợ/chồng của {obj} không?"
        elif rel == "IS_PARTNER_OF":
            return f"{sub} có phải là bạn đời của {obj} không?"
        elif rel == "IS_SIBLING_OF":
            return f"{sub} có phải là anh/chị em với {obj} không?"
        elif rel == "HAS_GRANDPARENT_OF":
            return f"{obj} có phải là ông/bà của {sub} không?" # Lưu ý đảo ngữ pháp cho tự nhiên
        else:
            return f"{sub} có quan hệ {rel} với {obj} không?"

    def save_to_csv(self, data):
        random.shuffle(data) # Xáo trộn toàn bộ
        print(f"💾 Saving {len(data)} questions to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=["level", "type", "question", "answer", "ground_truth"])
            writer.writeheader()
            writer.writerows(data)
        print("✅ Hoàn tất!")

# --- MAIN ---
if __name__ == "__main__":
    gen = YesNoDataGenerator(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    all_data = []
    
    # Sinh dữ liệu theo từng mức độ
    all_data.extend(gen.generate_level_1(COUNT_L1))
    all_data.extend(gen.generate_level_2(COUNT_L2))
    all_data.extend(gen.generate_level_3(COUNT_L3))
    
    # Kiểm tra số lượng
    print(f"\nTổng số câu hỏi: {len(all_data)}")
    print(f"- Mức 1: {len([x for x in all_data if x['level']==1])}")
    print(f"- Mức 2: {len([x for x in all_data if x['level']==2])}")
    print(f"- Mức 3: {len([x for x in all_data if x['level']==3])}")
    
    gen.save_to_csv(all_data)
    gen.close()