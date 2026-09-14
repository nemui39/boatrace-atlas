import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('exporter',Path(__file__).resolve().parents[1]/'tools/export_live_today.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SourcePriority(unittest.TestCase):
 def test_intermediate_hidden_history_kept_and_no_regression(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);rid='20260914_21_04'
   def put(source,name,obj):
    p=d/source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj));return p
   old=put('union_source_versions/union5_v1_1_source_v1',rid+'.json',{'race_id':rid})
   self.assertEqual(m.completed_union_sources(d,'UNION6'),[])
   final=put('union_source_versions/union6_mid50_100_source_v1',rid+'.json',{'race_id':rid})
   self.assertEqual(m.completed_union_sources(d,'UNION6'),[final])
   old.write_text(json.dumps({'race_id':rid,'generated_at':'newer'}))
   self.assertEqual(m.completed_union_sources(d,'UNION6'),[final])
   hist='20260913_07_09'
   historical=put('union_source_versions/union5_v1_1_source_v1',hist+'.json',{'race_id':hist})
   put('micro_live/union5_v1_1_dispatch',hist+'.json',{'status':'rule_skip'})
   self.assertEqual(m.completed_union_sources(d,'UNION6'),[historical,final])
if __name__=='__main__':unittest.main()
