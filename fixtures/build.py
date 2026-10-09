"""Five PUBLIC, synthetic examples. Values are not current promotions."""
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from couponz.evidence import flatten


def offer(name, description, price=3000):
    return {"name": name, "description": description, "price": price,
            "target": "가상 앱 회원", "channel": "가상 앱 주문", "start": "2026-10-01", "end": "2026-10-31",
            "minimum_spend": 0, "cap": 0, "exclusions": [], "stacking": "다른 쿠폰 중복 불가",
            "tax_included": True, "mandatory_fees": 0, "currency": "KRW",
            "kind": "physical", "model": "synthetic-coffee", "quantity": 1,
            "components": ["커피 1잔"], "eligibility": "가상 앱 회원"}


def evidence_for(job):
    assertions = {}
    for root in ("offers", "steps", "cart"):
        if root not in job:
            continue
        value = job[root]
        if isinstance(value, list):
            for i, item in enumerate(value):
                assertions.update(dict(flatten(item, f"{root}.{i}")))
        else:
            assertions.update(dict(flatten(value, root)))
    if 'theme' in job:
        assertions['theme'] = job['theme']
    job["evidence"] = [{"id": "synthetic-source", "kind": "synthetic", "scope": "conditions",
                        "locator": "본 JSON의 가상 입력표", "source_url": "https://example.invalid/synthetic",
                        "checked_at": "2026-10-09T00:00:00Z", "reviewed": True, "complete": False,
                        "assertions": assertions}]
    job["provenance"] = {path: ["synthetic-source"] for path in assertions}
    return job


def examples():
    base = {"schema_version": 1, "synthetic": True, "use_date": "2026-10-09"}
    a = {**base, "id": "A", "format": "single", "format_reason": "한 커피 혜택과 적용조건 설명",
         "offers": [offer("가상 커피 혜택", "앱 회원은 커피 한 잔을 3,000원에 주문할 수 있습니다.")],
         "cta": {"action": "check_conditions"}}
    burger = offer("버거와 음료를 따로 주문", "버거 7,900원과 음료 2,000원을 합친 구성입니다.", 9900)
    burger.update(model="synthetic-burger-meal", components=["버거 1개", "음료 1개"])
    meal = deepcopy(burger)
    meal.update(name="9,900원 세트", description="같은 버거 1개와 음료 1개가 들어 있는 9,900원 세트입니다.")
    b = {**base, "id": "B", "format": "comparison", "offers": [burger, meal], "format_reason": "같은 구성의 가격 차이 확인"}
    c_offer = offer("가상 앱 쿠폰", "쿠폰 목록에서 발급 안내를 확인할 수 있습니다.")
    c_offer["minimum_spend"] = None
    c = {**base, "id": "C", "format": "procedure", "offers": [c_offer], "format_reason": "앱 안에서 확인하는 경로가 중심",
         "steps": [{"instruction": "앱의 쿠폰 목록을 엽니다."}, {"instruction": "해당 쿠폰의 상세 조건을 확인합니다."}],
         "cta": {"action": "check_conditions"}}
    d = {**base, "id": "D", "format": "roundup", "theme": "가상 혜택 세 가지", "format_reason": "각 혜택을 따로 이용 가능",
         "offers": [offer("가상 커피", "커피 한 잔 예상 3,000원입니다."), offer("가상 빵", "빵 한 개 예상 2,000원입니다.", 2000), offer("가상 음료", "음료 한 잔 예상 1,500원입니다.", 1500)]}
    d["offers"][1].update(model="synthetic-bread", components=["빵 1개"])
    d["offers"][2].update(model="synthetic-drink", components=["음료 1잔"])
    e_offer = offer("가상 장바구니 쿠폰", "상품 합계 30,000원 이상이면 즉시 5,000원 쿠폰을 사용할 수 있습니다.", 30000)
    e_offer.update(minimum_spend=30000, cap=5000)
    e = {**base, "id": "E", "format": "cart", "offers": [e_offer], "format_reason": "상품·수량·쿠폰이 한 거래로 연결",
         "cart": {"lines": [{"name": "가상 상품", "unit_price": 10000, "quantity": 3}],
                  "coupon": {"amount": 5000, "minimum_spend": 30000}, "mandatory_fees": 0,
                  "rewards": [{"id": "future-points-1", "amount": 5000, "kind": "포인트", "condition": "다음 달 지급 조건을 충족해야 합니다"}]}}
    return {j["id"]: evidence_for(j) for j in (a, b, c, d, e)}


if __name__ == "__main__":
    for ident, job in examples().items():
        (Path(__file__).parent/f"{ident}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
