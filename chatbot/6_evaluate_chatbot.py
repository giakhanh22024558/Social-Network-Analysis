import pandas as pd
import sys
import os
import re
from tqdm import tqdm # Thư viện thanh tiến trình (pip install tqdm)
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
MODEL_ID = "Qwen/Qwen3-0.6B"
INPUT_CSV = "evaluation_dataset_2000.csv"
OUTPUT_CSV = "evaluation_results.csv"
BATCH_SIZE = 4 # Tăng lên 64 hoặc 128 nếu GPU mạnh
SAMPLE_SIZE = 50 # <--- ĐÃ THÊM LẠI: Số lượng câu hỏi chạy thử (Để None nếu muốn chạy hết)

# ==============================================================================
# PHẦN 1: CORE FUNCTIONS (GIỮ NGUYÊN)
# ==============================================================================

def init_components():
    print("⏳ Đang khởi tạo Model & Tokenizer...")
    # Fix: Set padding_side='left' for decoder-only models in batch generation
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, padding_side='left')
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    
    # Fix: Use dtype instead of torch_dtype
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype="auto", device_map="auto"
    )
    
    pipe = pipeline(
        "text-generation", model=model, tokenizer=tokenizer,
        max_new_tokens=256, temperature=0.1, top_p=0.9, do_sample=True, repetition_penalty=1.1,
        batch_size=BATCH_SIZE, pad_token_id=tokenizer.pad_token_id
    )
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return pipe, tokenizer, driver

def parse_qwen3_output(text, prompt_len):
    generated = text[prompt_len:]
    if "<think>" in generated: 
        generated = generated.split("</think>")[-1]
    return generated.strip()

def prepare_extraction_prompts(questions, tokenizer):
    prompts = []
    base_msgs = [{"role": "system", "content": "Trích xuất các TÊN RIÊNG (Người, Phim) có trong câu hỏi. Ngăn cách bằng dấu phẩy. Không thêm từ thừa."}]
    print("🛠️ Đang chuẩn bị Prompt trích xuất...")
    for q in questions:
        msgs = base_msgs + [{"role": "user", "content": f"Câu hỏi: {q}\nThực thể:"}]
        txt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        prompts.append(txt)
    return prompts

def prepare_answer_prompts(questions, contexts, tokenizer):
    prompts = []
    base_msgs = [{"role": "system", "content": "Dựa vào thông tin được cung cấp, hãy trả lời câu hỏi. Với câu hỏi Yes/No, hãy bắt đầu bằng 'Có' hoặc 'Không'. Với trắc nghiệm, hãy chọn đáp án đúng."}]
    print("🛠️ Đang chuẩn bị Prompt trả lời...")
    for q, ctx in zip(questions, contexts):
        content = f"THÔNG TIN:\n{ctx}\n\nCÂU HỎI: {q}\nTRẢ LỜI:" if ctx else f"CÂU HỎI: {q}\n(Không có thông tin tra cứu)\nTRẢ LỜI:"
        msgs = base_msgs + [{"role": "user", "content": content}]
        txt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=True)
        prompts.append(txt)
    return prompts

# ==============================================================================
# PHẦN 2: GRAPH LOOKUP (GIỮ NGUYÊN)
# ==============================================================================

def batch_get_contexts(driver, all_entities_list):
    print("🔍 Đang truy xuất Neo4j (Batch Lookup)...")
    contexts = []
    with driver.session() as session:
        for entities in tqdm(all_entities_list):
            if not entities:
                contexts.append(None); continue
            
            nodes = []
            for name in entities:
                res = session.run("CALL db.index.fulltext.queryNodes('names', $name + '~') YIELD node, score RETURN node.name, node.qid LIMIT 1", name=name).single()
                if res: nodes.append(res)
            
            if not nodes:
                contexts.append(None); continue

            ctx_text = ""
            if len(nodes) >= 2:
                s, e = nodes[0], nodes[-1]
                res = session.run("MATCH (a {qid: $s}), (b {qid: $e}) MATCH p=shortestPath((a)-[*..4]-(b)) RETURN p", s=s['node.qid'], e=e['node.qid']).single()
                if res:
                    p = res['p']
                    parts = [f"{p.nodes[i]['name']} --[{p.relationships[i].type}]--> {p.nodes[i+1]['name']}" for i in range(len(p.relationships))]
                    ctx_text = " -> ".join(parts)
                else: ctx_text = "Không tìm thấy đường đi kết nối."
            else:
                main = nodes[0]
                res = session.run("MATCH (n {qid: $id})-[r]-(m) RETURN type(r) as t, m.name as n LIMIT 15", id=main['node.qid']).data()
                lines = [f"- {r['t']} {r['n']}" for r in res]
                ctx_text = f"Thông tin về {main['node.name']}:\n" + "\n".join(lines)
            contexts.append(ctx_text)
    return contexts

# ==============================================================================
# PHẦN 3: MAIN PIPELINE (ĐÃ CẬP NHẬT SAMPLE_SIZE)
# ==============================================================================

def run_optimized_evaluation():
    # 1. Load Data
    try:
        df = pd.read_csv(INPUT_CSV)
        print(f"📊 Đã tìm thấy {len(df)} câu hỏi trong file gốc.")
    except FileNotFoundError:
        print("❌ Lỗi: Không tìm thấy file CSV dữ liệu.")
        return

    # --- LOGIC SAMPLE MỚI ---
    if SAMPLE_SIZE and isinstance(SAMPLE_SIZE, int) and SAMPLE_SIZE < len(df):
        print(f"⚠️ CHẾ ĐỘ TEST: Lấy mẫu ngẫu nhiên {SAMPLE_SIZE} câu để chạy thử.")
        df = df.sample(SAMPLE_SIZE, random_state=42).reset_index(drop=True)
    else:
        print("🚀 CHẾ ĐỘ FULL: Chạy toàn bộ dữ liệu.")
    # ------------------------

    pipe, tokenizer, driver = init_components()
    questions = df['question'].tolist()

    # PHA 1: EXTRACT
    extract_prompts = prepare_extraction_prompts(questions, tokenizer)
    print(f"🚀 Bắt đầu trích xuất thực thể (Batch Size={BATCH_SIZE})...")
    extract_outputs = []
    for out in tqdm(pipe(extract_prompts, batch_size=BATCH_SIZE), total=len(questions)):
        extract_outputs.append(out[0]['generated_text'])

    all_extracted_entities = []
    for q, raw_out, prompt in zip(questions, extract_outputs, extract_prompts):
        generated = raw_out[len(prompt):]
        cleaned = generated.split('\n')[0].replace("Thực thể:", "").strip()
        candidates = [e.strip() for e in cleaned.split(',') if e.strip()]
        valid = [e for e in candidates if e.lower() in q.lower()] # Filter ảo giác
        if not valid and candidates: valid = candidates
        all_extracted_entities.append(valid)

    # PHA 2: NEO4J
    contexts = batch_get_contexts(driver, all_extracted_entities)

    # PHA 3: ANSWER
    answer_prompts = prepare_answer_prompts(questions, contexts, tokenizer)
    pipe.model.config.max_new_tokens = 512 
    print(f"🚀 Bắt đầu sinh câu trả lời (Batch Size={BATCH_SIZE})...")
    final_outputs = []
    for out in tqdm(pipe(answer_prompts, batch_size=BATCH_SIZE), total=len(questions)):
        final_outputs.append(out[0]['generated_text'])

    # PHA 4: SCORING
    results = []
    correct_count = 0
    print("📝 Đang chấm điểm...")
    
    for i in range(len(df)):
        prompt = answer_prompts[i]
        raw_out = final_outputs[i]
        bot_ans = parse_qwen3_output(raw_out, len(prompt))
        
        ground_truth = str(df.iloc[i]['answer'])
        q_type = df.iloc[i]['type']
        
        score = 0
        ans_lower = bot_ans.lower()
        truth_lower = ground_truth.lower()
        
        if "yesno" in q_type.lower():
            is_pos = any(x in truth_lower for x in ["yes", "có", "đúng"])
            bot_yes = any(x in ans_lower for x in ["yes", "có", "đúng"])
            bot_no = any(x in ans_lower for x in ["no", "không", "sai"])
            if is_pos and bot_yes: score = 1
            elif (not is_pos) and bot_no: score = 1
        else:
            if truth_lower in ans_lower: score = 1
            
        correct_count += score
        results.append({
            "question": questions[i],
            "type": q_type,
            "ground_truth": ground_truth,
            "extracted_entities": str(all_extracted_entities[i]),
            "context_found": bool(contexts[i]),
            "bot_answer": bot_ans,
            "score": score
        })

    driver.close()
    
    final_df = pd.DataFrame(results)
    accuracy = (correct_count / len(final_df)) * 100
    
    print("\n" + "="*40)
    print(f"🏁 KẾT QUẢ ĐÁNH GIÁ ({len(final_df)} câu)")
    print(f"✅ Độ chính xác (Accuracy): {accuracy:.2f}%")
    print("="*40)
    print("\n📊 Chi tiết theo loại:")
    print(final_df.groupby('type')['score'].mean() * 100)
    
    final_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"\n💾 Đã lưu: {OUTPUT_CSV}")

if __name__ == "__main__":
    run_optimized_evaluation()