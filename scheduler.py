import json
from ortools.sat.python import cp_model
from datetime import datetime, timedelta

# -----------------------------
# Helper functions
# -----------------------------
def load_data(filename):
    """
    JSON 파일을 읽어 파이썬 객체로 반환합니다.

    - filename: JSON 파일 경로 (문자열)
    반환값: json.load로 읽어들인 파이썬 자료구조 (list 또는 dict)
    """
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def minutes_to_time_str(minutes):
    """
    분 단위 정수를 'HH:MM' 형식의 문자열로 변환합니다.

    예: 75 -> '01:15'
    이 함수는 출력용으로만 사용되며 내부 계산은 분 단위를 유지합니다.
    """
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


# -----------------------------
# Main scheduling logic
# -----------------------------
def run_local_poc(patient_exams, next_appointment_date_str):
    """
    환자 검사 목록과 다음 진료일을 받아 OR-Tools CP-SAT로 최소 방문 일수를 최소화하는
    검사 스케줄을 찾습니다.

    주요 개념:
    - slots_data.json: 가능한 검사 슬롯(날짜, 시작/종료 시간, 검사종류 등)을 포함
    - constraints.json: 검사 간의 제약(cannot_same_day, must_same_day, sequence_and_gap 등)
    - required_exams: 환자가 받아야 하는 검사 목록
    - 목적: 환자의 모든 검사를 가능한 한 적은 날짜(day) 내에 배정

    파라미터:
    - patient_exams: 검사 이름 문자열의 리스트
    - next_appointment_date_str: 'YYYY-MM-DD' 형식의 다음 진료일 문자열
    """

    # -----------------------------
    # 1) 입력 데이터 로드 및 전처리
    # -----------------------------
    slots_data = load_data('slots_data.json')         # 가능한 모든 슬롯 정보
    rules_data = load_data('constraints.json')        # 제약 및 전역 설정

    required_exams = patient_exams  # 사용자가 받아야 하는 검사들

    # constraints.json에 명시된 'result_waiting_days' 만큼 여유를 두고 검사 완료 기한 계산
    N_DAYS = rules_data['result_waiting_days']
    next_appointment_date = datetime.strptime(next_appointment_date_str, '%Y-%m-%d').date()
    deadline_date = next_appointment_date - timedelta(days=N_DAYS)
    print(f"📌 다음 진료일: {next_appointment_date} | 검사 완료 기한: {deadline_date}")

    # 검사 기한을 초과하는 슬롯은 고려하지 않음
    valid_slots = []
    for slot in slots_data:
        slot_date = datetime.strptime(slot['date'], '%Y-%m-%d').date()
        # 슬롯 날짜가 데드라인 이전(또는 동일)이고 해당 슬롯의 검사가 required_exams에 있을 때만 유효
        if slot_date <= deadline_date and slot['exam'] in required_exams:
            valid_slots.append(slot)

    if not valid_slots:
        print("❌ 유효한 기간 내에 가능한 슬롯이 없습니다.")
        return

    all_slots = valid_slots

    # -----------------------------
    # 2) CP-SAT 모델링 (변수 및 제약 추가)
    # -----------------------------
    model = cp_model.CpModel()

    # 선택 변수: (exam, slot_id) 쌍에 대해 0/1 변수 생성
    # choices[(exam_name, slot_id)] = BoolVar
    choices = {}

    # exam_slots_map: 각 검사별로 해당 가능한 슬롯들을 모아둠 (검사 -> [slot, ...])
    exam_slots_map = {e: [] for e in required_exams}

    for slot in all_slots:
        exam = slot['exam']
        if exam in required_exams:
            # 슬롯 선택 여부를 표현하는 BoolVar
            var = model.NewBoolVar(f'{exam}_in_slot_{slot["id"]}')
            choices[(exam, slot['id'])] = var
            exam_slots_map[exam].append(slot)

    # 제약 (1): 각 검사는 정확히 하나의 슬롯에 배정되어야 함
    for exam in required_exams:
        if exam not in exam_slots_map or not exam_slots_map[exam]:
            # 특정 검사에 대해 사용 가능한 슬롯이 없다면 스케줄링 불가
            print(f"ERROR: {exam}에 대한 유효한 슬롯 데이터가 없습니다.")
            return

        vars_for_this_exam = [choices[(exam, slot['id'])] for slot in exam_slots_map[exam]]
        # sum(vars) == 1: 반드시 하나의 슬롯만 선택
        model.Add(sum(vars_for_this_exam) == 1)

    # 제약 (2): cannot_same_day, must_same_day, sequence_and_gap 등 추가 제약 처리
    # (a) cannot_same_day: 규칙에 정의된 두 검사가 같은 날짜에 배정되지 않도록 함
    for ex1_name, ex2_name in rules_data['constraints'].get('cannot_same_day', []):
        if ex1_name in required_exams and ex2_name in required_exams:
            for s1 in exam_slots_map[ex1_name]:
                for s2 in exam_slots_map[ex2_name]:
                    if s1['date'] == s2['date']:
                        var1 = choices[(ex1_name, s1['id'])]
                        var2 = choices[(ex2_name, s2['id'])]
                        # 둘 다 선택되는 것을 금지 (Not A or Not B)
                        model.AddBoolOr([var1.Not(), var2.Not()])

    # (b) must_same_day: 그룹 내 검사들은 같은 날짜에 배정되어야 함
    # 구현 방식: 그룹 내 서로 다른 검사 쌍에 대해 '같은 날짜가 아닐 경우' 두 변수를 동시에 선택 불가로 설정
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
                            # 서로 다른 날짜에 배정되는 조합을 금지
                            model.AddBoolOr([var1.Not(), var2.Not()])

    # (c) sequence_and_gap: 선행 검사와 후속 검사 사이의 최소 시간 간격 및 날짜 순서 제약
    for rule in rules_data['constraints'].get('sequence_and_gap', []):
        pre_name = rule['pre']
        post_name = rule['post']
        gap = rule['min_gap_minutes']

        if pre_name in required_exams and post_name in required_exams:
            for pre_s in exam_slots_map[pre_name]:
                for post_s in exam_slots_map[post_name]:
                    pre_var = choices[(pre_name, pre_s['id'])]
                    post_var = choices[(post_name, post_s['id'])]

                    # 같은 날짜인 경우: 선행 검사 종료시간 + gap <= 후속 검사 시작시간 이어야 함
                    if pre_s['date'] == post_s['date']:
                        if pre_s['end_min'] + gap > post_s['start_min']:
                            # 시간 간격을 만족하지 못하면 두 변수가 동시에 1이 될 수 없음
                            model.AddBoolOr([pre_var.Not(), post_var.Not()])

                    # 날짜 순서 제약: 선행 검사 날짜가 후속 검사 날짜보다 늦으면 안 됨
                    pre_date = datetime.strptime(pre_s['date'], '%Y-%m-%d').date()
                    post_date = datetime.strptime(post_s['date'], '%Y-%m-%d').date()
                    if pre_date > post_date:
                        model.AddBoolOr([pre_var.Not(), post_var.Not()])

    # -----------------------------
    # 3) 목적 함수: 방문 일수 최소화
    # - 같은 날짜에 여러 검사가 몰리면 방문 일수는 증가하지 않도록
    # - 각 날짜에 대해 '그 날짜에 적어도 한 검사가 선택되었는가'를 나타내는 BoolVar 생성
    # -----------------------------
    all_dates = sorted(list(set(s['date'] for s in all_slots)))
    day_used_vars = []

    for date_str in all_dates:
        is_day_used = model.NewBoolVar(f'day_used_{date_str}')
        # 해당 날짜에 배정된 모든 슬롯의 선택 변수들을 모음
        vars_on_this_day = [v for (e, s_id), v in choices.items()
                            if next(item for item in all_slots if item['id'] == s_id)['date'] == date_str]

        # is_day_used == max(vars_on_this_day) 형태로 표현
        model.AddMaxEquality(is_day_used, vars_on_this_day)
        day_used_vars.append(is_day_used)

    # 방문한 날짜 수의 합을 최소화
    model.Minimize(sum(day_used_vars))

    # -----------------------------
    # 4) 솔버 실행 및 결과 해석
    # -----------------------------
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    print("\n" + "=" * 50)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"✅ 스케줄링 성공! (최소 방문 일수: {solver.ObjectiveValue():.0f}일)")

        # 선택된 슬롯들을 읽어 사람이 읽기 쉬운 형태로 변환
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

        # 날짜/시간 순으로 정렬해서 출력
        result_schedule.sort(key=lambda x: (x['Date'], x['Start']))

        for item in result_schedule:
            print(f"  > [{item['Date']}] {item['Start']} - {item['End']} : {item['Exam']}")

    else:
        # 해가 존재하지 않을 경우 (모든 제약 만족 불가)
        print("❌ 제약 조건을 모두 만족하는 스케줄을 찾지 못했습니다 (INFEASIBLE).")


if __name__ == '__main__':
    # =========================================================
    # 실행 예시: 로컬에서 스크립트를 바로 실행할 때 사용하는 입력값
    # 개발/디버그 용도로만 사용하고, 실제 배포시에는 외부 입력으로 교체하세요.
    # =========================================================

    # 환자가 받고자 하는 검사 리스트 (constraints.json의 "exam_metadata"와 이름이 일치해야 함)
    PATIENT_EXAMS = [
        "Exam_A_CT",
        "Exam_B_MRI",
        "Exam_C_Endoscopy",
        "Exam_D_BloodTest"
    ]

    # 다음 진료일 (모든 검사는 이 날짜의 N일 이전에 완료되어야 함)
    NEXT_APPOINTMENT = "2025-12-09"

    print("--- AI 통합 예약 스케줄링 POC ---")
    print(f"검사 목록: {PATIENT_EXAMS}")

    run_local_poc(PATIENT_EXAMS, NEXT_APPOINTMENT)