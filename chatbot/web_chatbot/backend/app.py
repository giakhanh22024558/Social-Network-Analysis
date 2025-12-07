"""
Backend API cho Iterative Graph RAG Chatbot
Sử dụng FastAPI + WebSocket để streaming logs
"""

import sys
import asyncio
from itertools import combinations
from typing import Generator
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rapidfuzz import process, fuzz
from neo4j import GraphDatabase
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_huggingface import HuggingFacePipeline

# --- CẤU HÌNH ---
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"
MODEL_ID = "Qwen/Qwen3-0.6B"
MAX_ITERATIONS = 5

# Global variables
llm = None
tokenizer = None
driver = None
all_names = []


class LogCallback:
    """Callback để thu thập logs và gửi qua WebSocket"""
    def __init__(self):
        self.logs = []
        self.websocket = None
        self.loop = None
        self.queue = None
    
    async def log(self, message: str, log_type: str = "info"):
        """Thêm log và gửi qua websocket nếu có"""
        log_entry = {"type": log_type, "message": message}
        self.logs.append(log_entry)
        if self.websocket:
            try:
                await self.websocket.send_json({"event": "log", "data": log_entry})
            except:
                pass
    
    def log_sync(self, message: str, log_type: str = "info"):
        """Version đồng bộ cho các hàm không async - đẩy vào queue để gửi real-time"""
        log_entry = {"type": log_type, "message": message}
        self.logs.append(log_entry)
        
        # Đẩy log vào queue để gửi qua WebSocket
        if self.queue is not None and self.loop is not None:
            try:
                self.loop.call_soon_threadsafe(self.queue.put_nowait, log_entry)
            except:
                pass
        
        return log_entry
    
    def clear(self):
        self.logs = []


# --- KHỞI TẠO HỆ THỐNG ---
def init_system():
    global llm, tokenizer, driver, all_names
    
    print("⏳ Đang khởi tạo hệ thống Iterative RAG...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto", device_map="auto")
    
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=32768, temperature=0.6, top_p=0.95, top_k=20, 
        min_p=0, repetition_penalty=1.1,
    )
    llm = HuggingFacePipeline(pipeline=pipe)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Load entity names
    print("⏳ Đang tải danh sách thực thể từ Neo4j...")
    try:
        with driver.session() as session:
            result = session.run("MATCH (n) WHERE n.name IS NOT NULL RETURN DISTINCT n.name as name")
            all_names = [r["name"] for r in result]
        print(f"✅ Đã tải {len(all_names)} tên thực thể.")
    except Exception as e:
        print(f"⚠️ Không thể tải danh sách thực thể: {e}")
    
    print("✅ Hệ thống đã sẵn sàng!")


def parse_qwen3_output(text):
    if "<think>" in text:
        text = text.split("</think>")[-1]
    return text.strip()


def clean_entities(raw_text, source_text):
    candidates = [e.strip() for e in raw_text.split(',') if e.strip()]
    candidates = [e.replace(".", "").replace('"', '').replace("'", "") for e in candidates]
    valid = [c for c in candidates if len(c) > 2]
    return valid


def extract_initial_entities(question, logger: LogCallback):
    """Vòng 1: Trích xuất từ câu hỏi gốc"""
    examples = """
    Hỏi: Ai là đạo diễn phim Titanic? -> Thực thể: Titanic
    Hỏi: Jon Voight là ai và có quan hệ gì với Angelina Jolie? -> Thực thể: Jon Voight, Angelina Jolie
    Hỏi: Brad Pitt và Leonardo DiCaprio có đóng chung phim Titanic không? -> Thực thể: Brad Pitt, Leonardo DiCaprio, Titanic
    """
    messages = [
        {"role": "system", "content": "Trích xuất các TÊN RIÊNG (Người, Phim) từ câu hỏi. Ngăn cách bởi dấu phẩy. Không thêm từ thừa."},
        {"role": "user", "content": f"Đây là các ví dụ{examples}\n. Đây là câu hỏi cần trích xuất: {question}\nThực thể:"}
    ]
    
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res:
        res = res.replace(prompt, "")
    
    raw = parse_qwen3_output(res).split('\n')[0].replace("Thực thể:", "").strip()
    logger.log_sync(f"[EXTRACT] Raw entities: {raw}", "debug")
    return clean_entities(raw, question)


def extract_more_entities(question, current_context, logger: LogCallback):
    """Vòng >1: Trích xuất thêm thực thể từ ngữ cảnh"""
    system_msg = """Bạn là trợ lý suy luận. 
    Dựa vào CÂU HỎI và THÔNG TIN ĐÃ BIẾT, hãy xác định xem cần tìm kiếm thêm thông tin về NHÂN VẬT hoặc BỘ PHIM nào nữa.
    Chỉ liệt kê tên riêng mới. Nếu không cần thêm ai, trả về 'NONE'."""
    
    user_msg = f"""CÂU HỎI: {question}
    THÔNG TIN ĐÃ BIẾT:
    {current_context}
    
    Cần tìm thêm thông tin về ai (Tên riêng)?"""
    
    messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res:
        res = res.replace(prompt, "")
    
    raw = parse_qwen3_output(res)
    logger.log_sync(f"[EXTRACT MORE] Raw: {raw}", "debug")
    
    if "NONE" in raw or "không cần" in raw.lower():
        return []
    
    return clean_entities(raw, raw)


def normalize_entities(entities, logger: LogCallback, threshold=85):
    """Chuẩn hóa tên thực thể bằng cách so khớp với DB"""
    if not all_names:
        return entities
    
    normalized = []
    if entities:
        logger.log_sync(f"[NORM] Input: {entities}", "info")
    
    for entity in entities:
        match = process.extractOne(entity, all_names, scorer=fuzz.WRatio)
        if match:
            best_name, score, _ = match
            if score >= threshold:
                logger.log_sync(f"[NORM] '{entity}' → '{best_name}' (Score: {score:.1f})", "success")
                normalized.append(best_name)
            else:
                logger.log_sync(f"[NORM] '{entity}' → Loại bỏ (Score: {score:.1f} < {threshold})", "warning")
        else:
            normalized.append(entity)
    
    return list(set(normalized))


def check_sufficiency(question, context, logger: LogCallback):
    """Hỏi model xem thông tin đã đủ chưa"""
    if not context:
        return False, "Chưa có thông tin."
    
    messages = [
        {"role": "system", "content": "Bạn là giám khảo khắt khe. Đánh giá xem thông tin đã ĐỦ để trả lời câu hỏi chưa. Chỉ trả lời 'ĐỦ' hoặc 'CHƯA ĐỦ'."},
        {"role": "user", "content": f"CÂU HỎI: {question}\nTHÔNG TIN:\n{context}\n\nĐánh giá:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res:
        res = res.replace(prompt, "")
    
    answer = parse_qwen3_output(res).lower()
    logger.log_sync(f"[EVAL] Sufficiency check: {answer}", "debug")
    is_sufficient = "đủ" in answer and "chưa" not in answer
    return is_sufficient, answer


# --- TRUY XUẤT ĐỒ THỊ ---
def find_node_qid(session, name):
    result = session.run(
        "CALL db.index.fulltext.queryNodes('names', $name + '~') YIELD node, score "
        "RETURN node.name, node.qid, labels(node) ORDER BY score DESC LIMIT 1",
        name=name
    ).single()
    if result:
        return {"name": result[0], "qid": result[1], "labels": result[2]}
    return None


def get_node_details_text(session, qid, name):
    node = session.run("MATCH (n {qid: $qid}) RETURN n.gender, n.birthDate", qid=qid).single()
    if not node:
        return ""
    info = [f"**{name}:**"]
    if node[0]:
        info.append(f"Giới tính: {node[0]}")
    if node[1]:
        info.append(f"Sinh: {str(node[1]).split('T')[0]}")
    return " - ".join(info)


def get_relationship_action(rel_type, is_forward):
    mapping = {
        "ACTED_IN": ("đóng trong phim", "có diễn viên là"),
        "DIRECTED": ("là đạo diễn của", "được đạo diễn bởi"),
        "PRODUCED": ("sản xuất phim", "được sản xuất bởi"),
        "IS_CHILD_OF": ("là con của", "là cha/mẹ của"),
        "IS_CHILD_OF_DAD": ("là con của cha", "là cha của"),
        "IS_CHILD_OF_MOM": ("là con của mẹ", "là mẹ của"),
        "IS_PARENT_OF": ("là cha/mẹ của", "là con của"),
        "IS_SPOUSE_OF": ("là vợ/chồng của", "là vợ/chồng của"),
        "IS_PARTNER_OF": ("là bạn đời của", "là bạn đời của"),
        "IS_SIBLING_OF": ("là anh/chị em với", "là anh/chị em với"),
        "HAS_GRANDPARENT_OF": ("là cháu của", "là ông/bà của"),
    }
    if rel_type in mapping:
        return mapping[rel_type][0 if is_forward else 1]
    return f"có quan hệ {rel_type} với"


def format_path_text(path):
    nodes = path.nodes
    rels = path.relationships
    parts = []
    
    for i, rel in enumerate(rels):
        start = nodes[i]
        end = nodes[i + 1]
        is_forward = (rel.start_node.element_id == start.element_id)
        action = get_relationship_action(rel.type, is_forward)
        parts.append(f"{start['name']} {action} {end['name']}")
    
    return " → ".join(parts) + "."


def get_full_graph_context(entity_names, logger: LogCallback):
    """Truy xuất context đầy đủ từ đồ thị"""
    with driver.session() as session:
        nodes = []
        for name in entity_names:
            n = find_node_qid(session, name)
            if n:
                nodes.append(n)
                logger.log_sync(f"[GRAPH] Tìm thấy node: {n['name']} (QID: {n['qid']})", "success")
            else:
                logger.log_sync(f"[GRAPH] Không tìm thấy node: {name}", "warning")
        
        if not nodes:
            logger.log_sync("[GRAPH] Không tìm thấy node nào trong DB!", "error")
            return "Không tìm thấy node nào."
        
        context_parts = []
        
        # 1. Thông tin chi tiết
        context_parts.append("--- THÔNG TIN CÁ NHÂN ---")
        logger.log_sync("\n📋 THÔNG TIN CÁ NHÂN:", "step")
        for n in nodes:
            details = get_node_details_text(session, n['qid'], n['name'])
            if details:
                context_parts.append(details)
                logger.log_sync(f"  {details}", "info")
        
        # 2. Quan hệ
        context_parts.append("\n--- MỐI QUAN HỆ ---")
        logger.log_sync("\n🔗 MỐI QUAN HỆ:", "step")
        
        for n in nodes:
            res = session.run("MATCH (n {qid: $id})-[r]-(m) RETURN r, n, m LIMIT 50", id=n['qid'])
            
            has_rel = False
            rel_count = 0
            for record in res:
                r = record['r']
                n_node = record['n']
                m_node = record['m']
                
                is_forward = (r.start_node.element_id == n_node.element_id)
                action = get_relationship_action(r.type, is_forward)
                rel_text = f"{n_node['name']} {action} {m_node['name']}"
                context_parts.append(rel_text)
                
                # Log từng quan hệ (giới hạn để không quá dài)
                rel_count += 1
                if rel_count <= 10:
                    logger.log_sync(f"  • {rel_text}", "info")
                has_rel = True
            
            if rel_count > 10:
                logger.log_sync(f"  ... và {rel_count - 10} quan hệ khác", "info")
            
            if not has_rel:
                no_rel_text = f"{n['name']} không có quan hệ nào trong DB."
                context_parts.append(no_rel_text)
                logger.log_sync(f"  ⚠️ {no_rel_text}", "warning")
        
        # 3. Tìm đường giữa các cặp
        if len(nodes) >= 2:
            context_parts.append("\n--- LIÊN KẾT GIỮA CÁC THỰC THỂ ---")
            pairs = list(combinations(nodes, 2))
            logger.log_sync(f"\n🔀 LIÊN KẾT GIỮA CÁC THỰC THỂ ({len(pairs)} cặp):", "step")
            
            for start, end in pairs:
                query = """
                    MATCH (p1 {qid: $s}), (p2 {qid: $e})
                    MATCH path = shortestPath((p1)-[*..6]-(p2))
                    RETURN path
                """
                result = session.run(query, s=start['qid'], e=end['qid']).single()
                
                if result:
                    path_text = format_path_text(result['path'])
                    full_path = f"- Quan hệ giữa {start['name']} và {end['name']}: {path_text}"
                    context_parts.append(full_path)
                    logger.log_sync(f"  ✓ {start['name']} ↔ {end['name']}: {path_text}", "success")
                else:
                    no_path = f"- Không tìm thấy liên kết giữa {start['name']} và {end['name']}."
                    context_parts.append(no_path)
                    logger.log_sync(f"  ✗ Không có liên kết: {start['name']} ↔ {end['name']}", "warning")
        
        full_context = "\n".join(context_parts)
        logger.log_sync(f"\n📊 Tổng context: {len(full_context)} ký tự", "info")
        return full_context


def generate_final_answer(question, context, logger: LogCallback):
    """Tạo câu trả lời cuối cùng"""
    messages = [
        {"role": "system", "content": "Bạn là trợ lý thông minh. Hãy trả lời câu hỏi dựa trên thông tin đã thu thập được."},
        {"role": "user", "content": f"DỮ LIỆU:\n{context}\n\nCÂU HỎI: {question}\nTRẢ LỜI:"}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True)
    res = llm.invoke(prompt)
    if prompt in res:
        res = res.replace(prompt, "")
    
    final_res = parse_qwen3_output(res)
    logger.log_sync(f"[ANSWER] Generated answer", "success")
    return final_res


def process_question(question: str, logger: LogCallback) -> str:
    """Xử lý câu hỏi với vòng lặp iterative"""
    accumulated_entities = set()
    current_context = ""
    
    logger.log_sync("🚀 BẮT ĐẦU VÒNG LẶP SUY LUẬN...", "info")
    
    for i in range(MAX_ITERATIONS):
        logger.log_sync(f"\n━━━ VÒNG {i + 1}/{MAX_ITERATIONS} ━━━", "step")
        
        # BƯỚC 1: TRÍCH XUẤT
        new_entities = []
        if i == 0:
            logger.log_sync("📝 Trích xuất thực thể từ câu hỏi...", "info")
            new_entities = extract_initial_entities(question, logger)
        else:
            logger.log_sync("🤔 Suy luận tìm thêm thực thể...", "info")
            new_entities = extract_more_entities(question, current_context, logger)
        
        # BƯỚC 2: CHUẨN HÓA
        logger.log_sync("🔄 Chuẩn hóa thực thể...", "info")
        new_entities = normalize_entities(new_entities, logger)
        
        # Cập nhật danh sách
        prev_len = len(accumulated_entities)
        for e in new_entities:
            accumulated_entities.add(e)
        
        logger.log_sync(f"🔍 Thực thể hiện có: {list(accumulated_entities)}", "info")
        
        if len(accumulated_entities) == prev_len and i > 0:
            logger.log_sync("🛑 Không tìm thấy thực thể mới. Dừng lặp.", "warning")
            break
        
        if not accumulated_entities:
            logger.log_sync("❌ Không tìm thấy thực thể nào!", "error")
            return "Xin lỗi, tôi không thể trích xuất được thực thể từ câu hỏi của bạn."
        
        # BƯỚC 3: TRUY XUẤT GRAPH
        logger.log_sync("🔗 Đang truy xuất đồ thị...", "info")
        current_context = get_full_graph_context(list(accumulated_entities), logger)
        
        # BƯỚC 4: KIỂM TRA ĐỘ ĐẦY ĐỦ
        logger.log_sync("⚖️ Đánh giá độ đầy đủ thông tin...", "info")
        is_enough, reason = check_sufficiency(question, current_context, logger)
        
        if is_enough:
            logger.log_sync(f"✅ Thông tin ĐỦ! ({reason})", "success")
            break
        else:
            logger.log_sync(f"⚠️ Thông tin CHƯA ĐỦ. Tiếp tục vòng sau...", "warning")
    
    # BƯỚC 5: TẠO CÂU TRẢ LỜI
    logger.log_sync("\n🏁 TỔNG HỢP CÂU TRẢ LỜI...", "step")
    final_answer = generate_final_answer(question, current_context, logger)
    logger.log_sync("✨ Hoàn thành!", "success")
    
    return final_answer


# --- FASTAPI APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_system()
    yield
    # Shutdown
    if driver:
        driver.close()


app = FastAPI(title="Iterative Graph RAG Chatbot", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    logs: list


@app.get("/")
async def root():
    return {"status": "ok", "message": "Iterative Graph RAG Chatbot API"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_loaded": llm is not None,
        "neo4j_connected": driver is not None,
        "entities_count": len(all_names)
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: QuestionRequest):
    """API endpoint cho chat (không streaming)"""
    logger = LogCallback()
    answer = process_question(request.question, logger)
    return ChatResponse(answer=answer, logs=logger.logs)


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint cho chat với streaming logs"""
    await websocket.accept()
    logger = LogCallback()
    logger.websocket = websocket
    
    try:
        while True:
            # Nhận câu hỏi
            data = await websocket.receive_json()
            question = data.get("question", "")
            
            if not question:
                await websocket.send_json({"event": "error", "data": "Câu hỏi trống"})
                continue
            
            logger.clear()
            
            # Setup queue cho real-time logging
            logger.queue = asyncio.Queue()
            logger.loop = asyncio.get_event_loop()
            
            # Gửi trạng thái bắt đầu
            await websocket.send_json({"event": "start", "data": {"question": question}})
            
            # Task để gửi logs từ queue
            async def send_logs():
                while True:
                    try:
                        log_entry = await asyncio.wait_for(logger.queue.get(), timeout=0.1)
                        await websocket.send_json({"event": "log", "data": log_entry})
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
            
            # Chạy song song: xử lý câu hỏi + gửi logs
            log_task = asyncio.create_task(send_logs())
            
            try:
                # Xử lý câu hỏi (chạy trong thread pool để không block)
                loop = asyncio.get_event_loop()
                answer = await loop.run_in_executor(None, process_question, question, logger)
            finally:
                # Đợi một chút để gửi hết logs còn lại
                await asyncio.sleep(0.2)
                log_task.cancel()
                try:
                    await log_task
                except asyncio.CancelledError:
                    pass
            
            # Gửi kết quả
            await websocket.send_json({
                "event": "complete",
                "data": {
                    "answer": answer,
                    "logs": logger.logs
                }
            })
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"event": "error", "data": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
