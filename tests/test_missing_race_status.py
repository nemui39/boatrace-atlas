import importlib.util,json,os,tempfile,unittest,datetime
from pathlib import Path
spec=importlib.util.spec_from_file_location('export_missing',os.environ.get('EXPORTER_TEST_PATH',str(Path(__file__).resolve().parents[1]/'tools/export_live_today.py')))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MissingRaceStatus(unittest.TestCase):
 def test_withdrawal_is_visible_without_predictions_or_money(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rid='20261022_14_04';sc={'hd':'20261022','jcd':'14','rno':4,'deadline':'09:55','venue_name':'鳴門'}
   f=p/'beforeinfo_status/venue_14_race_04_beforeinfo.json';f.parent.mkdir()
   bi={'dataheader':{'datakey':{'hd':'20261022','jcd':'14','rno':4}},'maindata':{'teiinfolist':[{'teino':'1','absentflag':'0'},{'teino':'4','absentflag':1}]}}
   f.write_text(json.dumps(bi));now=datetime.datetime(2026,10,22,10)
   def rows(existing=(),receipts=None,at=now):return m.missing_race_rows(existing,{rid:sc},p,[m.SEEDAVG_ENGINE],receipts or {},at)
   row=rows()[0];self.assertEqual(row['absent_boats'],[4]);self.assertEqual(row['verdict'],'withdrawal_skip');self.assertTrue(row['status_only']);self.assertEqual(row['bets'],[]);self.assertIsNone(row['pnl']);self.assertEqual(row['detail'],{})
   self.assertEqual(rows(at=datetime.datetime(2026,10,22,9)),[])
   self.assertEqual(rows(existing=[{'id':rid,'eng':m.SEEDAVG_ENGINE}]),[])
   self.assertEqual(rows(receipts={(m.SEEDAVG_ENGINE,rid):{'123':100}}),[])
   bi['dataheader']['datakey']['hd']='20261021';f.write_text(json.dumps(bi));self.assertEqual(rows()[0]['verdict'],'missing_processing_record')
   f.unlink();self.assertEqual(rows()[0]['absent_boats'],[])
if __name__=='__main__':unittest.main()
