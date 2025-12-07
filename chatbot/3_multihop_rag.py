
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from itertools import combinations
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

# --- 1. KHỞI TẠO ---
def init_system():
    print("⏳ Đang khởi tạo hệ thống RAG V5 (Full Mesh Context)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto", device_map="auto")
    
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=32768, temperature=0.6, top_p=0.95, top_k=20, do_sample=True, repetition_penalty=1.1
    )
    llm = HuggingFacePipeline(pipeline=pipe)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    print("✅ Hệ thống đã sẵn sàng!")
    return llm, tokenizer, driver

def parse_qwen3_output(text):
    if "<think>" in text: text = text.split("</think>")[-1]
    return text.strip()

# --- 2. TRÍCH XUẤT THỰC THỂ ---
def extract_entities(llm, tokenizer, question):
    examples = """
    Hỏi: Ai là đạo diễn phim Titanic? câu hỏi này có 1 thực thể -> Thực thể: Titanic
    Hỏi: Jon Voight là ai và có quan hệ gì với Angelina Jolie? câu hỏi này có 2 thực thể-> Thực thể: Jon Voight, Angelina Jolie
    Hỏi: Brad Pitt và Leonardo DiCaprio có đóng chung phim nào không? câu hỏi này có 2 thực thể -> Thực thể: Brad Pitt, Leonardo DiCaprio
    """
    messages = [
        {"role": "system", "content": "Trích xuất các TÊN RIÊNG (Người, Phim) từ câu hỏi (có thể 1, 2 hoặc có lớn hơn 2 thực thể (3,4,5,6, ..)). Ngăn cách bởi dấu phẩy. Không thêm từ thừa."},
        {"role": "user", "content": f"{examples}\nCâu hỏi: {question}\nThực thể:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    
    raw = parse_qwen3_output(res).split('\n')[0].replace("Thực thể:", "").strip()
    candidates = [e.strip() for e in raw.split(',') if e.strip()]
    candidates = [e.replace(".", "").replace('"', '') for e in candidates]
    
    # Lọc lại để đảm bảo thực thể có trong câu hỏi (giảm ảo giác)
    valid_entities = [e for e in candidates if e.lower() in question.lower()]
    # Fallback nếu lọc quá chặt tay mà danh sách rỗng
    if not valid_entities and candidates: valid_entities = candidates
    
    print(f"  🔍 Thực thể nhận diện: {valid_entities}")
    return valid_entities

def find_node_qid(session, name):
    result = session.run("""
        CALL db.index.fulltext.queryNodes("names", $name + "~") YIELD node, score
        RETURN node.name AS name, node.qid AS qid, labels(node) AS labels, score
        ORDER BY score DESC LIMIT 1
    """, name=name).single()
    
    if result:
        return {"name": result["name"], "qid": result["qid"], "labels": result["labels"]}
    return None

# --- 3. CÁC HÀM FORMAT VĂN BẢN ---

def get_node_details_text(session, qid, name):
    """Lấy thông tin chi tiết (Property) của một Node"""
    query = """
        MATCH (n {qid: $qid})
        RETURN n.name AS name, n.gender AS gender, n.birthDate AS birthDate, n.occupations AS occupations
    """
    node_data = session.run(query, qid=qid).single()
    if not node_data: return ""
    
    info = [f"**Thông tin về {name}:**"]
    
    # Giới tính
    gender = node_data.get('gender')
    if gender:
        g_text = "Nam" if gender == 'male' else "Nữ" if gender == 'female' else gender
        info.append(f"- Giới tính: {g_text}")
    
    # Ngày sinh
    dob = node_data.get('birthDate')
    if dob: info.append(f"- Ngày sinh: {dob.split('T')[0]}")
        
    # Nghề nghiệp
    jobs = node_data.get('occupations')
    if jobs:
        j_text = ', '.join(jobs) if isinstance(jobs, list) else jobs
        info.append(f"- Nghề nghiệp: {j_text}")
        
    return "\n".join(info)

def format_path_text(path):
    """Format đường đi ngữ nghĩa"""
    nodes = path.nodes
    rels = path.relationships
    parts = []
    
    for i, rel in enumerate(rels):
        start = nodes[i]
        end = nodes[i+1]
        
        # Kiểm tra chiều mũi tên trong DB
        is_forward = (rel.start_node.element_id == start.element_id)
        
        rel_type = rel.type
        action = ""
        
        if rel_type == "ACTED_IN":
            action = "đóng trong phim" if is_forward else "có diễn viên là"
        elif rel_type == "DIRECTED":
            action = "là đạo diễn của" if is_forward else "được đạo diễn bởi"
        elif rel_type == "PRODUCED":
            action = "sản xuất phim" if is_forward else "được sản xuất bởi"
        elif rel_type == "IS_CHILD_OF":
            action = "là con của" if is_forward else "là cha/mẹ của"
        elif rel_type == "IS_CHILD_OF_DAD":
            action = "là con của cha" if is_forward else "là cha của"
        elif rel_type == "IS_CHILD_OF_MOM":
            action = "là con của mẹ" if is_forward else "là mẹ của"
        elif rel_type == "IS_PARENT_OF":
            action = "là cha/mẹ của" if is_forward else "là con của"
        elif rel_type == "IS_SPOUSE_OF":
            action = "là vợ/chồng của"
        elif rel_type == "IS_PARTNER_OF":
            action = "là bạn đời của"
        elif rel_type == "IS_SIBLING_OF":
            action = "là anh/chị em với"
        else:
            action = f"có quan hệ {rel_type} với"
            
        parts.append(f"{start['name']} {action} {end['name']}")
        
    return " -> ".join(parts) + "."

# --- 4. TRUY XUẤT ĐỒ THỊ (NÂNG CẤP V5) ---
def get_graph_context(driver, entity_names):
    if not entity_names: return None, "Không tìm thấy tên riêng."
    
    with driver.session() as session:
        # 1. Map tên sang Node
        found_nodes = []
        for name in entity_names:
            node = find_node_qid(session, name)
            if node: found_nodes.append(node)
        
        if not found_nodes: return None, "Không tìm thấy đối tượng trong DB."
        print(f"  🔗 Đã map node: {[n['name'] for n in found_nodes]}")

        final_context = []

        # ---------------------------------------------------------
        # BƯỚC 1: LẤY THÔNG TIN CHI TIẾT TỪNG NODE (CHO TẤT CẢ)
        # ---------------------------------------------------------
        final_context.append("=== THÔNG TIN CÁ NHÂN ===")
        for node in found_nodes:
            detail_text = get_node_details_text(session, node['qid'], node['name'])
            if detail_text: final_context.append(detail_text)
        
        # ---------------------------------------------------------
        # BƯỚC 2: TÌM MỐI QUAN HỆ (XỬ LÝ ĐA TRƯỜNG HỢP)
        # ---------------------------------------------------------
        final_context.append("\n=== CÁC MỐI LIÊN KẾT ===")
        
        # Trường hợp 1: Chỉ có 1 Node -> Lấy hàng xóm 1-hop
        if len(found_nodes) == 1:
            main = found_nodes[0]
            query = """
                MATCH (n {qid: $qid})-[r]-(m) 
                RETURN startNode(r).qid as sid, type(r) as t, m.name as mname 
                LIMIT 15
            """
            res = session.run(query, qid=main['qid']).data()
            lines = []
            for row in res:
                # Tái sử dụng logic format đơn giản
                is_out = (row['sid'] == main['qid'])
                t = row['t']
                act = "có quan hệ"
                if t == "ACTED_IN": act = "đóng phim" if is_out else "có diễn viên"
                elif t == "IS_CHILD_OF": act = "là con của" if is_out else "là cha/mẹ của"
                lines.append(f"- {main['name']} {act} {row['mname']}.")
            
            if lines: final_context.extend(lines)
            else: final_context.append("Không có thông tin kết nối thêm.")

        # Trường hợp 2: Có >= 2 Node -> Tìm đường giữa TẤT CẢ CÁC CẶP (All Pairs)
        else:
            # Tạo các cặp đôi (Combinations)
            # Ví dụ: [A, B, C] -> (A,B), (A,C), (B,C)
            pairs = list(combinations(found_nodes, 2))
            
            print(f"  🚀 Đang tìm đường cho {len(pairs)} cặp node...")
            
            has_path = False
            for start, end in pairs:
                # Tìm đường ngắn nhất (tối đa 3 bước để tránh lan man)
                query = """
                    MATCH (p1 {qid: $s}), (p2 {qid: $e})
                    MATCH path = shortestPath((p1)-[*..6]-(p2))
                    RETURN path
                """
                result = session.run(query, s=start['qid'], e=end['qid']).single()
                
                if result:
                    path_text = format_path_text(result['path'])
                    final_context.append(f"- Quan hệ giữa {start['name']} và {end['name']}: {path_text}")
                    has_path = True
                else:
                    final_context.append(f"- Không tìm thấy liên kết trực tiếp giữa {start['name']} và {end['name']}.")
            
            if not has_path:
                final_context.append("(Các thực thể này có vẻ không liên quan đến nhau trong dữ liệu hiện có)")

        return "Tổng hợp thông tin", "\n".join(final_context)

def generate_answer(llm, tokenizer, question, context):
    if not context: return "Tôi không có thông tin này."
    
    messages = [
        {"role": "system", "content": "Bạn là trợ lý điện ảnh thông minh. Hãy trả lời câu hỏi dựa trên thông tin chi tiết được cung cấp dưới đây."},
        {"role": "user", "content": f"DỮ LIỆU CUNG CẤP:\n{context}\n\nCÂU HỎI: {question}\nTRẢ LỜI:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    return parse_qwen3_output(res)

# --- MAIN ---
def main():
    llm, tokenizer, driver = init_system()
    while True:
        q = input("\n💬 Câu hỏi (exit): ")
        if q in ["exit", "quit"]: break
        
        entities = extract_entities(llm, tokenizer, q)
        if entities:
            name, ctx = get_graph_context(driver, entities)
            print(f"\n📄 [DEBUG] Context:\n{ctx}\n")
            print("🤖 Bot đang suy nghĩ...")
            print(f"💡 KẾT QUẢ: {generate_answer(llm, tokenizer, q, ctx)}")
        else:
            print("⚠️ Không tìm thấy thực thể.")
    driver.close()

if __name__ == "__main__":
    main()