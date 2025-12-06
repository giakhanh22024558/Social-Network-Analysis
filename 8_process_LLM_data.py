import json

# Bảng ánh xạ các mối quan hệ tiếng Việt sang tiếng Anh
RELATIONSHIP_MAPPING = {
    # Quan hệ học tập
    "Học tại": "EDUCATED_AT",
    "học tại": "EDUCATED_AT",
    "theo học tại": "EDUCATED_AT",
    "từng học tại": "EDUCATED_AT",
    "attended": "EDUCATED_AT",
    "studied at": "EDUCATED_AT",
    "studied_at": "EDUCATED_AT",
    "trained at": "EDUCATED_AT",
    "trained_at": "EDUCATED_AT",
    "graduated from": "EDUCATED_AT",
    "graduated_from": "EDUCATED_AT",
    "tốt nghiệp": "EDUCATED_AT",
    
    # Quan hệ sinh, nơi sinh
    "sinh ra tại": "BORN_IN",
    "sinh ra ở": "BORN_IN",
    "sinh tại": "BORN_IN",
    "born in": "BORN_IN",
    "born_in": "BORN_IN",
    "sinh ngày": "BORN_IN",
    
    # Quan hệ sống, cư trú
    "lớn lên tại": "LIVED_IN",
    "lớn lên ở": "LIVED_IN",
    "chuyển đến": "LIVED_IN",
    
    # Quan hệ cha mẹ con
    "là con gái của": "CHILD_OF",
    "là con trai của": "CHILD_OF",
    "con của": "CHILD_OF",
    "con gái là": "PARENT_OF",
    "con trai của": "CHILD_OF",
    "Là con gái của": "CHILD_OF",
    "daughter of": "CHILD_OF",
    "son of": "CHILD_OF",
    "is_son_of": "CHILD_OF",
    "child of": "CHILD_OF",
    
    "là cha của": "PARENT_OF",
    "là mẹ của": "PARENT_OF",
    "cha là": "PARENT_OF",
    "mẹ là": "PARENT_OF",
    "father_of": "PARENT_OF",
    "is mother of": "PARENT_OF",
    "có con gái với": "PARENT_OF",
    "has_daughter": "PARENT_OF",
    
    # Quan hệ anh chị em
    "là em trai của": "SIBLING_OF",
    "là cháu cố của": "SIBLING_OF",
    
    # Quan hệ hôn nhân
    "kết hôn với": "SPOUSE",
    "vợ": "SPOUSE",
    "ly dị": "SPOUSE",
    "married": "SPOUSE",
    "married_to": "SPOUSE",
    "hẹn hò với": "PARTNER",
    "partner of": "PARTNER",
    
    # Quan hệ hợp tác
    "Hợp tác với": "COLLABORATED_WITH",
    "hợp tác với": "COLLABORATED_WITH",
    "collaborated with": "COLLABORATED_WITH",
    "collaborated_with": "COLLABORATED_WITH",
    "collaborated with director": "COLLABORATED_WITH",
    "cùng với": "COLLABORATED_WITH",
    "hợp tác sáng tác với": "COLLABORATED_WITH",
    "hợp tác viết với": "COLLABORATED_WITH",
    "hợp tác với đạo diễn": "COLLABORATED_WITH",
    "co-starred with": "COLLABORATED_WITH",
    "co-wrote screenplay for": "COLLABORATED_WITH",
    "acted with": "COLLABORATED_WITH",
    "worked_with": "COLLABORATED_WITH",
    "đóng cùng": "COLLABORATED_WITH",
    "đóng cặp với": "COLLABORATED_WITH",
    "đồng biên kịch với": "COLLABORATED_WITH",
    
    # Quan hệ ký hợp đồng
    "Ký hợp đồng với": "SIGNED_WITH",
    "ký hợp đồng với": "SIGNED_WITH",
    "kí hợp đồng ca sĩ với": "SIGNED_WITH",
    "kí hợp đồng người mẫu với công ty của": "SIGNED_WITH",
    "signed_with": "SIGNED_WITH",
    
    # Quan hệ thành viên
    "là thành viên của": "MEMBER_OF",
    "từng là thành viên của": "MEMBER_OF",
    "member of": "MEMBER_OF",
    "member_of": "MEMBER_OF",
    "is_member_of": "MEMBER_OF",
    "was_member_of": "MEMBER_OF",
    "included_member": "MEMBER_OF",
    "is_lead_singer_of": "MEMBER_OF",
    "is_leader_of": "MEMBER_OF",
    
    # Quan hệ sáng lập
    "sáng lập": "FOUNDED",
    "thành lập": "FOUNDED",
    "đồng sáng lập": "FOUNDED",
    "founded": "FOUNDED",
    
    # Quan hệ đạo diễn
    "đạo diễn": "DIRECTED",
    "đạo diễn cho": "DIRECTED",
    "directed": "DIRECTED",
    "directed film": "DIRECTED",
    "directed_by": "DIRECTED",
    "directed_and_starred_in": "DIRECTED",
    "directed_co_produced_and_wrote": "DIRECTED",
    "co_created_directed_and_starred_in": "DIRECTED",
    "đóng phim đạo diễn bởi": "DIRECTED",
    "đạo diễn bởi": "DIRECTED",
    "started career with director": "DIRECTED",
    "tái hợp với đạo diễn": "DIRECTED",
    
    # Quan hệ sản xuất
    "sản xuất": "PRODUCED",
    "produced": "PRODUCED",
    
    # Quan hệ giải thưởng
    "giành": "WON_AWARD",
    "giành giải": "WON_AWARD",
    "giành được": "WON_AWARD",
    "thắng giải": "WON_AWARD",
    "nhận": "WON_AWARD",
    "nhận giải": "WON_AWARD",
    "nhận được": "WON_AWARD",
    "đoạt": "WON_AWARD",
    "đoạt giải": "WON_AWARD",
    "Đoạt": "WON_AWARD",
    "đoạt danh hiệu": "WON_AWARD",
    "won": "WON_AWARD",
    "won_event": "WON_AWARD",
    "received": "WON_AWARD",
    "received award": "WON_AWARD",
    "received_award": "WON_AWARD",
    "received_award_at": "WON_AWARD",
    "được thưởng": "WON_AWARD",
    "được trao": "WON_AWARD",
    "đoạt giải từ": "WON_AWARD",
    "đoạt giải Oscar cho": "WON_AWARD_FOR",
    "cho vai diễn trong": "WON_AWARD_FOR",
    "lập kỷ lục": "WON_AWARD",
    
    # Quan hệ đề cử
    "được đề cử": "NOMINATED_FOR",
    "đề cử": "NOMINATED_FOR",
    "nominated for": "NOMINATED_FOR",
    "nominated_for": "NOMINATED_FOR",
    "received nomination": "NOMINATED_FOR",
    
    # Quan hệ vinh danh
    "được vinh danh bởi": "RECOGNIZED_BY",
    "được vinh danh": "RECOGNIZED_BY",
    "Được vinh danh tại": "RECOGNIZED_BY",
    "được phong tặng": "RECOGNIZED_BY",
    "recognized by": "RECOGNIZED_BY",
    "recognized_by": "RECOGNIZED_BY",
    "inducted_into": "RECOGNIZED_BY",
    
    # Quan hệ diễn xuất
    "đóng vai": "ACTED_IN",
    "đóng vai chính trong": "STARRED_IN",
    "đóng vai chính trong phim": "STARRED_IN",
    "đóng chính trong": "STARRED_IN",
    "đóng trong": "ACTED_IN",
    "thủ vai": "ACTED_IN",
    "xuất hiện trong": "APPEARED_IN",
    "starred": "STARRED_IN",
    "starred_in": "STARRED_IN",
    "appeared_in_film": "APPEARED_IN",
    "played_role_in": "ACTED_IN",
    "portrayed": "ACTED_IN",
    "known_for_role": "ACTED_IN",
    "đóng kịch tại": "PERFORMED_AT",
    
    # Quan hệ xuất hiện
    "Xuất hiện trên": "APPEARED_ON",
    "xuất hiện trên": "APPEARED_ON",
    "appeared_on": "APPEARED_ON",
    "biểu diễn trên": "PERFORMED_ON",
    "performs_on": "PERFORMED_ON",
    "performed_at": "PERFORMED_AT",
    "có ngôi sao trên": "APPEARED_ON",
    
    # Quan hệ phát sóng
    "phát sóng trên": "AIRED_ON",
    "aired_on": "AIRED_ON",
    "streamed_on": "STREAMED_ON",
    
    # Quan hệ làm việc
    "là phát ngôn viên của": "WORKED_FOR",
    "là gương mặt đại diện của": "WORKED_FOR",
    "là đại sứ thương hiệu của": "WORKED_FOR",
    "là Sứ giả Hòa bình của": "WORKED_FOR",
    "là phóng viên trên": "WORKED_FOR",
    "điều hành công ty": "WORKED_FOR",
    "is_chairman_of": "WORKED_FOR",
    "Chủ tịch của": "WORKED_FOR",
    "was_executive_at": "WORKED_FOR",
    "managed_by": "WORKED_FOR",
    "coached by": "WORKED_FOR",
    "huấn luyện diễn xuất cho": "WORKED_FOR",
    "played_for": "WORKED_FOR",
    
    # Quan hệ tham gia
    "tham gia": "PARTICIPATED_IN",
    "được mời tham gia": "PARTICIPATED_IN",
    "participated_in": "PARTICIPATED_IN",
    "currently participates in": "PARTICIPATED_IN",
    "thử giọng tại": "PARTICIPATED_IN",
    
    # Quan hệ chứng nhận
    "Được chứng nhận bởi": "CERTIFIED_BY",
    "certified_by": "CERTIFIED_BY",
    
    # Quan hệ tạo ra/sáng tạo
    "created": "CREATED",
    
    # Quan hệ phát hành
    "released": "RELEASED",
    "phát hành đĩa đơn": "RELEASED",
    "phát hành đĩa đơn đạt thứ hạng trên": "RELEASED",
    "phát hành album đạt thứ hạng trên": "RELEASED",
    "ra mắt dòng nước hoa": "RELEASED",
    "published_book": "RELEASED",
    
    # Quan hệ xếp hạng
    "được xếp hạng bởi": "RANKED_BY",
    "Đạt vị trí số 1 trên": "RANKED_BY",
    "đứng hạng 6": "RANKED_BY",
    "listed_in": "RANKED_BY",
    
    # Quan hệ khác
    "là": "IS_A",
    "is a": "IS_A",
    "is_a": "IS_A",
    "real_name_is": "IS_A",
    "born_as": "IS_A",
    "quốc tịch": "NATIONALITY",
    "Qua đời tại": "DIED_IN",
    "có mối quan hệ với": "RELATED_TO",
    "có sự cố với": "RELATED_TO",
    "idolized": "INFLUENCED_BY",
    "gây ấn tượng với": "INFLUENCED_BY",
    "helped_launch_career_of": "INFLUENCED",
    "teacher_of": "INFLUENCED",
    "là trợ lý nghiên cứu của": "WORKED_FOR",
    "trained under": "TRAINED_UNDER",
    "trained in": "TRAINED_IN",
    "thu âm tại": "RECORDED_AT",
    "lồng tiếng": "VOICED",
    "tổ chức lưu diễn tại": "TOURED_IN",
    "trình diễn DJ lần đầu tại": "DEBUTED_AT",
    "trong sê ri": "PART_OF",
    "part_of": "PART_OF",
    "distributed_by": "DISTRIBUTED_BY",
    "wrote for": "WROTE_FOR",
    "wrote screenplay for": "WROTE_FOR",
    "held title": "HELD_TITLE",
    "held_title": "HELD_TITLE",
    "đạt danh hiệu Á hậu thứ nhất": "HELD_TITLE",
    "là nghệ sĩ được phát trực tuyến nhiều nhất trên": "ACHIEVED_SUCCESS_ON",
    "achieved_success_on": "ACHIEVED_SUCCESS_ON",
    "gained recognition in": "ACHIEVED_SUCCESS_ON",
    "ủng hộ": "SUPPORTED",
    "là nhà đầu tư của": "INVESTED_IN",
    "được nhận vào": "ADMITTED_TO",
    "được nhận xét bởi": "REVIEWED_BY",
    "lost first MMA fight to": "COMPETED_WITH",
    "chuyển sang hợp tác với": "COLLABORATED_WITH",
}

def normalize_relationships(input_file, output_file):
    """
    Đọc file JSON, chuẩn hóa các mối quan hệ tiếng Việt sang tiếng Anh,
    và ghi vào file mới
    """
    # Đọc dữ liệu
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Thống kê
    total_normalized = 0
    not_mapped = set()
    
    # Chuẩn hóa
    for entity_key, entity_data in data.items():
        if 'relationships' in entity_data:
            for rel in entity_data['relationships']:
                old_type = rel['type']
                
                # Kiểm tra xem có trong bảng ánh xạ không
                if old_type in RELATIONSHIP_MAPPING:
                    rel['type'] = RELATIONSHIP_MAPPING[old_type]
                    total_normalized += 1
                else:
                    not_mapped.add(old_type)
    
    # Ghi file mới
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # In thống kê
    print(f"✓ Đã chuẩn hóa {total_normalized} mối quan hệ")
    print(f"✓ Đã lưu vào file: {output_file}")
    
    if not_mapped:
        print(f"\n⚠ Có {len(not_mapped)} loại quan hệ chưa được ánh xạ:")
        for rel_type in sorted(not_mapped):
            print(f"  - {rel_type}")
    
    return data

ALLOWED_RELATIONSHIPS = {
    'ACHIEVED_SUCCESS_ON',
    'AWARDED_AT',
    'BORN_IN',
    'CERTIFIED_BY',
    'CREATED',
    'DEBUTED_AT',
    'DIED_IN',
    'DISTRIBUTED_BY',
    'EDUCATED_AT',
    'FOUNDED',
    'INFLUENCED',
    'INVESTED_IN',
    'LIVED_IN',
    'NOMINATED_FOR',
    'OWNED',
    'PARTICIPATED_IN',
    'PART_OF',
    'PERFORMED_AT',
    'PRODUCED',
    'RANKED_BY',
    'RECORDED_AT',
    'RELATED_TO',
    'RELEASED',
    'SUPPORTED',
    'TOURED_IN',
    'TRAINED_IN',
    'VOICED',
    'WON_AWARD',
    'WORKED_FOR',
}

# Bảng ánh xạ đổi tên và xóa
RELATIONSHIP_RENAME = {
    'NOMINATED_FOR_WORK': 'NOMINATED_FOR',
    'PERFORMED_ON': 'PERFORMED_AT',
    'SIGNED_WITH': 'WORKED_FOR',
    'STARRED_IN': 'TOURED_IN',
    'TRAINED_UNDER': 'TRAINED_IN',
    'WROTE_FOR': 'WORKED_FOR',
}

# Danh sách các mối quan hệ cần xóa
RELATIONSHIPS_TO_DELETE = {
    'WON_AWARD_FOR',
}

def filter_and_normalize_relationships(input_file, output_file):
    """
    Lọc và chuẩn hóa các mối quan hệ:
    - Đổi tên theo bảng RELATIONSHIP_RENAME
    - Xóa các mối quan hệ trong RELATIONSHIPS_TO_DELETE
    - Chỉ giữ lại các mối quan hệ trong ALLOWED_RELATIONSHIPS
    """
    # Đọc dữ liệu
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Thống kê
    total_relationships = 0
    renamed_count = 0
    deleted_count = 0
    filtered_count = 0
    
    # Xử lý từng entity
    for entity_key, entity_data in data.items():
        if 'relationships' in entity_data:
            original_relationships = entity_data['relationships']
            filtered_relationships = []
            
            for rel in original_relationships:
                total_relationships += 1
                rel_type = rel['type']
                
                # Bước 1: Xóa các mối quan hệ không mong muốn
                if rel_type in RELATIONSHIPS_TO_DELETE:
                    deleted_count += 1
                    continue
                
                # Bước 2: Đổi tên các mối quan hệ
                if rel_type in RELATIONSHIP_RENAME:
                    rel['type'] = RELATIONSHIP_RENAME[rel_type]
                    rel_type = rel['type']
                    renamed_count += 1
                
                # Bước 3: Chỉ giữ các mối quan hệ được phép
                if rel_type in ALLOWED_RELATIONSHIPS:
                    filtered_relationships.append(rel)
                else:
                    filtered_count += 1
            
            # Cập nhật lại danh sách relationships
            entity_data['relationships'] = filtered_relationships
    
    # Ghi file mới
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # In thống kê
    print("=" * 60)
    print("KẾT QUẢ LỌC VÀ CHUẨN HÓA MỐI QUAN HỆ")
    print("=" * 60)
    print(f"📊 Tổng số mối quan hệ ban đầu: {total_relationships}")
    print(f"✏️  Đã đổi tên: {renamed_count} mối quan hệ")
    print(f"🗑️  Đã xóa: {deleted_count} mối quan hệ (WON_AWARD_FOR)")
    print(f"🚫 Đã lọc bỏ: {filtered_count} mối quan hệ (không trong danh sách)")
    print(f"✅ Còn lại: {total_relationships - deleted_count - filtered_count} mối quan hệ")
    print(f"💾 Đã lưu vào file: {output_file}")
    
    return data

def verify_relationships(data):
    """
    Kiểm tra và hiển thị các loại mối quan hệ sau khi lọc
    """
    relationship_types = set()
    relationship_counts = {}
    
    for entity_key, entity_data in data.items():
        if 'relationships' in entity_data:
            for rel in entity_data['relationships']:
                rel_type = rel['type']
                relationship_types.add(rel_type)
                relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1
    
    print("\n" + "=" * 60)
    print(f"📋 CÁC LOẠI MỐI QUAN HỆ SAU KHI LỌC ({len(relationship_types)} loại)")
    print("=" * 60)
    
    for idx, rel_type in enumerate(sorted(relationship_types), 1):
        count = relationship_counts[rel_type]
        print(f"{idx:2d}. {rel_type:30s} ({count:,} mối quan hệ)")
    
    # Kiểm tra xem có mối quan hệ nào không nằm trong danh sách cho phép không
    unexpected = relationship_types - ALLOWED_RELATIONSHIPS
    if unexpected:
        print("\n⚠️  CẢNH BÁO: Có mối quan hệ không nằm trong danh sách cho phép:")
        for rel_type in sorted(unexpected):
            print(f"  - {rel_type}")
    else:
        print("\n✅ TẤT CẢ MỐI QUAN HỆ ĐỀU HỢP LỆ!")

# Lọc, chọn các mối quan hệ mình cần
if __name__ == "__main__":
    input_file = "output/data_normalized.json"  # File đã chuẩn hóa từ bước trước
    output_file = "output/all_actors_data_filtered.json"   # File sau khi lọc
    
    # Lọc và chuẩn hóa
    filtered_data = filter_and_normalize_relationships(input_file, output_file)
    
    # Kiểm tra kết quả
    verify_relationships(filtered_data)
    
    print("\n" + "=" * 60)
    print("HOÀN THÀNH!")
    print("=" * 60)


# Chuẩn hóa các mối quan hệ sau khi gọi LLM
# if __name__ == "__main__":
#     input_file = "output/all_actors_extracted.json" 
#     output_file = "output/all_actor_data_normalized.json"  
    
#     normalized_data = normalize_relationships(input_file, output_file)
    
#     # Kiểm tra số loại quan hệ sau khi chuẩn hóa
#     relationship_types = set()
#     for entity_key, entity_data in normalized_data.items():
#         if 'relationships' in entity_data:
#             for rel in entity_data['relationships']:
#                 relationship_types.add(rel['type'])
    
#     print(f"\n📊 Tổng số loại quan hệ sau chuẩn hóa: {len(relationship_types)}")
#     print("\nDanh sách các loại quan hệ sau chuẩn hóa:")
#     for idx, rel_type in enumerate(sorted(relationship_types), 1):
#         print(f"{idx}. {rel_type}")