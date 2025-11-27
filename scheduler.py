import json
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# --- Helper Functions ---
# ... (load_data, minutes_to_time_str 함수는 이전과 동일) ...

def load_data(filename):
    """JSON 파일을 로드합니다."""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def minutes_to_time_str(minutes):
    """분을 'HH:MM' 형식의 문자열로 변환합니다."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


# --- Main Scheduler Logic ---

def run_local_poc(patient_exams, next_appointment_date_str): # <--- 입력값을 함수 인자로 받습니다.
    """OR-Tools CP-SAT 솔버를 실행하여 최적의 스케줄을 찾습니다."""
    
    # 1. 데이터 로드 및 초기 설정
    slots_data = load_data('slots_data.json')
    rules_data = load_data('constraints.json')
    
    # --- 환자 입력값 사용 ---
    required_exams = patient_exams # 환자가 받고자 하는 검사 목록
    
    # 다음 진료일 기준 N일 전 완료 제약 조건 계산
    N_DAYS = rules_data['result_waiting_days'] # constraints.json에서 7일 기본값 로드
    next_appointment_date = datetime.strptime(next_appointment_date_str, '%Y-%m-%d').date()
    deadline_date = next_appointment_date - timedelta(days=N_DAYS)
    print(f"📌 다음 진료일: {next_appointment_date} | 검사 완료 기한: {deadline_date}")

    # 검사 기한을 벗어나는 슬롯 필터링
    valid_slots = []
    for slot in slots_data:
        slot_date = datetime.strptime(slot['date'], '%Y-%m-%d').date()
        if slot_date <= deadline_date and slot['exam'] in required_exams:
            valid_slots.append(slot)
    
    if not valid_slots:
        print("❌ 유효한 기간 내에 가능한 슬롯이 없습니다.")
        return

    all_slots = valid_slots
    
    # 2. OR-Tools 모델링 시작 (이하 로직은 이전과 동일하게 진행)
    model = cp_model.CpModel()
    
    # --- 변수 생성 ---
    choices = {}
    exam_slots_map = {e: [] for e in required_exams}
    
    for slot in all_slots:
        exam = slot['exam']
        if exam in required_exams:
            var = model.NewBoolVar(f'{exam}_in_slot_{slot["id"]}')
            choices[(exam, slot['id'])] = var
            exam_slots_map[exam].append(slot)
    
    # [제약 1] 각 검사는 정확히 하나의 슬롯에 배정되어야 함
    # ... (이전 코드와 동일) ...
    for exam in required_exams:
        if exam not in exam_slots_map or not exam_slots_map[exam]:
            print(f"ERROR: {exam}에 대한 유효한 슬롯 데이터가 없습니다.")
            return

        vars_for_this_exam = [choices[(exam, slot['id'])] for slot in exam_slots_map[exam]]
        model.Add(sum(vars_for_this_exam) == 1)

    # [제약 2] 충돌 방지 (이 예시에서는 slots_data.json이 충돌 없는 슬롯을 가정했으므로 생략)
    # [제약 3] 의료진 제약 조건 적용 (cannot_same_day, must_same_day, sequence_and_gap)
    # ... (이전 코드와 동일) ...
    
    # (a) 같은 날 검사 불가능 (cannot_same_day)
    for ex1_name, ex2_name in rules_data['constraints'].get('cannot_same_day', []):
        if ex1_name in required_exams and ex2_name in required_exams:
            for s1 in exam_slots_map[ex1_name]:
                for s2 in exam_slots_map[ex2_name]:
                    if s1['date'] == s2['date']:
                        var1 = choices[(ex1_name, s1['id'])]
                        var2 = choices[(ex2_name, s2['id'])]
                        model.AddBoolOr([var1.Not(), var2.Not()])

    # (b) 같은 날 검사 필수 (must_same_day)
    for group in rules_data['constraints'].get('must_same_day', []):
        valid_group_exams = [e for e in group if e in required_exams]
        if len(valid_group_exams) >= 2:
            ex1_name = valid_group_exams[0]
            for ex2_name in valid_group_exams[1:]:
                for s1 in exam_slots_map[ex1_name]:
                    for s2 in exam_slots_map[ex2_name]:
                        if s1['date'] != s2['date']:
                            var1 = choices[(ex1_name, s1['id'])]
                            var2 = choices[(ex2_name, s2['id'])]
                            model.AddBoolOr([var1.Not(), var2.Not()])

    # (c) 순서 및 시간 간격 (sequence_and_gap)
    for rule in rules_data['constraints'].get('sequence_and_gap', []):
        pre_name = rule['pre']
        post_name = rule['post']
        gap = rule['min_gap_minutes']
        
        if pre_name in required_exams and post_name in required_exams:
            for pre_s in exam_slots_map[pre_name]:
                for post_s in exam_slots_map[post_name]:
                    pre_var = choices[(pre_name, pre_s['id'])]
                    post_var = choices[(post_name, post_s['id'])]
                    
                    # 1. 같은 날짜 제약: Pre가 Post보다 먼저 끝나야 함
                    if pre_s['date'] == post_s['date']:
                        if pre_s['end_min'] + gap > post_s['start_min']:
                            # 시간 간격 제약 위반 -> 이 조합은 불가
                            model.AddBoolOr([pre_var.Not(), post_var.Not()])
                    
                    # 2. 날짜 제약: Pre가 Post보다 늦은 날짜에 있으면 불가
                    pre_date = datetime.strptime(pre_s['date'], '%Y-%m-%d').date()
                    post_date = datetime.strptime(post_s['date'], '%Y-%m-%d').date()
                    if pre_date > post_date:
                        model.AddBoolOr([pre_var.Not(), post_var.Not()])


    # --- 목적 함수 (Objective) ---
    all_dates = sorted(list(set(s['date'] for s in all_slots))) # 유효 슬롯의 날짜만 사용
    day_used_vars = []

    for date_str in all_dates:
        is_day_used = model.NewBoolVar(f'day_used_{date_str}')
        # 해당 날짜에 할당된 모든 선택 변수
        vars_on_this_day = [v for (e, s_id), v in choices.items() 
                            if next(item for item in all_slots if item['id'] == s_id)['date'] == date_str]
        
        model.AddMaxEquality(is_day_used, vars_on_this_day)
        day_used_vars.append(is_day_used)

    model.Minimize(sum(day_used_vars))

    # 3. 솔버 실행 및 결과 출력 (이전 코드와 동일)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    print("\n" + "="*50)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"✅ 스케줄링 성공! (최소 방문 일수: {solver.ObjectiveValue():.0f}일)")
        
        result_schedule = []
        for slot in all_slots:
            exam = slot['exam']
            slot_id = slot['id']
            
            if (exam, slot_id) in choices and solver.Value(choices[(exam, slot_id)]) == 1:
                result_schedule.append({
                    "Exam": exam,
                    "Date": slot['date'],
                    "Start": minutes_to_time_str(slot['start_min']),
                    "End": minutes_to_time_str(slot['end_min'])
                })
        
        # 결과 정리 및 출력
        result_schedule.sort(key=lambda x: (x['Date'], x['Start']))
        
        for item in result_schedule:
            print(f"  > [{item['Date']}] {item['Start']} - {item['End']} : {item['Exam']}")

    else:
        print("❌ 제약 조건을 모두 만족하는 스케줄을 찾지 못했습니다 (INFEASIBLE).")


if __name__ == '__main__':
    # =========================================================
    # 📌 3. 실행 시 필요한 입력값을 여기에 직접 설정합니다.
    # =========================================================
    
    # 1. 환자가 받고자 하는 검사 리스트 (constraints.json의 "exam_metadata"와 일치해야 함)
    PATIENT_EXAMS = [
        "Exam_A_CT", 
        "Exam_B_MRI", 
        "Exam_C_Endoscopy", 
        "Exam_D_BloodTest"
    ]
    
    # 2. 다음 진료일 (모든 검사는 이 날짜 N일 전에 완료되어야 함)
    NEXT_APPOINTMENT = "2025-12-09" # 예시: 화요일
    
    # OR-Tools 실행
    print("--- AI 통합 예약 스케줄링 POC ---")
    print(f"검사 목록: {PATIENT_EXAMS}")
    
    run_local_poc(PATIENT_EXAMS, NEXT_APPOINTMENT)