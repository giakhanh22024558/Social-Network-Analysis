import sys
import re
from itertools import combinations
from rapidfuzz import process, fuzz
from neo4j import GraphDatabase
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_huggingface import HuggingFacePipeline

# --- CẤU HÌNH ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789" # <--- Thay mật khẩu của bạn
MODEL_ID = "Qwen/Qwen3-0.6B"
MAX_ITERATIONS = 5 # Giới hạn số vòng lặp tối đa

# --- 1. KHỞI TẠO ---
def init_system():
    print("⏳ Đang khởi tạo hệ thống Iterative RAG...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto", device_map="auto")
    
    # Temperature thấp để đánh giá (Evaluation) chính xác
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=32768, temperature=0.6, top_p=0.95, top_k=20, min_p=0, repetition_penalty=1.1, 
    )
    llm = HuggingFacePipeline(pipeline=pipe)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Load all entity names for normalization
    print("⏳ Đang tải danh sách thực thể từ Neo4j để chuẩn hóa...")
    all_names = []
    try:
        with driver.session() as session:
            # Lấy tất cả tên của các node có thuộc tính name
            result = session.run("MATCH (n) WHERE n.name IS NOT NULL RETURN DISTINCT n.name as name")
            all_names = [r["name"] for r in result]
        print(f"✅ Đã tải {len(all_names)} tên thực thể.")
    except Exception as e:
        print(f"⚠️ Không thể tải danh sách thực thể: {e}")

    print("✅ Hệ thống đã sẵn sàng!")
    return llm, tokenizer, driver, all_names

def parse_qwen3_output(text):
    if "<think>" in text: text = text.split("</think>")[-1]
    return text.strip()

# --- 2. CÁC HÀM TRÍCH XUẤT ---

def extract_initial_entities(llm, tokenizer, question):

    examples = """
    Hỏi: Ai là đạo diễn phim Titanic? câu hỏi này có 1 thực thể -> Thực thể: Titanic
    Hỏi: Jon Voight là ai và có quan hệ gì với Angelina Jolie? câu hỏi này có 2 thực thể-> Thực thể: Jon Voight, Angelina Jolie
    Hỏi: Brad Pitt và Leonardo DiCaprio có đóng chung phim Titanic không? câu hỏi này có 3 thực thể -> Thực thể: Brad Pitt, Leonardo DiCaprio, Titanic
    """
    messages = [
        {"role": "system", "content": "Trích xuất các TÊN RIÊNG (Người, Phim) từ câu hỏi (có thể 1, 2 hoặc có lớn hơn 2 thực thể (3,4,5,6, ..)). Ngăn cách bởi dấu phẩy. Không thêm từ thừa."},
        {"role": "user", "content": f"Đây là các ví dụ{examples}\n. Đây là câu hỏi cần trích xuất: {question}\nThực thể:"}
    ]
    """Vòng 1: Trích xuất từ câu hỏi gốc"""

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True) # Bật thinking để suy luận
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    
    raw = parse_qwen3_output(res).split('\n')[0].replace("Thực thể:", "").strip()
    print(f"   [DEBUG] Raw entities extraction: {raw}")
    return clean_entities(raw, question)

def extract_more_entities(llm, tokenizer, question, current_context):
    """Vòng >1: Trích xuất thêm thực thể từ ngữ cảnh đã tìm được"""
    # Prompt thông minh để model biết cần tìm thêm ai
    system_msg = """Bạn là trợ lý suy luận. 
    Dựa vào CÂU HỎI và THÔNG TIN ĐÃ BIẾT, hãy xác định xem cần tìm kiếm thêm thông tin về NHÂN VẬT hoặc BỘ PHIM nào nữa để trả lời trọn vẹn câu hỏi.
    Chỉ liệt kê tên riêng mới. Nếu không cần thêm ai, trả về 'NONE'."""
    
    user_msg = f"""CÂU HỎI: {question}
    THÔNG TIN ĐÃ BIẾT:
    {current_context}
    
    Cần tìm thêm thông tin về ai (Tên riêng)?"""
    
    messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True) # Bật thinking để suy luận
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    
    raw = parse_qwen3_output(res)
    print(f"   [DEBUG] Raw more entities extraction: {raw}")
    # Nếu model nói NONE hoặc không tìm thấy gì
    if "NONE" in raw or "không cần" in raw.lower():
        return []
    
    # Lấy dòng đầu tiên chứa tên
    return clean_entities(raw, raw) # Lọc tên từ chính output

def clean_entities(raw_text, source_text):
    candidates = [e.strip() for e in raw_text.split(',') if e.strip()]
    candidates = [e.replace(".", "").replace('"', '').replace("'", "") for e in candidates]
    # Chỉ giữ lại những từ có vẻ là tên riêng (Viết hoa chữ cái đầu hoặc có trong source)
    valid = []
    for c in candidates:
        if len(c) > 2: # Bỏ rác ngắn
            valid.append(c)
    return valid

def normalize_entities(entities, all_names, threshold=85):
    """Chuẩn hóa tên thực thể bằng cách so khớp với DB"""
    if not all_names: return entities
    
    normalized = []
    if entities:
        print(f"   [NORM] Input: {entities}")
    
    for entity in entities:
        # Dùng WRatio để so khớp (xử lý tốt viết tắt, sai trật tự)
        match = process.extractOne(entity, all_names, scorer=fuzz.WRatio)
        if match:
            best_name, score, _ = match
            if score >= threshold:
                print(f"   [NORM] '{entity}' -> '{best_name}' (Score: {score:.1f})")
                normalized.append(best_name)
            else:
                # Nếu điểm thấp quá thì loại bỏ
                print(f"   [NORM] '{entity}' -> Loại bỏ (Score: {score:.1f} < {threshold})")
        else:
            normalized.append(entity)
            
    return list(set(normalized))

# --- 3. KIỂM TRA ĐỘ ĐẦY ĐỦ (EVALUATOR) ---
def check_sufficiency(llm, tokenizer, question, context):
    """Hỏi model xem thông tin đã đủ chưa"""
    if not context: return False, "Chưa có thông tin."
    
    messages = [
        {"role": "system", "content": "Bạn là giám khảo khắt khe. Nhiệm vụ: Đánh giá xem thông tin được cung cấp đã ĐỦ để trả lời chính xác câu hỏi chưa. Chỉ trả lời 'ĐỦ' hoặc 'CHƯA ĐỦ'."},
        {"role": "user", "content": f"CÂU HỎI: {question}\nTHÔNG TIN:\n{context}\n\nĐánh giá:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True) # Bật thinking để suy luận
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    
    answer = parse_qwen3_output(res).lower()
    print(f"   [DEBUG] Sufficiency check raw: {answer}")
    is_sufficient = "đủ" in answer and "chưa" not in answer
    return is_sufficient, answer

# --- 4. TRUY XUẤT ĐỒ THỊ (TÁI SỬ DỤNG V5 - FULL MESH) ---
def find_node_qid(session, name):
    result = session.run("CALL db.index.fulltext.queryNodes('names', $name + '~') YIELD node, score RETURN node.name, node.qid, labels(node) ORDER BY score DESC LIMIT 1", name=name).single()
    if result: return {"name": result[0], "qid": result[1], "labels": result[2]}
    return None

def get_node_details_text(session, qid, name):
    # node = session.run("MATCH (n {qid: $qid}) RETURN n.gender, n.birthDate, n.occupations", qid=qid).single()
    # if not node: return ""
    # info = [f"**{name}:**"]
    # if node[0]: info.append(f"Giới tính: {node[0]}")
    # if node[1]: info.append(f"Sinh: {str(node[1]).split('T')[0]}")
    # if node[2]: info.append(f"Nghề: {node[2] if isinstance(node[2], str) else ', '.join(node[2])}")
    # return " - ".join(info)
    node = session.run("MATCH (n {qid: $qid}) RETURN n.gender, n.birthDate", qid=qid).single()
    if not node: return ""
    info = [f"**{name}:**"]
    if node[0]: info.append(f"Giới tính: {node[0]}")
    if node[1]: info.append(f"Sinh: {str(node[1]).split('T')[0]}")
    return " - ".join(info)

def get_relationship_action(rel_type, is_forward):
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
    elif rel_type == "HAS_GRANDPARENT_OF":
        action = "là cháu của" if is_forward else "là ông/bà của"
    else:
        action = f"có quan hệ {rel_type} với"
    return action

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
        
        action = get_relationship_action(rel.type, is_forward)
            
        parts.append(f"{start['name']} {action} {end['name']}")
        
    return " -> ".join(parts) + "."

def get_full_graph_context(driver, entity_names):
    with driver.session() as session:
        nodes = []
        for name in entity_names:
            n = find_node_qid(session, name)
            if n: nodes.append(n)
        
        if not nodes: return "Không tìm thấy node nào."
        
        context_parts = []
        
        # 1. Thông tin chi tiết
        context_parts.append("--- THÔNG TIN CÁ NHÂN ---")
        for n in nodes:
            context_parts.append(get_node_details_text(session, n['qid'], n['name']))
            
        # 2. Quan hệ (Full Mesh)
        context_parts.append("\n--- MỐI QUAN HỆ ---")
        
        # PHẦN 1: Luôn lấy các mối quan hệ trực tiếp (1-hop) cho TỪNG node
        # (Dù có 1 hay nhiều node, ta vẫn cần biết xung quanh họ có gì)
        for n in nodes:
            # Giới hạn số lượng quan hệ để tránh quá tải context (ví dụ: 15 quan hệ mỗi người)
            res = session.run("MATCH (n {qid: $id})-[r]-(m) RETURN r, n, m LIMIT 50", id=n['qid'])
            
            has_rel = False
            for record in res:
                r = record['r']
                n_node = record['n']
                m_node = record['m']
                
                is_forward = (r.start_node.element_id == n_node.element_id)
                action = get_relationship_action(r.type, is_forward)
                
                context_parts.append(f"{n_node['name']} {action} {m_node['name']}")
                has_rel = True
            
            if not has_rel:
                context_parts.append(f"{n['name']} không có quan hệ nào trong DB.")

        # PHẦN 2: Nếu có >= 2 Node -> Tìm đường giữa TẤT CẢ CÁC CẶP (All Pairs)
        if len(nodes) >= 2:
            context_parts.append("\n--- LIÊN KẾT GIỮA CÁC THỰC THỂ ---")
            # Tạo các cặp đôi (Combinations)
            # Ví dụ: [A, B, C] -> (A,B), (A,C), (B,C)
            pairs = list(combinations(nodes, 2))
            
            print(f"  🚀 Đang tìm đường cho {len(pairs)} cặp node...")
            
            has_path = False
            for start, end in pairs:
                # Tìm đường ngắn nhất (tối đa 6 bước để tránh lan man)
                query = """
                    MATCH (p1 {qid: $s}), (p2 {qid: $e})
                    MATCH path = shortestPath((p1)-[*..6]-(p2))
                    RETURN path
                """
                result = session.run(query, s=start['qid'], e=end['qid']).single()
                
                if result:
                    path_text = format_path_text(result['path'])
                    context_parts.append(f"- Quan hệ giữa {start['name']} và {end['name']}: {path_text}")
                    has_path = True
                else:
                    context_parts.append(f"- Không tìm thấy liên kết trực tiếp giữa {start['name']} và {end['name']}.")
            
            if not has_path:
                context_parts.append("(Các thực thể này có vẻ không liên quan đến nhau trong dữ liệu hiện có)")
                    
        full_context = "\n".join(context_parts)
        print(f"   [DEBUG] Graph Context Retrieved ({len(full_context)} chars):\n{full_context}...")
        return full_context

# --- 5. TẠO CÂU TRẢ LỜI ---
def generate_final_answer(llm, tokenizer, question, context):
    messages = [
        {"role": "system", "content": "Bạn là trợ lý thông minh. Hãy trả lời câu hỏi dựa trên thông tin đã thu thập được."},
        {"role": "user", "content": f"DỮ LIỆU:\n{context}\n\nCÂU HỎI: {question}\nTRẢ LỜI:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    final_res = parse_qwen3_output(res)
    print(f"   [DEBUG] Final Answer Raw: {final_res}")
    return final_res

# --- MAIN LOOP (ITERATIVE) ---
def main():
    llm, tokenizer, driver, all_names = init_system()
    
    while True:
        question = input("\n💬 Câu hỏi (exit): ")
        if question in ["exit", "quit"]: break
        
        # Tập hợp tất cả thực thể đã tìm thấy qua các vòng
        accumulated_entities = set()
        current_context = ""
        
        print("\n🚀 BẮT ĐẦU VÒNG LẶP SUY LUẬN...")
        
        for i in range(MAX_ITERATIONS):
            print(f"\n--- VÒNG {i+1} ---")
            
            # BƯỚC 1: TRÍCH XUẤT
            new_entities = []
            if i == 0:
                # Vòng 1: Lấy từ câu hỏi
                new_entities = extract_initial_entities(llm, tokenizer, question)
            else:
                # Vòng > 1: Lấy từ ngữ cảnh cũ (Suy luận)
                print("🤔 Đang suy luận tìm thêm thực thể liên quan...")
                new_entities = extract_more_entities(llm, tokenizer, question, current_context)
            
            # Chuẩn hóa thực thể
            new_entities = normalize_entities(new_entities, all_names)
            
            # Cập nhật danh sách thực thể
            prev_len = len(accumulated_entities)
            for e in new_entities:
                accumulated_entities.add(e)
            
            print(f"  🔍 Thực thể hiện có: {list(accumulated_entities)}")
            
            if len(accumulated_entities) == prev_len and i > 0:
                print("  🛑 Không tìm thấy thực thể mới. Dừng lặp.")
                break # Nếu không tìm thêm được ai thì dừng
                
            # BƯỚC 2: TRUY XUẤT GRAPH
            # Mỗi vòng đều truy xuất lại với danh sách thực thể ngày càng đầy đủ
            print("  🔗 Đang truy xuất Đồ thị cho toàn bộ danh sách...")
            current_context = get_full_graph_context(driver, list(accumulated_entities))
            
            # print(f"  📄 Context Vòng {i+1}:\n{current_context[:500]}...") # Debug
            
            # BƯỚC 3: KIỂM TRA ĐỘ ĐẦY ĐỦ
            print("  ⚖️ Đang tự đánh giá thông tin...")
            is_enough, reason = check_sufficiency(llm, tokenizer, question, current_context)
            print(f"  -> Đánh giá của Model: {reason.upper()}")
            
            if is_enough:
                print("  ✅ Thông tin đã ĐỦ. Kết thúc suy luận.")
                break
            else:
                print("  ⚠️ Thông tin CHƯA ĐỦ. Tiếp tục vòng sau.")

        # KẾT THÚC VÒNG LẶP -> TRẢ LỜI
        print("\n🏁 TỔNG HỢP CÂU TRẢ LỜI CUỐI CÙNG:")
        final_ans = generate_final_answer(llm, tokenizer, question, current_context)
        print(f"💡 {final_ans}")

    driver.close()

if __name__ == "__main__":
    main()