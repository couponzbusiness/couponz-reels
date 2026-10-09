"""Five narrative families, with no timing or editing decisions."""
from .evidence import validate
from datetime import date
FORMAT_NAMES = {'single': '단일 혜택 안내', 'comparison': '가격·구성 비교', 'procedure': '사용 절차', 'roundup': '여러 혜택 모음', 'cart': '장바구니 조합'}

def won(value):
    return f'{value:,}원'

def spoken_date(value):
    try:
        d = date.fromisoformat(value)
        return f'{d.year}년 {d.month}월 {d.day}일'
    except (ValueError, TypeError):
        return '미확인 날짜'

def conditions(o):
    parts = [f"대상은 {o.get('target') or '미확인'}이고, 이용 채널은 {o.get('channel') or '미확인'}입니다",
             f"기간은 {spoken_date(o.get('start'))}부터 {spoken_date(o.get('end'))}까지입니다"]
    if o.get('minimum_spend') is None:
        parts.append('최소 결제금액 미확인')
    elif o['minimum_spend']:
        parts.append(f"최소 결제금액은 {won(o['minimum_spend'])}입니다")
    if o.get('cap'):
        parts.append(f"혜택 상한은 {won(o['cap'])}입니다")
    if o.get('exclusions'):
        parts.append(', '.join(o['exclusions']) + '은 제외됩니다')
    if o.get('stacking'):
        parts.append('중복 사용 조건은 다음과 같습니다: ' + o['stacking'])
    if o.get('mandatory_fees'):
        parts.append(f"필수 추가비용은 {won(o['mandatory_fees'])}입니다")
    parts.append('표시 가격은 세금 포함입니다' if o.get('tax_included') is True else '세금은 별도입니다' if o.get('tax_included') is False else '세금 여부는 미확인입니다')
    return '. '.join(parts) + '.'

def make_script(job, result):
    fmt, offers = (job['format'], job['offers'])
    lines = []

    def add(role, text, paths):
        lines.append({'id': f's{len(lines) + 1}', 'role': role, 'text': text, 'claim_paths': paths})
    if fmt == 'single':
        o = offers[0]
        add('benefit', f"{o['name']}. {o['description']}", ['offers.0.name', 'offers.0.description'])
        add('conditions', conditions(o), ['offers.0'])
    elif fmt == 'comparison':
        calc = result['calculation']
        for i, o in enumerate(offers):
            amount = won(calc['baseline'] if i == 0 else calc['alternative']) if calc['status'] == 'supported' else (won(o['price'] + o['mandatory_fees']) if isinstance(o.get('price'), int) and isinstance(o.get('mandatory_fees'), int) else '미확인 금액')
            add('baseline' if i == 0 else 'alternative', f"{o['name']}, 필수비용 포함 예상 금액 {amount}. {o['description']}", [f'offers.{i}'])
        text = '동일 기준이 확인되지 않아 절약액 판단은 보류합니다.'
        if calc['status'] == 'supported':
            if calc['saving'] == 0:
                text = f"양쪽 모두 {won(calc['baseline'])}으로 금액 차이는 없습니다. 구성을 보고 선택하세요."
            elif calc['saving'] > 0:
                text = f"같은 구성과 조건의 예상 금액 차이는 {won(calc['saving'])}입니다. 결제 완료 금액은 아닙니다."
            else:
                text = f"대안이 {won(-calc['saving'])} 더 높습니다."
        add('difference', text, ['calculation'])
        if len(offers) == 2 and conditions(offers[0]) == conditions(offers[1]):
            add('conditions', '두 구성의 공통 조건입니다. ' + conditions(offers[0]), ['offers.0', 'offers.1'])
        else:
            for i, o in enumerate(offers):
                add('conditions', f"{o['name']}의 조건입니다. " + conditions(o), [f'offers.{i}'])
    elif fmt == 'procedure':
        o = offers[0]
        add('benefit', f"{o['name']}. {o['description']}", ['offers.0'])
        add('conditions', conditions(o), ['offers.0'])
        for i, step in enumerate(job.get('steps', [])):
            add('step', f"{i + 1}단계. {step['instruction']}", [f'steps.{i}'])
        add('verification', '발급과 결제 완료는 해당 화면으로 별도 확인해야 합니다.', [])
    elif fmt == 'roundup':
        add('theme', f"{job.get('theme', '독립된 혜택 모음')}입니다. 각 혜택은 따로 이용합니다.", [])
        for i, o in enumerate(offers):
            add('item', f"{o['name']}. {o['description']}", [f'offers.{i}'])
            add('conditions', conditions(o), [f'offers.{i}'])
    elif fmt == 'cart':
        calc = result['calculation']
        add('goal', '상품과 쿠폰을 조합한 예상 결제금액을 계산합니다.', [])
        for i, line in enumerate(job.get('cart', {}).get('lines', [])):
            add('item', f"{line['name']} {line['quantity']}개, 개당 {won(line['unit_price'])}입니다.", [f'cart.lines.{i}'])
        if calc['status'] == 'supported':
            add('calculation', f"상품 합계 {won(calc['subtotal'])}에서 즉시 쿠폰 {won(calc['immediate_discount'])}을 빼면, 필수비용 포함 예상 결제는 {won(calc['expected_payable'])}입니다.", ['calculation'])
            for i, reward in enumerate(calc['future_rewards']):
                add('future_reward', f"추가 보상은 조건부 {won(reward['amount'])} 상당의 {reward['kind']}입니다. {reward['condition'].rstrip('.')}. 지금 결제금액에서 빼지 않습니다.", [f'cart.rewards.{i}'])
        else:
            add('hold', '쿠폰 또는 필수비용 조건이 미확인이라 결제금액 계산은 보류합니다.', [])
        add('conditions', conditions(offers[0]), ['offers.0'])
    if result['status'] == 'hold':
        add('hold', '미확인 또는 불일치가 남아 있습니다. 혜택의 최종 안내는 보류합니다.', [])
    cta = job.get('cta')
    if cta and result['status'] == 'supported':
        text = {'check_conditions': '이용 전에 공식 안내에서 적용 조건을 확인하세요.', 'save_for_reference': '조건을 다시 확인할 수 있도록 저장해 두세요.'}[cta['action']]
        add('cta', text, [])
        lines[-1]['claim_type'] = 'editorial_recommendation'
    return lines

def draft(job):
    result = validate(job)
    if job.get('format') not in FORMAT_NAMES or not job.get('offers'):
        raise ValueError('Select one of five formats and provide at least one offer. Intake alone is not a verified job.')
    if any(o.get('currency') != 'KRW' for o in job['offers']):
        raise ValueError('This script MVP supports KRW only; other currencies need a separate formatter.')
    lines = make_script(job, result)
    for line in lines:
        line['status'] = 'provisional' if result['status'] == 'hold' else 'supported_by_reviewed_assertions'
    return {'engine_version': '0.1.0', 'job_id': job.get('id', 'untitled'), 'format': job['format'], 'format_name': FORMAT_NAMES[job['format']], 'format_reason': job.get('format_reason', '제작 측이 소재의 중심 질문에 따라 선택한 초안'), 'synthetic': bool(job.get('synthetic')), 'status': 'script_review_only', 'fact_check': result, 'script': lines, 'editorial_status': 'NOT DECIDED: effects, timing, captions, transitions and CTA visuals await discussion', 'approval': 'NOT RUN', 'blockers': ['Source collection/OCR/ASR not implemented', 'Producer fact and wording review required']}
