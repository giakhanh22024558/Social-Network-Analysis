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
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456789")
MODEL_ID = "Qwen/Qwen3-0.6B"

# --- SCHEMA ĐỒ THỊ (Rất quan trọng để LLM hiểu) ---
SCHEMA_INFO = """
Node Labels: :Person, :Film, :ActorDirector
Relationship Types:
- (:Person)-[:ACTED_IN]->(:Film) (Diễn viên đóng phim)
- (:Person)-[:DIRECTED]->(:Film) (Đạo diễn phim)
- (:Person)-[:PRODUCED]->(:Film) (Sản xuất phim)
- (:Person)-[:IS_CHILD_OF]->(:Person) (Con của ai)
- (:Person)-[:IS_PARENT_OF]->(:Person) (Cha/mẹ của ai)
- (:Person)-[:IS_SPOUSE_OF]->(:Person) (Vợ/chồng của ai)
- (:Person)-[:IS_PARTNER_OF]->(:Person) (Bạn đời của ai)
- (:Person)-[:IS_SIBLING_OF]->(:Person) (Anh chị em của ai)
- (:Person)-[:HAS_GRANDPARENT_OF]->(:Person) (Cháu của ai - Ông/Bà)
"""

def init_system():
    print("⏳ Đang khởi tạo hệ thống Text-to-Cypher...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto", device_map="auto")
    
    # Cấu hình Thinking Mode
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=32768, temperature=0.6, top_p=0.95, top_k=20, do_sample=True, repetition_penalty=1.1
    )
    llm = HuggingFacePipeline(pipeline=pipe)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Tạo Index Fulltext để hỗ trợ tìm kiếm tên (quan trọng cho bước map tên)
    with driver.session() as session:
        session.run("CREATE FULLTEXT INDEX names IF NOT EXISTS FOR (n:Person|Film) ON EACH [n.name]")
        
    print("✅ Hệ thống sẵn sàng!")
    return llm, tokenizer, driver

def parse_qwen3_output(text):
    if "<think>" in text: text = text.split("</think>")[-1]
    return text.strip()

# --- 1. TRÍCH XUẤT & CHUẨN HÓA TÊN ---
# Vì người dùng có thể gõ sai tên (vd: "Angelina Joly"), ta cần tìm tên đúng trong DB trước
def normalize_entities(driver, question):
    print(f"  🔍 Đang phân tích tên thực thể trong câu hỏi: '{question}'")
    # Tìm các cụm từ viết hoa có thể là tên riêng
    potential_names = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', question)
    print(f"  📝 Các tên tiềm năng tìm thấy: {potential_names}")
    
    name_mapping = {}
    with driver.session() as session:
        for name in potential_names:
            # Bỏ qua các từ ngắn hoặc từ khóa phổ biến
            if len(name) < 3 or name in ["Who", "What", "Phim", "Dao dien"]: continue
            
            result = session.run("""
                CALL db.index.fulltext.queryNodes("names", $name + "~") YIELD node, score
                RETURN node.name AS db_name, score ORDER BY score DESC LIMIT 1
            """, name=name).single()
            
            if result and result['score'] > 0.9: # Độ tin cậy > 80%
                name_mapping[name] = result['db_name']
                print(f"    ✅ Map thành công: '{name}' -> '{result['db_name']}' (Score: {result['score']:.2f})")
            else:
                print(f"    ❌ Không tìm thấy hoặc độ tin cậy thấp cho: '{name}'")
    
    # Thay thế tên trong câu hỏi bằng tên chuẩn trong DB
    normalized_question = question
    for raw, db_name in name_mapping.items():
        normalized_question = normalized_question.replace(raw, f'"{db_name}"')
        
    return normalized_question

# --- 2. SINH CÂU LỆNH CYPHER ---
def generate_cypher(llm, tokenizer, question):
    examples = """
    Ví dụ 1:
    Câu hỏi: Ai là đạo diễn của phim "Titanic"?
    Cypher: MATCH (f:Film {name: "Titanic"})<-[:DIRECTED]-(p:Person) RETURN p.name

    Ví dụ 2:
    Câu hỏi: Cha của "Angelina Jolie" là ai?
    Cypher: MATCH (p:Person {name: "Angelina Jolie"})-[:IS_CHILD_OF]->(father) RETURN father.name

    Ví dụ 3: (Câu hỏi phức tạp - Chuỗi quan hệ)
    Câu hỏi: Đạo diễn của phim mà cha "Angelina Jolie" đóng là ai?
    Suy luận: Angelina Jolie -> Cha -> Đóng phim -> Đạo diễn
    Cypher: MATCH (p:Person {name: "Angelina Jolie"})-[:IS_CHILD_OF]->(father)-[:ACTED_IN]->(m:Film)<-[:DIRECTED]-(d:Person) RETURN d.name, m.name

    Ví dụ 4: (Câu hỏi nhiều thông tin - Vừa hỏi vợ/chồng vừa hỏi phim)
    Câu hỏi: Vợ/chồng của "Brad Pitt" là ai và anh ấy đóng phim gì?
    Cypher: MATCH (p:Person {name: "Brad Pitt"}) OPTIONAL MATCH (p)-[:IS_SPOUSE_OF]->(s:Person) OPTIONAL MATCH (p)-[:ACTED_IN]->(m:Film) RETURN s.name, m.name

    Ví dụ 5: (Truy vấn lồng nhau)
    Câu hỏi: Chồng của "Angelina Jolie" là ai và anh ta đóng những phim nào?
    Cypher: MATCH (p:Person {name: "Angelina Jolie"})-[:IS_SPOUSE_OF]->(spouse) MATCH (spouse)-[:ACTED_IN]->(m:Film) RETURN spouse.name, m.name
    """
    
    messages = [
        {"role": "system", "content": f"""Bạn là chuyên gia Neo4j Cypher. Dựa vào Schema sau, hãy viết câu lệnh Cypher để trả lời câu hỏi.
{SCHEMA_INFO}

QUY TẮC QUAN TRỌNG:
1. CHỈ TRẢ VỀ CÂU LỆNH CYPHER, KHÔNG GIẢI THÍCH.
2. KHÔNG dùng Pattern Expression trong mệnh đề RETURN (Ví dụ SAI: RETURN a.name, (a)-->(b)).
3. Luôn dùng MATCH hoặc OPTIONAL MATCH để tìm node trước khi RETURN.
"""},
        {"role": "user", "content": f"Đây là các ví dụ:{examples}\n\nNhiệm vụ thực hiện của bạn:\nCâu hỏi: {question}\nCypher:"}
    ]
    
    print("  🧠 Đang suy luận để sinh Cypher...")
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    print(f"  💭 Raw LLM Output (Cypher Generation): {res[:100]}...")
    if prompt in res: res = res.replace(prompt, "")
    
    # Làm sạch output để chỉ lấy câu lệnh Cypher
    cypher = parse_qwen3_output(res)
    
    # Nếu có markdown code block, ưu tiên lấy nội dung bên trong
    code_block_pattern = r"```(?:cypher)?(.*?)```"
    code_blocks = re.findall(code_block_pattern, cypher, re.DOTALL)
    if code_blocks:
        cypher = code_blocks[0].strip()
    else:
        # Nếu không có block, xóa markdown và tìm MATCH
        cypher = cypher.replace("```cypher", "").replace("```", "").strip()
        match_index = cypher.upper().find("MATCH")
        if match_index != -1:
            cypher = cypher[match_index:]
            
    return cypher

# --- 3. THỰC THI & TRẢ LỜI ---
def execute_and_answer(driver, llm, tokenizer, question, cypher):
    print(f"  🚀 Đang thực thi Cypher trên Neo4j...")
    print(f"  💻 Cypher Generated: {cypher}")
    
    try:
        with driver.session() as session:
            result = session.run(cypher).data()
            
        if not result:
            print("  ⚠️ Không có kết quả từ DB.")
            return "Không tìm thấy thông tin nào khớp với câu hỏi trong cơ sở dữ liệu."
            
        # Chuyển kết quả DB thành văn bản
        context = str(result)
        print(f"  📄 DB Result: {context[:200]}...") # In gọn
        
        print("  ✍️ Đang tổng hợp câu trả lời tự nhiên...")
        # Dùng LLM để tạo câu trả lời tự nhiên
        messages = [
            {"role": "system", "content": "Bạn là trợ lý điện ảnh. Dựa vào dữ liệu thô từ Database, hãy trả lời câu hỏi của người dùng một cách tự nhiên, đầy đủ."},
            {"role": "user", "content": f"Dữ liệu: {context}\nCâu hỏi: {question}\nTrả lời:"}
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        res = llm.invoke(prompt)
        if prompt in res: res = res.replace(prompt, "")
        return parse_qwen3_output(res)
        
    except Exception as e:
        print(f"  ❌ Lỗi: {str(e)}")
        return f"Lỗi khi thực thi truy vấn: {str(e)}"

# --- MAIN ---
def main():
    llm, tokenizer, driver = init_system()
    
    print("\n💡 Mẹo: Hãy hỏi những câu phức tạp!")
    print("VD: Đạo diễn của phim mà cha Angelina Jolie đóng là ai?")
    
    while True:
        q = input("\n💬 Câu hỏi (exit): ")
        if q in ["exit", "quit"]: break
        
        # B1: Chuẩn hóa tên (Mapping tên người dùng nhập -> Tên trong DB)
        normalized_q = normalize_entities(driver, q)
        if normalized_q != q:
            print(f"  ✨ Đã chuẩn hóa câu hỏi: {normalized_q}")
        
        # B2: Sinh Cypher
        print("🤖 Đang viết câu lệnh truy vấn...")
        cypher = generate_cypher(llm, tokenizer, normalized_q)
        
        # B3: Thực thi & Trả lời
        ans = execute_and_answer(driver, llm, tokenizer, q, cypher)
        print(f"💡 KẾT QUẢ: {ans}")

    driver.close()

if __name__ == "__main__":
    main()
