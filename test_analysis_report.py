import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from analysis_report import aggregate, build_report, report_html, validate_context
from app import Application


def row(day,minutes,osa=0,current=False):
    return {'date':day,'minutes':minutes,'current':current,'counts':{'OSA':osa,'CSA':0,'HYP':0},'wave':False,'index':osa/(minutes/60) if minutes else None}

class AnalysisTests(unittest.TestCase):
    def test_weighted_rates_missing_and_pending(self):
        rows=[row('2026-09-01',60,10),row('2026-09-02',540,0),row('2026-09-03',None,20,True)]
        a=aggregate(rows,'2026-09-01','2026-09-04')
        self.assertEqual(a['frequency'],1) # Not mean(10,0)=5 and not 30/10=3.
        self.assertEqual(a['mean_minutes'],300)
        self.assertEqual((a['settled_days'],a['missing_days'],a['pending_days']),(2,1,1))
    def test_no_clinical_clearance_and_context_changes_action(self):
        rows=[row('2026-09-01',360,0)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        a=build_report(ds,'2026-09-01','2026-09-01')
        self.assertFalse(a['comparison']['eligible'])
        self.assertIn('缺少完整症状',a['summary'])
        self.assertNotIn('persistent_symptoms',[f['id'] for f in a['findings']])
        b=build_report(ds,'2026-09-01','2026-09-01',{'sleepiness':'yes','note':'<script>alert(1)</script>'})
        self.assertIn('persistent_symptoms',[f['id'] for f in b['findings']])
        self.assertNotIn('<script>',report_html(b))
        self.assertIn('&lt;script&gt;',report_html(b))
    def test_context_scoped_persistence_and_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Application(temp);app.data=SimpleNamespace(catalog={'device':{'serial':'TEST'}})
            app.save_context('2026-09-01','2026-09-02',{'mask_off':'yes','sleep_hours':7})
            self.assertEqual(app.get_context('2026-09-01','2026-09-02')['mask_off'],'yes')
            self.assertEqual(app.get_context('2026-09-03','2026-09-04'),{})
            self.assertEqual((Path(temp)/'patient-contexts.json').stat().st_mode&0o777,0o600)
        for value in [float('nan'),float('inf'),0,25]:
            with self.assertRaises(ValueError):validate_context({'sleep_hours':value})

if __name__=='__main__':unittest.main()
