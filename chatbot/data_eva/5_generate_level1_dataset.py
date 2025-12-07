import csv
import random
from neo4j import GraphDatabase
from tqdm import tqdm

# --- CẤU HÌNH ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789" # <--- Thay mật khẩu của bạn
OUTPUT_FILE = "eval_level1_875.csv"
TARGET_TOTAL = 875
TARGET_PER_TYPE = 0 # Sinh dư một chút để lọc

class Level1Generator:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        with self.driver.session() as session:
            return session.run(query, params).data()

    def create_mcq(self, question, correct_ans, wrong_ans, rel_type):
        """Tạo câu hỏi trắc nghiệm 2 đáp án ngẫu nhiên"""
        is_a_correct = random.choice([True, False])
        
        if is_a_correct:
            option_a = correct_ans
            option_b = wrong_ans
            answer = "A"
        else:
            option_a = wrong_ans
            option_b = correct_ans
            answer = "B"
            
        return {
            "level": 1,
            "rel_type": rel_type,
            "question": question,
            "option_a": option_a,
            "option_b": option_b,
            "answer": answer,
            "ground_truth": correct_ans
        }

    # --- 1. ACTED_IN: Ai đóng phim X? ---
    def gen_acted_in(self, count):
        print(f"Generating {count} ACTED_IN questions...")
        data = []
        # Lấy cặp Actor-Film đúng
        query = "MATCH (p:Person)-[:ACTED_IN]->(f:Film) RETURN p.name as p, f.name as f LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        
        # Lấy danh sách actor để làm nhiễu
        actors = [r['p'] for r in pos]
        if not actors: return []

        for row in pos[:count]:
            wrong = random.choice(actors)
            while wrong == row['p']: wrong = random.choice(actors)
            
            q = self.create_mcq(
                f"Ai đã tham gia vào bộ phim '{row['f']}'?",
                row['p'], wrong, "ACTED_IN"
            )
            data.append(q)
        return data

    # --- 2. DIRECTED: Ai đạo diễn phim X? ---
    def gen_directed(self, count):
        print(f"Generating {count} DIRECTED questions...")
        data = []
        query = "MATCH (p:Person)-[:DIRECTED]->(f:Film) RETURN p.name as p, f.name as f LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        directors = [r['p'] for r in pos]
        if not directors: return []

        for row in pos[:count]:
            wrong = random.choice(directors)
            while wrong == row['p']: wrong = random.choice(directors)
            
            q = self.create_mcq(
                f"Ai là đạo diễn của bộ phim '{row['f']}'?",
                row['p'], wrong, "DIRECTED"
            )
            data.append(q)
        return data

    # --- 3. PRODUCED: Ai sản xuất phim X? ---
    def gen_produced(self, count):
        print(f"Generating {count} PRODUCED questions...")
        data = []
        query = "MATCH (p:Person)-[:PRODUCED]->(f:Film) RETURN p.name as p, f.name as f LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        producers = [r['p'] for r in pos]
        if not producers: return []

        for row in pos[:count]:
            wrong = random.choice(producers)
            while wrong == row['p']: wrong = random.choice(producers)
            
            q = self.create_mcq(
                f"Bộ phim '{row['f']}' được sản xuất bởi ai?",
                row['p'], wrong, "PRODUCED"
            )
            data.append(q)
        return data

    # --- 4 & 5. IS_CHILD_OF (Cha/Mẹ) ---
    def gen_parents(self, count):
        print(f"Generating {count} PARENT questions (Father/Mother)...")
        data = []
        # Lấy quan hệ con -> cha/mẹ, kèm giới tính cha/mẹ để phân biệt
        query = """
        MATCH (child:Person)-[:IS_CHILD_OF]->(parent:Person) 
        RETURN child.name as c, parent.name as p, parent.gender as g 
        LIMIT $limit
        """
        pos = self.run_query(query, params={"limit": count * 3})
        parents = [r['p'] for r in pos]
        if not parents: return []

        for row in pos:
            if len(data) >= count: break
            
            gender = row['g']
            if gender == 'male':
                q_text = f"Cha của {row['c']} là ai?"
                rel_tag = "IS_CHILD_OF_DAD"
            elif gender == 'female':
                q_text = f"Mẹ của {row['c']} là ai?"
                rel_tag = "IS_CHILD_OF_MOM"
            else:
                continue # Bỏ qua nếu không rõ giới tính

            wrong = random.choice(parents)
            while wrong == row['p']: wrong = random.choice(parents)
            
            q = self.create_mcq(q_text, row['p'], wrong, rel_tag)
            data.append(q)
        return data

    # --- 6. IS_PARENT_OF (Con cái) ---
    def gen_children(self, count):
        print(f"Generating {count} CHILDREN questions...")
        data = []
        query = "MATCH (parent:Person)-[:IS_PARENT_OF]->(child:Person) RETURN parent.name as p, child.name as c LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        children = [r['c'] for r in pos]
        if not children: return []

        for row in pos[:count]:
            wrong = random.choice(children)
            while wrong == row['c']: wrong = random.choice(children)
            
            q = self.create_mcq(
                f"Ai là con của {row['p']}?",
                row['c'], wrong, "IS_PARENT_OF"
            )
            data.append(q)
        return data

    # --- 7. IS_SPOUSE_OF (Vợ/Chồng) ---
    def gen_spouse(self, count):
        print(f"Generating {count} SPOUSE questions...")
        data = []
        query = "MATCH (p1:Person)-[:IS_SPOUSE_OF]->(p2:Person) RETURN p1.name as p1, p2.name as p2 LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        people = [r['p2'] for r in pos]
        if not people: return []

        for row in pos[:count]:
            wrong = random.choice(people)
            while wrong == row['p2']: wrong = random.choice(people)
            
            q = self.create_mcq(
                f"Vợ/Chồng của {row['p1']} là ai?",
                row['p2'], wrong, "IS_SPOUSE_OF"
            )
            data.append(q)
        return data

    # --- 8. IS_PARTNER_OF (Bạn đời) ---
    def gen_partner(self, count):
        print(f"Generating {count} PARTNER questions...")
        data = []
        query = "MATCH (p1:Person)-[:IS_PARTNER_OF]->(p2:Person) RETURN p1.name as p1, p2.name as p2 LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        if not pos: return []
        people = [r['p2'] for r in pos]

        for row in pos[:count]:
            wrong = random.choice(people)
            while wrong == row['p2']: wrong = random.choice(people)
            
            q = self.create_mcq(
                f"Bạn đời của {row['p1']} là ai?",
                row['p2'], wrong, "IS_PARTNER_OF"
            )
            data.append(q)
        return data

    # --- 9. IS_SIBLING_OF (Anh chị em) ---
    def gen_sibling(self, count):
        print(f"Generating {count} SIBLING questions...")
        data = []
        query = "MATCH (p1:Person)-[:IS_SIBLING_OF]->(p2:Person) RETURN p1.name as p1, p2.name as p2 LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        if not pos: return []
        people = [r['p2'] for r in pos]

        for row in pos[:count]:
            wrong = random.choice(people)
            while wrong == row['p2']: wrong = random.choice(people)
            
            q = self.create_mcq(
                f"Ai là anh/chị em với {row['p1']}?",
                row['p2'], wrong, "IS_SIBLING_OF"
            )
            data.append(q)
        return data

    # --- 10. HAS_GRANDPARENT_OF (Ông bà) ---
    def gen_grandparent(self, count):
        print(f"Generating {count} GRANDPARENT questions...")
        data = []
        query = "MATCH (child:Person)-[:HAS_GRANDPARENT_OF]->(gp:Person) RETURN child.name as c, gp.name as g LIMIT $limit"
        pos = self.run_query(query, params={"limit": count * 2})
        if not pos: return []
        gps = [r['g'] for r in pos]

        for row in pos[:count]:
            wrong = random.choice(gps)
            while wrong == row['g']: wrong = random.choice(gps)
            
            q = self.create_mcq(
                f"Ông/Bà của {row['c']} là ai?",
                row['g'], wrong, "HAS_GRANDPARENT_OF"
            )
            data.append(q)
        return data

    def save(self, data):
        random.shuffle(data)
        # Cắt đúng 875 câu
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
    gen = Level1Generator(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    all_data = []
    
    # Chia đều 875 câu cho khoảng 9-10 loại quan hệ (~90-100 câu/loại)
    # Nếu loại nào thiếu dữ liệu, các loại khác sẽ bù vào (do list extend)
    
    all_data.extend(gen.gen_acted_in(100))
    all_data.extend(gen.gen_directed(100))
    all_data.extend(gen.gen_produced(100))
    all_data.extend(gen.gen_parents(150)) # Cha + Mẹ
    all_data.extend(gen.gen_children(100))
    all_data.extend(gen.gen_spouse(100))
    all_data.extend(gen.gen_partner(100))
    all_data.extend(gen.gen_sibling(100))
    all_data.extend(gen.gen_grandparent(100))
    
    gen.save(all_data)
    gen.close()