import json
from datetime import datetime, timedelta
import random

def minutes_to_time_str(minutes):
    """분을 'HH:MM' 형식의 문자열로 변환합니다."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def generate_slots_data_sorted_by_exam(start_date_str, end_date_str, booked_percentage=20, output_format_mode=0):
    """
    슬롯 데이터를 생성하고 정렬한 후, output_format_mode에 따라 JSON 출력 형식을 제어합니다.
    """
    
    EXAMS_INFO = {
        "Exam_A_CT": 30, "Exam_B_MRI": 60, 
        "Exam_C_Endoscopy": 45, "Exam_D_BloodTest": 15
    }
    
    # --- 날짜 파라미터 처리 ---
    try:
        current_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        print("❌ 오류: 날짜 형식은 YYYY-MM-DD(예: 2025-12-01)를 사용해야 합니다.")
        return
    
    if current_date > end_date:
        print("❌ 오류: 시작 날짜가 끝 날짜보다 늦을 수 없습니다.")
        return
    
    # --- 슬롯 생성 로직 (이전과 동일) ---
    
    all_slots = []
    slot_id_counter = 1
    first_date = current_date

    while current_date <= end_date:
        if current_date.weekday() < 5: 
            for start_min_of_day in range(540, 1020, 30): 
                for exam_name, duration in EXAMS_INFO.items():
                    slot_start_min = start_min_of_day
                    slot_end_min = start_min_of_day + duration
                    
                    if slot_end_min > 1020: 
                        continue

                    all_slots.append({
                        "id": slot_id_counter,
                        "exam": exam_name,
                        "date": current_date.strftime("%Y-%m-%d"),
                        "day": (current_date - first_date).days + 1,
                        "start_min": slot_start_min,
                        "end_min": slot_end_min,
                        "is_available": True
                    })
                    slot_id_counter += 1
        
        current_date += timedelta(days=1)

    total_slots = len(all_slots)
    if total_slots == 0:
        print(f"기간: {start_date_str} ~ {end_date_str}")
        print("✅ 생성된 유효한 슬롯이 없습니다 (주말, 잘못된 기간 지정 등).")
        return
        
    slots_to_book = int(total_slots * (booked_percentage / 100))
    booked_indices = random.sample(range(total_slots), slots_to_book)
    
    for index in booked_indices:
        all_slots[index]['is_available'] = False
        
    for slot in all_slots:
        start_time_str = minutes_to_time_str(slot['start_min'])
        end_time_str = minutes_to_time_str(slot['end_min'])
        status = "예약 가능" if slot['is_available'] else "예약됨"
        slot['time_status_display'] = f"{start_time_str}-{end_time_str}, {status}"

    print(f"기간: {start_date_str} ~ {end_date_str}")
    print(f"총 {total_slots}개 슬롯 중 {slots_to_book}개 ({booked_percentage}%)가 예약됨 처리되었습니다.")

    # --- 정렬 및 출력 형식 제어 (로직 동일) ---
    all_slots.sort(key=lambda x: (x['exam'], x['date'], x['start_min']))
    
    output_filename = 'slots_data.json'
    
    if output_format_mode == 0:
        indent_level = 4
        separators = (',', ': ')
        print("💡 출력 모드 0: 항목별 줄 바꿈 및 들여쓰기 (개발/디버깅용)")
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(all_slots, f, indent=indent_level, separators=separators, ensure_ascii=False)
            
    else: # output_format_mode == 1 (ID별 줄 바꿈 모드)
        print("💡 출력 모드 1: ID별 줄 바꿈 (압축 + 가독성 최적화)")
        json_strings = []
        for slot in all_slots:
            compressed_slot = json.dumps(slot, separators=(',', ':'), ensure_ascii=False)
            json_strings.append(compressed_slot)
            
        file_content = "[\n" + ",\n".join(json_strings) + "\n]"
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(file_content)

    print(f"✅ 정렬 및 형식 제어된 {output_filename} 파일이 성공적으로 생성되었습니다.")


if __name__ == '__main__':
    
    # =========================================================
    # 📌 여기에 원하는 파라미터를 지정하세요!
    # =========================================================
    
    # 1. 생성 기간 설정 (YYYY-MM-DD 형식)
    START_DATE = "2025-12-01" 
    END_DATE = "2025-12-10" 
    
    # 2. 예약률 설정 (0~100)
    BOOKED_PERCENTAGE = 80  # 예시: 30%의 슬롯이 이미 예약됨
    
    # 3. 출력 형식 모드 설정 (0 또는 1)
    # 0: 가독성 모드 (들여쓰기) | 1: ID별 줄 바꿈 모드 (압축)
    FORMAT_MODE = 1
    
    # ---------------------------------------------------------

    # 함수 실행 (위에 지정된 변수 사용)
    generate_slots_data_sorted_by_exam(
        start_date_str=START_DATE,
        end_date_str=END_DATE,
        booked_percentage=BOOKED_PERCENTAGE,
        output_format_mode=FORMAT_MODE
    )