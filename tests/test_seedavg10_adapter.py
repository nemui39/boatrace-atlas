import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('exporter',Path(__file__).resolve().parents[1]/'tools/export_live_today.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SeedAvgAdapter(unittest.TestCase):
 def test_probability_ev_and_actual_stake(self):
  odds=[10.04]*120;prob=[1/120]*120;prob[1]=0.02;prob[0]=1/120-0.02+1/120
  d={'contract':'m1_seedavg_family_shadow_v1','race_id':'20260926_01_01','rule':'family_ev1.10_cap300','forward_eligible':True,
     'odds_120':odds,'p_clip_120':prob,'win6_p':[.5,.1,.1,.1,.1,.1],
     'bets_flat100_reference':[{'idx120':1,'kumi':'124','odds':10.0,'p':0.02,'ev':0.2,'flat100_reference_yen':100}]}
  out=m.adapt_seedavg10(dict(d),{'bets_final':[{'kumi':'124','stake':300}],'plan':{'target':37500,'wealth_start':500000}})
  self.assertEqual(out['kumi_order_120'][:2],['123','124'])
  self.assertAlmostEqual(out['ev_120'][1],0.02*10.0)
  self.assertEqual(out['bets_final'][0]['stake'],300)
  self.assertEqual(out['_strategy_label'],'SEEDAVG10')
  self.assertEqual([a['key'] for a in out['_union3_arms']],['seedavg10','market'])
  no_adm=m.adapt_seedavg10(dict(d))
  self.assertEqual(no_adm['bets_final'][0]['stake'],100)
 def test_reference_candidates_are_not_planned_bets_in_multi_leg_modes(self):
  d={'contract':'m1_seedavg_family_shadow_v1','race_id':'20261116_03_06','odds_120':[10.04]*120,'p_clip_120':[1/120]*120,
     'bets_flat100_reference':[{'idx120':1,'kumi':'124','odds':10.0,'p':0.12,'ev':1.2,'flat100_reference_yen':100}]}
  old=m.SEEDAVG_LABEL
  try:
   self.assertFalse(m.adapt_seedavg10(dict(d))['_reference_only'])
   m.SEEDAVG_LABEL='LIVE v4'
   self.assertTrue(m.adapt_seedavg10(dict(d))['_reference_only'])
   adm={'contract':'live_a_i30_predprice_refill_live_admission_v4','bets_final':[{'kumi':'135','odds':20.0,'ev':1.2,'p_model':0.06,'stake':300}]}
   out=m.adapt_seedavg10(dict(d),adm);self.assertFalse(out.get('_reference_only'));self.assertEqual(out['bets_final'][0]['kumi'],'135')
  finally:m.SEEDAVG_LABEL=old
 def test_other_contract_untouched(self):
  d={'contract':'union6_mid50_100_source_v1'};self.assertIs(m.adapt_seedavg10(d),d)
if __name__=='__main__':unittest.main()
