import csv
from lxml import etree
import mwparserfromhell

# --- CẤU HÌNH ---
# Thay đổi đường dẫn này tới file XML đã giải nén của bạn
XML_FILE_PATH = '/home/lehongtrieu/Desktop/PTM/viwiki-20250720-pages-articles-multistream.xml/viwiki-20250720-pages-articles-multistream.xml'
# Tên file CSV để lưu kết quả
CSV_FILE_PATH = 'actors_data.csv'

# Các loại infobox mà chúng ta quan tâm (viết bằng chữ thường)
TARGET_INFOBOXES = ["thông tin nghệ sĩ", "thông tin diễn viên", "infobox person"]

# --- HÀM HỖ TRỢ ---
def process_element(elem):
    """Hàm này sẽ xử lý một thẻ <page> duy nhất."""
    # Namespace của MediaWiki XML
    ns = {'mw': 'http://www.mediawiki.org/xml/export-0.10/'}
    
    # Lấy tiêu đề và nội dung wikitext
    title = elem.findtext('mw:title', namespaces=ns)
    wikitext = elem.findtext('mw:revision/mw:text', namespaces=ns)
    
    # Bỏ qua các trang không có nội dung hoặc trang điều hướng
    if not wikitext or wikitext.lower().startswith('#redirect'):
        return None
    
    # --- PHẦN LOGIC CHÍNH SẼ ĐƯỢC THÊM VÀO ĐÂY (Ở CÁC BƯỚC SAU) ---
    # print(f"Đang đọc bài: {title}") # Có thể bỏ dòng này để đỡ rối console

    return None # Tạm thời trả về None

# --- CHƯƠNG TRÌNH CHÍNH ---
print("Bắt đầu quá trình xử lý...")

# Mở file CSV để ghi
with open(CSV_FILE_PATH, 'w', newline='', encoding='utf-8') as csvfile:
    # Định nghĩa các cột cho file CSV của bạn
    fieldnames = ['ten_bai_viet', 'ten_khai_sinh', 'ngay_sinh', 'noi_sinh', 'nghe_nghiep', 'phim_da_dong']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()

    # Sử dụng iterparse để đọc file XML lớn mà không tốn bộ nhớ
    context = etree.iterparse(XML_FILE_PATH, tag='{http://www.mediawiki.org/xml/export-0.10/}page')

    # Lặp qua từng thẻ <page>
    for event, elem in context:
        actor_info = process_element(elem)
        
        # Nếu hàm xử lý trả về dữ liệu của một diễn viên, ghi nó vào file CSV
        if actor_info:
            writer.writerow(actor_info)
        
        # Giải phóng bộ nhớ sau khi xử lý xong mỗi thẻ
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

print(f"Hoàn thành! Dữ liệu đã được lưu vào file {CSV_FILE_PATH}")