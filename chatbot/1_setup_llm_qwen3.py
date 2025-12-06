import torch
import re
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_huggingface import HuggingFacePipeline
from langchain_core.prompts import PromptTemplate

# --- CẤU HÌNH MODEL ---
# Qwen3 tích hợp cả thinking và chat mode vào model gốc
MODEL_ID = "Qwen/Qwen3-0.6B"

def load_llm_components():
    print("⏳ Đang tải model Qwen3... (Lần đầu sẽ hơi lâu)")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    
    # Load model
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        device_map="auto",
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        trust_remote_code=True
    )

    # Tạo pipeline
    # Qwen3 khuyến nghị temperature 0.6 cho thinking mode
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=1024, # Tăng token vì model cần "đất" để suy nghĩ
        temperature=0.6,     
        top_p=0.95,
        repetition_penalty=1.1
    )

    llm = HuggingFacePipeline(pipeline=pipe)
    print("✅ Model Qwen3 (Thinking Mode) đã sẵn sàng!")
    return llm, tokenizer

def create_thinking_prompt(tokenizer, question):
    """
    Tạo prompt đặc biệt kích hoạt chế độ suy nghĩ của Qwen3
    """
    messages = [
        {"role": "system", "content": "Bạn là một trợ lý AI hữu ích. Hãy suy nghĩ kỹ trước khi trả lời."},
        {"role": "user", "content": question}
    ]
    
    # Cấu hình quan trọng: enable_thinking=True
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True # <--- KÍCH HOẠT CHẾ ĐỘ SUY NGHĨ
    )
    return prompt

def parse_response(full_response):
    """
    Tách phần suy nghĩ (Thinking) và phần trả lời (Answer)
    """
    # Pattern để tìm nội dung trong thẻ <think>
    think_pattern = r"<think>(.*?)</think>"
    
    match = re.search(think_pattern, full_response, re.DOTALL)
    
    if match:
        thinking_content = match.group(1).strip()
        # Phần trả lời là phần còn lại sau thẻ </think>
        answer_content = full_response.split("</think>")[-1].strip()
        return thinking_content, answer_content
    else:
        return None, full_response.strip()

# --- CHẠY THỬ NGHIỆM ---
def test_model():
    llm, tokenizer = load_llm_components()
    
    # Câu hỏi cần suy luận một chút (Multi-hop nhẹ)
    question = "Nếu Leonardo DiCaprio sinh năm 1974, thì năm 2025 anh ấy bao nhiêu tuổi và năm đó có phải năm nhuận không?"
    
    print(f"\n📝 Câu hỏi: {question}")
    print("-" * 50)

    # 1. Tạo prompt chuẩn Qwen3
    final_prompt = create_thinking_prompt(tokenizer, question)
    
    # 2. Gọi model qua LangChain
    try:
        # invoke trả về toàn bộ text (bao gồm cả prompt ban đầu ở một số pipeline)
        # LangChain thường chỉ trả về phần generated, nhưng ta cần handle kỹ
        response_text = llm.invoke(final_prompt)
        
        # Một số pipeline trả về cả prompt, ta cắt bỏ nếu cần
        if final_prompt in response_text:
            response_text = response_text.replace(final_prompt, "")

        # 3. Phân tích kết quả
        thinking, answer = parse_response(response_text)
        
        if thinking:
            print("\n🧠 QUÁ TRÌNH SUY NGHĨ (Thinking Process):")
            print(f"{thinking}")
            print("-" * 50)
        
        print("\n🤖 TRẢ LỜI CUỐI CÙNG (Final Answer):")
        print(f"{answer}")
        
    except Exception as e:
        print(f"❌ Lỗi: {e}")

if __name__ == "__main__":
    test_model()