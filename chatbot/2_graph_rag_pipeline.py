import sys
import os
import re
from dotenv import load_dotenv
from neo4j import GraphDatabase
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_huggingface import HuggingFacePipeline

# Load environment variables from project root
# Tìm file .env ở thư mục cha nếu chạy từ thư mục chatbot
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
    print("⏳ Đang khởi tạo hệ thống...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, torch_dtype="auto", device_map="auto"
    )
    # Tăng temperature một chút để model linh hoạt, nhưng prompt sẽ kìm lại
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=1024, temperature=0.5, top_p=0.9, do_sample=True, repetition_penalty=1.1
    )
    llm = HuggingFacePipeline(pipeline=pipe)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Tạo index nếu chưa có
    with driver.session() as session:
        session.run("CREATE FULLTEXT INDEX names IF NOT EXISTS FOR (n:Person|Film) ON EACH [n.name]")
    
    print("✅ Hệ thống đã sẵn sàng!")
    return llm, tokenizer, driver

def parse_qwen3_output(text):
    # Lọc bỏ thẻ think và các dòng thừa
    if "<think>" in text:
        text = text.split("</think>")[-1]
    return text.strip()

# --- 2. TRÍCH XUẤT THỰC THỂ (FEW-SHOT) ---
def extract_entity(llm, tokenizer, question):
    examples = """
    Hỏi: Ai là đạo diễn phim Titanic? -> Thực thể: Titanic
    Hỏi: Angelina Jolie con ai? -> Thực thể: Angelina Jolie
    Hỏi: Tom Hanks đóng phim gì? -> Thực thể: Tom Hanks
    """
    messages = [
        {"role": "system", "content": "Bạn là công cụ trích xuất thực thể. Chỉ trả về TÊN RIÊNG của phim hoặc người trong câu hỏi. Không giải thích."},
        {"role": "user", "content": f"Đây là các ví dụ mẫu :\n{examples}\n. Đây là câu hỏi cần bạn trả lời: {question}\nThực thể:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    entity = parse_qwen3_output(res).split('\n')[0].replace("Thực thể:", "").strip()
    print(f"  🔍 Trích xuất: '{entity}'")
    return entity


# --- 3. TRUY XUẤT ĐỒ THỊ (CẬP NHẬT ĐẦY ĐỦ QUAN HỆ) ---
def get_graph_context(driver, entity_name):
    with driver.session() as session:
        # 1. Tìm Node chính xác (Giữ nguyên)
        node = session.run("""
            CALL db.index.fulltext.queryNodes("names", $name + "~") YIELD node, score
            RETURN node.name AS name, node.qid AS qid, labels(node) AS labels, score
            ORDER BY score DESC LIMIT 1
        """, name=entity_name).single()

        if not node: return None, None
        
        main_name = node["name"]
        main_qid = node["qid"]
        main_label = "Film" if "Film" in node["labels"] else "Person"
        print(f"  🔗 Tìm thấy: {main_name} ({main_label})")

        # 2. Lấy quan hệ (Tăng LIMIT lên chút để lấy nhiều thông tin hơn)
        query = """
            MATCH (main {qid: $qid})-[r]-(neighbor)
            RETURN startNode(r).qid AS start_id, type(r) AS rel_type, neighbor.name AS neighbor_name, labels(neighbor) AS neighbor_labels
            LIMIT 40
        """
        results = session.run(query, qid=main_qid).data()

        # 3. Xây dựng văn bản ngữ cảnh (Logic mở rộng)
        context_lines = []
        for row in results:
            rel = row['rel_type']
            neighbor = row['neighbor_name']
            is_outgoing = (row['start_id'] == main_qid) # True nếu Main -> Neighbor (Chiều đi)

            sentence = ""
            
            # --- LOGIC CHO NGƯỜI (PERSON / ACTORDIRECTOR) ---
            if main_label == "Person":
                if rel == "ACTED_IN":
                    sentence = f"{main_name} đã đóng trong phim {neighbor}."
                elif rel == "DIRECTED":
                    sentence = f"{main_name} là đạo diễn của phim {neighbor}."
                elif rel == "PRODUCED":
                    sentence = f"{main_name} đã sản xuất phim {neighbor}."
                
                # Quan hệ gia đình/xã hội
                elif rel == "IS_CHILD_OF":
                    # (Con)-[:IS_CHILD_OF]->(Cha/Mẹ)
                    if is_outgoing: sentence = f"{main_name} là con của {neighbor}."
                    else: sentence = f"{neighbor} là con của {main_name}." # (Cha/Mẹ)<-[:IS_CHILD_OF]-(Con)
                
                elif rel == "IS_PARENT_OF": # P40
                    # (Cha/Mẹ)-[:IS_PARENT_OF]->(Con)
                    if is_outgoing: sentence = f"{main_name} là cha/mẹ của {neighbor}."
                    else: sentence = f"{neighbor} là cha/mẹ của {main_name}."

                elif rel == "IS_SPOUSE_OF": # P26
                    sentence = f"{main_name} là vợ/chồng của {neighbor}."
                
                elif rel == "IS_PARTNER_OF": # P451
                    sentence = f"{main_name} là bạn đời/bạn tình của {neighbor}."
                
                elif rel == "IS_SIBLING_OF": # P3373
                    sentence = f"{main_name} là anh/chị em với {neighbor}."
                
                elif rel == "HAS_GRANDPARENT_OF": # P1038
                    # (Cháu)-[:HAS_GRANDPARENT_OF]->(Ông/Bà)
                    if is_outgoing: sentence = f"{main_name} có ông/bà là {neighbor}."
                    else: sentence = f"{neighbor} là cháu của {main_name}."

            # --- LOGIC CHO PHIM (FILM) ---
            elif main_label == "Film":
                if rel == "ACTED_IN":
                    # (Actor)-[:ACTED_IN]->(Film)
                    sentence = f"Phim {main_name} có diễn viên {neighbor} tham gia."
                elif rel == "DIRECTED":
                    # (Director)-[:DIRECTED]->(Film)
                    sentence = f"Phim {main_name} được đạo diễn bởi {neighbor}."
                elif rel == "PRODUCED":
                    # (Producer)-[:PRODUCED]->(Film)
                    sentence = f"Phim {main_name} được sản xuất bởi {neighbor}."

            if sentence:
                context_lines.append(sentence)

        if not context_lines:
            return main_name, "Không có thông tin kết nối nào trong cơ sở dữ liệu."
            
        # Gộp các câu lại thành một đoạn văn
        return main_name, "\n".join(context_lines)

# --- 4. TẠO CÂU TRẢ LỜI (ANTI-HALLUCINATION) ---
def generate_answer(llm, tokenizer, question, context):
    if not context: return "Tôi không tìm thấy thông tin này trong dữ liệu."

    # Prompt cực kỳ nghiêm ngặt để chống bịa đặt
    system_prompt = """Bạn là trợ lý AI trung thực.
    CHỈ trả lời dựa trên "THÔNG TIN ĐƯỢC CUNG CẤP" bên dưới.
    - Nếu thông tin có trong danh sách -> Trả lời ngắn gọn.
    - Nếu thông tin KHÔNG có trong danh sách -> BẮT BUỘC trả lời: "Trong dữ liệu của tôi không có thông tin này."
    - TUYỆT ĐỐI KHÔNG tự bịa ra tên người không có trong danh sách."""

    user_content = f"""THÔNG TIN ĐƯỢC CUNG CẤP:
    {context}

    CÂU HỎI: {question}
    TRẢ LỜI:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    # Enable thinking để model "tự kiểm tra" xem có info hay không
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res: res = res.replace(prompt, "")
    return parse_qwen3_output(res)

# --- MAIN LOOP ---
def main():
    llm, tokenizer, driver = init_system()
    while True:
        q = input("\n💬 Câu hỏi (exit): ")
        if q in ["exit", "quit"]: break
        
        entity = extract_entity(llm, tokenizer, q)
        if not entity: continue
        
        name, ctx = get_graph_context(driver, entity)
        
        # Debug: In ra context để bạn kiểm tra xem Neo4j trả về gì
        print(f"\n📄 [DEBUG] Context gửi cho Model:\n{ctx}\n")
        
        print("🤖 Bot đang suy nghĩ...")
        ans = generate_answer(llm, tokenizer, q, ctx)
        print(f"💡 KẾT QUẢ: {ans}")
    driver.close()

if __name__ == "__main__":
    main()