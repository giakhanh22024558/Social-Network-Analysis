import torch
import re
import sys
from packaging import version
import transformers
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_huggingface import HuggingFacePipeline

# --- 1. KIỂM TRA PHIÊN BẢN (Theo tài liệu Hugging Face) ---
# Qwen3 yêu cầu transformers >= 4.51.0
current_version = version.parse(transformers.__version__)
required_version = version.parse("4.51.0")
if current_version < required_version:
    raise ImportError(f"Qwen3 yêu cầu transformers>=4.51.0. Phiên bản hiện tại là {current_version}. Hãy chạy: pip install --upgrade transformers")

# --- CẤU HÌNH MODEL ---
MODEL_ID = "Qwen/Qwen3-0.6B"

def load_llm_components():
    print(f"⏳ Đang tải model {MODEL_ID}...")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    
    # Load model với device map tự động
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype="auto",
        device_map="auto"
    )

    # --- CẤU HÌNH SAMPLING THEO BEST PRACTICES ---
    # Tài liệu: "For thinking mode, use Temperature=0.6, TopP=0.95, TopK=20, and MinP=0"
    # "DO NOT use greedy decoding"
    generation_config = {
        "max_new_tokens": 32768, # Context length của Qwen3 là 32k
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0, 
        "do_sample": True, # Bắt buộc phải True để tránh greedy decoding
        "repetition_penalty": 1.1 # Giúp giảm lặp từ (tùy chỉnh nhẹ)
    }

    # Tạo pipeline
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        **generation_config
    )

    llm = HuggingFacePipeline(pipeline=pipe)
    print("✅ Model Qwen3 (Thinking Mode Configured) đã sẵn sàng!")
    return llm, tokenizer

def create_prompt_with_thinking(tokenizer, user_input, history=[]):
    """
    Sử dụng apply_chat_template chuẩn của Qwen3 để bật thinking mode.
    """
    messages = history + [{"role": "user", "content": user_input}]
    
    # Tài liệu: enable_thinking=True (Mặc định là True, nhưng set rõ ràng cho chắc chắn)
    prompt_text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True 
    )
    return prompt_text

def parse_qwen3_response(full_response):
    """
    Phân tích cú pháp dựa trên thẻ <think>...</think> chuẩn của Qwen3.
    """
    # Làm sạch chuỗi (đôi khi model trả về cả prompt ban đầu)
    # Lưu ý: Trong thực tế pipeline có thể trả về cả prompt, ta cần cắt nó đi trước khi vào hàm này
    # ở đây giả định full_response chỉ là phần generated mới.
    
    # Regex bắt nội dung trong thẻ think (flag re.DOTALL để bắt cả xuống dòng)
    think_pattern = r"<think>(.*?)</think>"
    match = re.search(think_pattern, full_response, re.DOTALL)
    
    if match:
        thinking_content = match.group(1).strip()
        # Phần trả lời là phần nằm sau thẻ </think>
        answer_content = full_response.split("</think>")[-1].strip()
        return thinking_content, answer_content
    else:
        # Trường hợp không kích hoạt được thinking hoặc lỗi format
        return None, full_response.strip()

# --- CHẠY THỬ NGHIỆM ---
def main():
    try:
        llm, tokenizer = load_llm_components()
        
        # Câu hỏi test logic (để kích hoạt tư duy)
        question = "Nếu tôi có 3 quả táo, tôi ăn 1 quả, sau đó mua thêm 2 quả nữa. Hỏi tôi còn bao nhiêu quả?"
        question = "Ai là đạo diễn của phim Inception và ông ấy đã thắng bao nhiêu giải Oscar?"
        question = "Đạo diễn của phim Titanic đã sản xuất những phim nào khác?"
        question = "Nếu Leonardo DiCaprio sinh năm 1974, thì năm 2025 anh ấy bao nhiêu tuổi và năm đó có phải năm nhuận không?"
        
        print(f"\n📝 Câu hỏi: {question}")
        print("-" * 50)

        # 1. Tạo Prompt chuẩn
        prompt = create_prompt_with_thinking(tokenizer, question)
        
        # 2. Gọi Model (LangChain invoke)
        # Lưu ý: Pipeline 'text-generation' mặc định trả về cả prompt + response.
        # LangChain HuggingFacePipeline thường xử lý việc này, nhưng ta cần cẩn thận.
        response = llm.invoke(prompt)
        
        # Cắt bỏ phần prompt nếu nó bị lặp lại trong kết quả (đặc thù của một số pipeline)
        if response.startswith(prompt):
            response = response[len(prompt):]

        # 3. Phân tích kết quả
        thinking, answer = parse_qwen3_response(response)
        
        if thinking:
            print("\n🧠 QUÁ TRÌNH TƯ DUY (Thinking Mode):")
            print(thinking)
            print("-" * 50)
        else:
            print("\n⚠️ Không tìm thấy thẻ <think>. Kiểm tra lại config.")

        print("\n🤖 CÂU TRẢ LỜI (Final Answer):")
        print(answer)

    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()