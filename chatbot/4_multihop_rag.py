
import os
import re
from datetime import datetime
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

# --- 1. KHỞI TẠO ---
def init_system():
    print("⏳ Đang khởi tạo hệ thống Multi-hop V3...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto", device_map="auto")
    
    # Cấu hình cho Thinking Mode (theo tài liệu Qwen3)
    # Temperature=0.6, TopP=0.95, TopK=20, MinP=0
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=32768, # Tăng token tối đa theo hướng dẫn Qwen3
        temperature=0.6, 
        top_p=0.95, 
        top_k=20,
        do_sample=True, 
        repetition_penalty=1.1
    )
    llm = HuggingFacePipeline(pipeline=pipe)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Tự động tạo Fulltext Index nếu chưa có
    with driver.session() as session:
        print("🛠️ Đang kiểm tra và tạo chỉ mục tìm kiếm (Fulltext Index)...")
        session.run("""
            CREATE FULLTEXT INDEX names IF NOT EXISTS 
            FOR (n:Person|Film) ON EACH [n.name]
        """)
        
    print("✅ Hệ thống đã sẵn sàng!")
    return llm, tokenizer, driver

def parse_qwen3_output(text):
    if "<think>" in text: text = text.split("</think>")[-1]
    return text.strip()

# --- 2. TRÍCH XUẤT THỰC THỂ (CÓ BỘ LỌC CHỐNG ẢO GIÁC) ---
def extract_entities(llm, tokenizer, question):
    examples = """
    Ví dụ:
    Câu hỏi: Ai là đạo diễn phim Titanic?
    Thực thể: Titanic

    Câu hỏi: Mối quan hệ giữa Leonardo DiCaprio và Kathy Bates là gì?
    Thực thể: Leonardo DiCaprio, Kathy Bates
    """
    
    messages = [
        {"role": "system", "content": "Bạn là công cụ trích xuất thực thể. Nhiệm vụ: Liệt kê các TÊN RIÊNG (Người, Phim) xuất hiện trong câu hỏi. Ngăn cách bởi dấu phẩy. TUYỆT ĐỐI KHÔNG thêm tên không có trong câu hỏi."},
        {"role": "user", "content": f"{examples}\n\nNhiệm vụ thực tế:\nCâu hỏi: {question}\nThực thể:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    
    raw_text = parse_qwen3_output(res).split('\n')[0].replace("Thực thể:", "").strip()
    
    # Tách danh sách
    candidates = [e.strip() for e in raw_text.split(',') if e.strip()]
    candidates = [e.replace(".", "").replace('"', '') for e in candidates]
    
    # --- BỘ LỌC THÔNG MINH (GUARDRAIL) ---
    valid_entities = []
    print(f"  🤔 Model đề xuất: {candidates}")
    
    for entity in candidates:
        # Kiểm tra xem entity có thực sự nằm trong câu hỏi không (không phân biệt hoa thường)
        if entity.lower() in question.lower():
            valid_entities.append(entity)
        else:
            print(f"  ❌ Loại bỏ ảo giác: '{entity}' (Không có trong câu hỏi)")
            
    print(f"  🔍 Thực thể hợp lệ: {valid_entities}")
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

# --- 3. XỬ LÝ NGỮ PHÁP ĐƯỜNG ĐI ---
def format_path_context(path):
    nodes = path.nodes
    relationships = path.relationships
    text_parts = []
    
    text_parts.append(f"Mối liên hệ chuỗi giữa {nodes[0]['name']} và {nodes[-1]['name']}:")
    
    for i, rel in enumerate(relationships):
        db_start_node = rel.start_node 
        current_node = nodes[i]
        next_node = nodes[i+1]
        rel_type = rel.type
        
        # Kiểm tra hướng mũi tên
        is_forward = (db_start_node.element_id == current_node.element_id) 
        
        action = ""
        if rel_type == "ACTED_IN":
            if is_forward: action = "đã đóng trong phim"     # Actor -> Film
            else: action = "có diễn viên là"                # Film <- Actor
        elif rel_type == "DIRECTED":
            if is_forward: action = "đã đạo diễn phim"
            else: action = "được đạo diễn bởi"
        elif rel_type == "IS_CHILD_OF":
            if is_forward: action = "là con của"            # Child -> Parent
            else: action = "là cha/mẹ của"                  # Parent <- Child
        elif rel_type == "IS_SPOUSE_OF":
            action = "là vợ/chồng của"
        elif rel_type == "IS_PARTNER_OF":
            action = "là bạn đời của"
        else:
            action = f"có quan hệ {rel_type} với"

        text_parts.append(f"{i+1}. {current_node['name']} {action} {next_node['name']}.")
        
    return "\n".join(text_parts)

# --- 4. TRUY XUẤT & TÌM ĐƯỜNG ---
def get_graph_context(driver, entity_names):
    if not entity_names: return None, "Không tìm thấy tên riêng hợp lệ."
    
    with driver.session() as session:
        found_nodes = []
        for name in entity_names:
            node = find_node_qid(session, name)
            if node: found_nodes.append(node)
        
        if not found_nodes: return None, "Không tìm thấy đối tượng trong DB."
        print(f"  🔗 Đã map node: {[n['name'] for n in found_nodes]}")

        # --- LOGIC MULTI-HOP (CHỌN ĐIỂM ĐẦU & CUỐI) ---
        if len(found_nodes) >= 2:
            start_node = found_nodes[0]
            end_node = found_nodes[-1] # Luôn lấy người đầu và người cuối để tìm đường
            
            print(f"  🚀 Tìm đường ShortestPath từ '{start_node['name']}' đến '{end_node['name']}'...")
            
            # Tìm đường đi ngắn nhất (tối đa 4 bước nhảy)
            query = """
                MATCH (p1 {qid: $start_id}), (p2 {qid: $end_id})
                MATCH path = shortestPath((p1)-[*..10]-(p2))
                RETURN path
            """
            result = session.run(query, start_id=start_node["qid"], end_id=end_node["qid"]).single()
            
            if result:
                path = result["path"]
                # --- IN CHI TIẾT ĐƯỜNG ĐI ĐỂ DEBUG ---
                print("\n" + "="*40)
                print("🔍 CHI TIẾT ĐƯỜNG ĐI (DEBUG):")
                for i, node in enumerate(path.nodes):
                    print(f"  Node {i}: {node.get('name')} (Labels: {list(node.labels)}, QID: {node.get('qid')})")
                for i, rel in enumerate(path.relationships):
                    print(f"  Rel {i}: ({rel.start_node.get('name')}) -[{rel.type}]-> ({rel.end_node.get('name')})")
                print("="*40 + "\n")
                # -------------------------------------

                test_result = format_path_context(path)
                print(f"  🛤️ Đường đi tìm được:\n{test_result}")
                return f"Quan hệ {start_node['name']} - {end_node['name']}", format_path_context(path)

            else:
                return None, f"Không tìm thấy đường đi kết nối trực tiếp giữa {start_node['name']} và {end_node['name']}."

        # --- LOGIC 1-HOP ---
        elif len(found_nodes) == 1:
            main_node = found_nodes[0]
            query = """
                MATCH (main {qid: $qid})-[r]-(neighbor)
                RETURN startNode(r).qid AS start_id, type(r) AS rel_type, neighbor.name AS neighbor_name
                LIMIT 20
            """
            results = session.run(query, qid=main_node["qid"]).data()
            
            # (Tái sử dụng logic format đơn giản cho 1-hop)l
            lines = [f"Thông tin về {main_node['name']}:"]
            for row in results:
                rel = row['rel_type']
                neigh = row['neighbor_name']
                is_out = (row['start_id'] == main_node["qid"])
                
                txt = rel
                if rel == "ACTED_IN": txt = "đóng phim" if is_out else "có diễn viên"
                elif rel == "IS_CHILD_OF": txt = "là con của" if is_out else "là cha/mẹ của"
                # ... (các map khác tương tự)
                lines.append(f"- {txt} {neigh}")
            
            return main_node["name"], "\n".join(lines)

def generate_answer(llm, tokenizer, question, context):
    if not context or "Không tìm thấy" in context: return context
    
    messages = [
        {"role": "system", "content": "Bạn là trợ lý điện ảnh. Dựa vào thông tin kết nối được cung cấp, hãy mô tả mối quan hệ giữa hai người một cách tự nhiên."},
        {"role": "user", "content": f"THÔNG TIN:\n{context}\n\nCÂU HỎI: {question}\nTRẢ LỜI:"}
    ]
    # Bật thinking mode theo tài liệu Qwen3
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
        if not entities: 
            print("⚠️ Không tìm thấy thực thể nào trong câu hỏi.")
            continue
        
        name, ctx = get_graph_context(driver, entities)
        print(f"\n📄 [DEBUG] Context:\n{ctx}\n")
        
        print("🤖 Bot đang suy nghĩ...")
        ans = generate_answer(llm, tokenizer, q, ctx)
        print(f"💡 KẾT QUẢ: {ans}")
    driver.close()

if __name__ == "__main__":
    main()