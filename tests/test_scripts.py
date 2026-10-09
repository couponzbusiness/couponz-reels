"""Executed script-scope checks, not the original 29 full media acceptance tests."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from couponz.evidence import validate, check_fact, compare, cart
from couponz.intake import intake, SourceExtractor, SpeechRecognizer
from couponz.planner import draft
from fixtures.build import examples, evidence_for


class ScriptChecks(unittest.TestCase):
    def setUp(self):
        self.jobs = examples()

    def text(self, ident):
        return '\n'.join(l['text'] for l in draft(self.jobs[ident])['script'])

    def test_five_distinct_narrative_families(self):
        drafts = [draft(self.jobs[x]) for x in 'ABCDE']
        self.assertEqual(len({d['format'] for d in drafts}), 5)
        roles = [{l['role'] for l in d['script']} for d in drafts]
        self.assertIn('difference', roles[1])
        self.assertIn('step', roles[2])
        self.assertIn('theme', roles[3])
        self.assertIn('future_reward', roles[4])
        self.assertNotIn('step', roles[0])
        self.assertNotIn('tracks', drafts[0])

    def test_A_single_coffee(self):
        result=validate(self.jobs['A'])
        self.assertEqual(result['status'], 'supported')
        self.assertIn('3,000원', self.text('A'))
        self.assertTrue(result['script_candidate_allowed'])
        self.assertFalse(result['final_claim_allowed'])  # synthetic, no real promotion

    def test_B_equal_9900_no_false_2000_saving(self):
        self.assertEqual(validate(self.jobs['B'])['calculation']['saving'], 0)
        self.assertIn('금액 차이는 없습니다', self.text('B'))
        self.assertNotIn('2,000원 절약', self.text('B'))
        job=deepcopy(self.jobs['B']); job['declared_saving']=2000
        self.assertIn('declared_saving_conflict', validate(job)['issues'])

    def test_C_missing_minimum_blocks_claim_and_cta(self):
        d=draft(self.jobs['C'])
        self.assertEqual(d['fact_check']['status'], 'hold')
        self.assertFalse(d['fact_check']['final_claim_allowed'])
        self.assertIn('최소 결제금액 미확인', self.text('C'))
        self.assertNotIn('쿠폰을 바로 사용하세요', self.text('C'))
        self.assertTrue(all(l['status']=='provisional' for l in d['script']))

    def test_D_independent_roundup_not_summed(self):
        d=draft(self.jobs['D'])
        self.assertEqual(len([l for l in d['script'] if l['role']=='item']), 3)
        self.assertIn('따로 이용', self.text('D'))
        self.assertNotIn('6,500원', self.text('D'))
        self.assertIsNone(d['fact_check']['calculation'])
        j=deepcopy(self.jobs['D']); j['linked_purchase']=True
        self.assertIn('linked_purchase_requires_cart_review', validate(j)['issues'])

    def test_E_payable_25000_future_points_separate(self):
        result=validate(self.jobs['E'])
        self.assertEqual(result['calculation']['expected_payable'], 25000)
        self.assertFalse(result['calculation']['future_rewards_deducted'])
        self.assertIn('예상 결제는 25,000원', self.text('E'))
        self.assertNotIn('20,000원', self.text('E'))
        self.assertIn('지금 결제금액에서 빼지 않습니다', self.text('E'))
        j=deepcopy(self.jobs['E']); j['cart']['declared_payable']=20000; evidence_for(j)
        self.assertEqual(validate(j)['status'], 'hold')

    def test_unknown_is_not_zero(self):
        j=deepcopy(self.jobs['A']); j['offers'][0]['mandatory_fees']=None; evidence_for(j)
        self.assertEqual(validate(j)['status'], 'hold')
        self.assertEqual(check_fact(j,'offers.0.mandatory_fees',None)['status'],'unknown')

    def test_evidence_conflict_and_missing_locator(self):
        j=deepcopy(self.jobs['A']); j['offers'][0]['price']=2000
        self.assertEqual(check_fact(j,'offers.0.price',2000)['status'],'conflict')
        j=deepcopy(self.jobs['A']); j['evidence'][0]['locator']=None
        self.assertEqual(validate(j)['status'],'hold')

    def test_synthetic_cannot_be_official(self):
        j=deepcopy(self.jobs['A']); j['synthetic']=False
        self.assertEqual(validate(j)['status'],'hold')

    def test_expired_future_unknown_date(self):
        for date in ('2026-11-01','2026-09-30',None):
            j=deepcopy(self.jobs['A']); j['use_date']=date
            self.assertEqual(validate(j)['status'],'hold')

    def test_comparison_basis_and_tax(self):
        for field, value in (('quantity',2),('kind','digital'),('model','other'),('eligibility','new members'),('tax_included',None),('components',['burger only'])):
            j=deepcopy(self.jobs['B']); j['offers'][1][field]=value; evidence_for(j)
            self.assertEqual(validate(j)['calculation']['status'],'hold',field)
            self.assertNotIn('금액 차이는 없습니다', '\n'.join(x['text'] for x in draft(j)['script']))

    def test_mandatory_fee_is_included(self):
        j=deepcopy(self.jobs['B']); j['offers'][1]['mandatory_fees']=1000; evidence_for(j)
        self.assertEqual(validate(j)['calculation']['saving'],-1000)
        self.assertIn('1,000원 더 높습니다', '\n'.join(x['text'] for x in draft(j)['script']))

    def test_receipt_scope_not_upgraded(self):
        for scope in ('conditions','poster','expected_checkout','balance_due','partial_receipt'):
            j=deepcopy(self.jobs['A']); j['offers'][0]['claimed_state']='paid'; evidence_for(j); j['evidence'][0]['scope']=scope
            self.assertIn('offers.0:paid_state_not_proven',validate(j)['issues'])

    def test_issued_needs_complete_evidence(self):
        j=deepcopy(self.jobs['A']); j['offers'][0]['claimed_state']='issued'; evidence_for(j)
        self.assertIn('offers.0:issued_state_not_proven',validate(j)['issues'])

    def test_unknown_net_spend_and_duplicate_rewards(self):
        j=deepcopy(self.jobs['A']); j['offers'][0]['net_spend']=2000; evidence_for(j)
        self.assertIn('offers.0:net_spend_requires_separate_review',validate(j)['issues'])
        j=deepcopy(self.jobs['E']); j['cart']['rewards']*=2; evidence_for(j)
        self.assertEqual(validate(j)['calculation']['reason'],'duplicate_or_missing_reward_id')

    def test_multiple_transactions_explicitly_unsupported(self):
        j=deepcopy(self.jobs['E']); j['transactions']=[{'id':'first'},{'id':'second'}]
        self.assertIn('multiple_transactions_not_implemented',validate(j)['issues'])

    def test_negative_boolean_amounts_and_unknown_reward(self):
        for amount in (-1, True, 2.5, None):
            j=deepcopy(self.jobs['E']); j['cart']['coupon']['amount']=amount; evidence_for(j)
            self.assertEqual(validate(j)['calculation']['status'],'hold')
        j=deepcopy(self.jobs['E']); j['cart']['rewards'][0]['amount']=None; evidence_for(j)
        self.assertEqual(validate(j)['calculation']['reason'],'future_reward_unknown')

    def test_causal_performance_claim_rejected(self):
        j=deepcopy(self.jobs['A']); j['performance_claim']='This edit guarantees 1M views'
        self.assertIn('performance_causal_claim_not_supported',validate(j)['issues'])

    def test_long_conditions_retained_without_fixed_duration(self):
        j=deepcopy(self.jobs['A']); j['offers'][0]['exclusions']=['조건'+str(i) for i in range(50)]; evidence_for(j)
        d=draft(j)
        self.assertIn('조건49','\n'.join(l['text'] for l in d['script']))
        self.assertNotIn('duration',d)
        self.assertNotIn('timing',d)

    def test_price_assertion_conflict(self):
        j=deepcopy(self.jobs['A']); j['offers'][0]['claimed_price']=2500; evidence_for(j)
        self.assertIn('offers.0:claimed_price_conflict',validate(j)['issues'])

    def test_every_required_condition_missing_is_held(self):
        from couponz.evidence import COMMON
        for field in COMMON:
            j=deepcopy(self.jobs['A']); del j['offers'][0][field]; evidence_for(j)
            self.assertEqual(validate(j)['status'], 'hold', field)

    def test_missing_evidence_or_unsupported_wording_is_held(self):
        j=deepcopy(self.jobs['A']); j['evidence']=[]
        self.assertEqual(validate(j)['status'], 'hold')
        j=deepcopy(self.jobs['A']); j['offers'][0]['description']='오늘 누구나 무료로 이용할 수 있습니다.'
        self.assertIn('offers.0.description:conflict',validate(j)['issues'])
        self.assertTrue(all(l['status']=='provisional' for l in draft(j)['script']))

    def test_free_cta_cannot_sneak_in_a_savings_claim(self):
        j=deepcopy(self.jobs['B']); j['cta']={'text':'2,000원 절약하고 바로 구매하세요.'}
        d=draft(j)
        self.assertEqual(d['fact_check']['status'],'hold')
        self.assertNotIn('cta',[l['role'] for l in d['script']])

    def test_roundup_theme_requires_evidence(self):
        j=deepcopy(self.jobs['D']); j['theme']='모두 무료인 혜택 세 가지'
        self.assertIn('theme:conflict',validate(j)['issues'])

    def test_unknown_additional_tax_blocks_total(self):
        for ident in ('B','E'):
            j=deepcopy(self.jobs[ident])
            for o in j['offers']: o['tax_included']=False
            evidence_for(j)
            self.assertEqual(validate(j)['calculation']['status'],'hold')
            self.assertEqual(validate(j)['calculation']['reason'],'additional_tax_unknown')
        j=deepcopy(self.jobs['B'])
        for o in j['offers']: o.update(tax_included=False,tax_amount=1000)
        evidence_for(j)
        self.assertEqual(validate(j)['calculation']['baseline'],10900)

    def test_spoken_conditions_include_fees_exclusions_and_cap(self):
        j=deepcopy(self.jobs['A']); j['offers'][0].update(minimum_spend=10000,cap=2000,exclusions=['배달 주문'],mandatory_fees=500); evidence_for(j)
        text='\n'.join(l['text'] for l in draft(j)['script'])
        for expected in ('10,000원','2,000원','배달 주문','500원','2026년 10월 31일','다른 쿠폰 중복 불가'):
            self.assertIn(expected,text)

    def test_no_forced_cta_or_fixed_editorial_defaults(self):
        for ident in 'ABCDE':
            d=draft(self.jobs[ident])
            for key in ('tracks','duration','caption_style','transition','visual_intent','cursor','underline'):
                self.assertNotIn(key,d)
                self.assertTrue(all(key not in l for l in d['script']))
        self.assertNotIn('cta',[l['role'] for l in draft(self.jobs['B'])['script']])

    def test_korean_reward_sentence_and_comparison_repetition(self):
        self.assertNotIn('포인트은', self.text('E'))
        self.assertIn('5,000원 상당의 포인트입니다', self.text('E'))
        conditions=[l for l in draft(self.jobs['B'])['script'] if l['role']=='conditions']
        self.assertEqual(len(conditions),1)
        self.assertIn('공통 조건',conditions[0]['text'])

    def test_no_coordinates_or_timecodes_intake(self):
        result=intake(url='https://example.invalid/offer')
        self.assertFalse(result['user_coordinates_required'])
        self.assertFalse(result['user_timecodes_required'])
        self.assertEqual(result['claims'],[])
        self.assertEqual(result['capabilities']['source_collection'],'NOT IMPLEMENTED')
        with self.assertRaises(NotImplementedError): SourceExtractor().extract(result)
        with self.assertRaises(NotImplementedError): SpeechRecognizer().transcribe('voice.wav')

    def test_cli_end_to_end_five_drafts_and_immutable_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ident in 'ABCDE':
                source=Path(tmp)/f'{ident}.json'; source.write_text(json.dumps(self.jobs[ident]))
                out=Path(tmp)/f'{ident}-draft.json'
                command=[sys.executable,'-m','couponz','draft',str(source),'--out',str(out)]
                proc=subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(proc.returncode,0,proc.stderr)
                self.assertEqual(json.loads(out.read_text())['format'],self.jobs[ident]['format'])
                original=out.read_bytes()
                proc=subprocess.run(command,capture_output=True,text=True)
                self.assertNotEqual(proc.returncode,0)
                self.assertEqual(out.read_bytes(),original)


if __name__=='__main__':
    unittest.main()
