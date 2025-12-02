import sys
import csv
import random
import json
from neo4j import GraphDatabase


import os
import re
from dotenv import load_dotenv
from neo4j import GraphDatabase
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_huggingface import HuggingFacePipeline

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
dotenv_path = os.path.join(root_dir, '.env')
load_dotenv(dotenv_path)

# --- CẤU HÌNH ---
# Ưu tiên lấy từ .env, nếu không có thì dùng giá trị mặc định
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456789")
MODEL_ID = "Qwen/Qwen3-0.6B" # Qwen3-0.6B đã public
OUTPUT_FILE = "evaluation_dataset_2000.csv"
TARGET_TOTAL = 2500 # Sinh dư ra một chút để lọc sau

class DatasetGenerator:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        self.driver.close()

    def run_query(self, query, params=None):
        with self.driver.session() as session:
            return session.run(query, params).data()

    # --- LOẠI 1: CÂU HỎI YES/NO (ACTOR - FILM) ---
    def generate_actor_film_questions(self, count=800):
        print(f"🔄 Đang sinh {count} câu hỏi Actor-Film (Yes/No)...")
        dataset = []
        
        # 1. Lấy mẫu dương (Positive Sample - Câu trả lời YES)
        query_pos = """
        MATCH (p:Person)-[:ACTED_IN]->(f:Film)
        RETURN p.name as actor, f.name as film
        LIMIT $limit
        """
        pos_results = self.run_query(query_pos, params={"limit": count // 2})
        
        for row in pos_results:
            dataset.append({
                "type": "1-hop_YesNo",
                "question": f"{row['actor']} có tham gia bộ phim '{row['film']}' không?",
                "answer": "Yes",
                "explanation": f"Đúng, {row['actor']} là diễn viên trong phim {row['film']}."
            })

        # 2. Lấy mẫu âm (Negative Sample - Câu trả lời NO)
        # Lấy diễn viên và phim KHÔNG liên quan
        query_neg = """
        MATCH (p:Person), (f:Film)
        WHERE NOT (p)-[:ACTED_IN]->(f) AND rand() < 0.1
        RETURN p.name as actor, f.name as film
        LIMIT $limit
        """
        neg_results = self.run_query(query_neg, params={"limit": count // 2})
        
        for row in neg_results:
            dataset.append({
                "type": "1-hop_YesNo",
                "question": f"{row['actor']} có tham gia bộ phim '{row['film']}' không?",
                "answer": "No",
                "explanation": f"Sai, {row['actor']} không tham gia phim {row['film']}."
            })
            
        return dataset

    # --- LOẠI 2: CÂU HỎI MULTI-HOP (CO-ACTORS) ---
    def generate_co_actor_questions(self, count=800):
        print(f"🔄 Đang sinh {count} câu hỏi Co-Actors (Multi-hop)...")
        dataset = []
        
        # 1. Mẫu Dương: 2 người cùng đóng 1 phim
        query_pos = """
        MATCH (p1:Person)-[:ACTED_IN]->(f:Film)<-[:ACTED_IN]-(p2:Person)
        WHERE elementId(p1) < elementId(p2)
        RETURN p1.name as a1, p2.name as a2, f.name as film
        LIMIT $limit
        """
        pos_results = self.run_query(query_pos, params={"limit": count // 2})
        
        for row in pos_results:
            dataset.append({
                "type": "2-hop_CoActor",
                "question": f"{row['a1']} và {row['a2']} có từng đóng chung phim nào không?",
                "answer": "Yes",
                "explanation": f"Có, họ cùng đóng trong phim '{row['film']}'."
            })

        # 2. Mẫu Âm: 2 người KHÔNG đóng chung (Random)
        # Lấy 2 diễn viên bất kỳ không có đường nối ACTED_IN chung
        query_neg = """
        MATCH (p1:Person), (p2:Person)
        WHERE elementId(p1) < elementId(p2) 
        AND NOT (p1)-[:ACTED_IN]->()<-[:ACTED_IN]-(p2)
        AND rand() < 0.05
        RETURN p1.name as a1, p2.name as a2
        LIMIT $limit
        """
        neg_results = self.run_query(query_neg, params={"limit": count // 2})
        
        for row in neg_results:
            dataset.append({
                "type": "2-hop_CoActor",
                "question": f"{row['a1']} và {row['a2']} có từng đóng chung phim nào không?",
                "answer": "No",
                "explanation": "Không, không tìm thấy phim chung nào giữa họ."
            })
            
        return dataset

    # --- LOẠI 3: TRẮC NGHIỆM (MCQ) - ĐẠO DIỄN ---
    def generate_director_mcq(self, count=500):
        print(f"🔄 Đang sinh {count} câu hỏi Trắc nghiệm Đạo diễn...")
        dataset = []
        
        # Lấy danh sách tất cả đạo diễn để làm phương án nhiễu
        all_directors = [r['d'] for r in self.run_query("MATCH (p:Person)-[:DIRECTED]->() RETURN DISTINCT p.name as d LIMIT 200")]
        if len(all_directors) < 4: 
            print("⚠️ Không đủ dữ liệu đạo diễn để sinh câu hỏi MCQ.")
            return []

        # Lấy cặp Phim - Đạo diễn đúng
        query = """
        MATCH (p:Person)-[:DIRECTED]->(f:Film)
        RETURN p.name as director, f.name as film
        LIMIT $limit
        """
        results = self.run_query(query, params={"limit": count})
        
        for row in results:
            correct = row['director']
            film = row['film']
            
            # Chọn 3 đáp án sai ngẫu nhiên
            distractors = random.sample([d for d in all_directors if d != correct], 3)
            options = distractors + [correct]
            random.shuffle(options)
            
            # Xác định index đáp án đúng (A, B, C, D)
            labels = ['A', 'B', 'C', 'D']
            correct_idx = options.index(correct)
            correct_label = labels[correct_idx]
            
            # Format câu hỏi
            q_text = f"Ai là đạo diễn của phim '{film}'?\n"
            for i, opt in enumerate(options):
                q_text += f"{labels[i]}. {opt}\n"
                
            dataset.append({
                "type": "MCQ_Director",
                "question": q_text.strip(),
                "answer": correct_label,
                "explanation": f"Đạo diễn của '{film}' là {correct}."
            })
            
        return dataset

    # --- LOẠI 4: QUAN HỆ GIA ĐÌNH (Family) ---
    def generate_family_questions(self, count=400):
        print(f"🔄 Đang sinh {count} câu hỏi Gia đình...")
        dataset = []
        
        query = """
        MATCH (child:Person)-[:IS_CHILD_OF]->(parent:Person)
        RETURN child.name as c, parent.name as p
        LIMIT $limit
        """
        results = self.run_query(query, params={"limit": count})
        
        for row in results:
            # Câu hỏi xuôi
            dataset.append({
                "type": "Family",
                "question": f"Cha/Mẹ của {row['c']} là ai?",
                "answer": row['p'],
                "explanation": f"{row['p']} là cha/mẹ của {row['c']}."
            })
            # Câu hỏi ngược (False)
            dataset.append({
                "type": "Family_YesNo",
                "question": f"{row['c']} có phải là cha/mẹ của {row['p']} không?",
                "answer": "No",
                "explanation": f"Sai, {row['c']} là con của {row['p']}."
            })
            
        return dataset

    def save_to_csv(self, dataset):
        print(f"\n💾 Đang lưu {len(dataset)} câu hỏi vào {OUTPUT_FILE}...")
        keys = ["type", "question", "answer", "explanation"]
        
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(dataset)
        print("✅ Hoàn tất!")

# --- MAIN ---
def main():
    gen = DatasetGenerator(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    all_data = []
    
    # 1. Sinh câu hỏi Yes/No (Actor-Film)
    all_data.extend(gen.generate_actor_film_questions(800))
    
    # 2. Sinh câu hỏi Multi-hop (Co-Actors)
    all_data.extend(gen.generate_co_actor_questions(800))
    
    # 3. Sinh câu hỏi MCQ (Đạo diễn)
    all_data.extend(gen.generate_director_mcq(500))
    
    # 4. Sinh câu hỏi Gia đình
    all_data.extend(gen.generate_family_questions(400))
    
    # Xáo trộn dữ liệu
    random.shuffle(all_data)
    
    # Lưu file
    gen.save_to_csv(all_data)
    gen.close()

if __name__ == "__main__":
    main()