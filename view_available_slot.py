import json

# JSON 파일 읽기
with open('slots_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# is_available이 true인 것만 필터링
available_slots = [item for item in data if item.get('is_available') == True]

# 결과를 새 JSON 파일로 저장
with open('available_slots_data.json', 'w', encoding='utf-8') as f:
    json.dump(available_slots, f, ensure_ascii=False, indent=2)

print(f"총 {len(available_slots)}개의 예약 가능한 슬롯을 찾았습니다.")
print(f"결과가 'available_slots_data.json' 파일로 저장되었습니다.")