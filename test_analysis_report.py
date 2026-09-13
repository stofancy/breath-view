import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from analysis_report import aggregate, build_report, report_html, report_markdown, validate_context
from app import Application
from i18n import normalize_locale
from patient_summary import compare, previous_year
from portable_report import mobile_html


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
        self.assertEqual(a['patient']['assessment']['state'],'limited')
        self.assertIn('自述已填 0/',a['patient']['assessment']['confidence_note'])
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

    def test_patient_advice_prioritizes_symptoms_over_low_device_values(self):
        rows=[row('2026-09-01',360,0)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        from analysis_report import CONTEXT_FIELDS
        clear={key:'no' for key in CONTEXT_FIELDS}
        for field,level in [('unrefreshed','review'),('gasping','review'),('drowsy_driving','priority'),('mask_off','support')]:
            with self.subTest(field=field):
                r=build_report(ds,'2026-09-01','2026-09-01',clear|{field:'yes'})
                self.assertEqual(r['patient']['followup']['level'],level)
                self.assertIsNone(r['patient']['ahi']['value'])
        unknown=build_report(ds,'2026-09-01','2026-09-01')
        self.assertEqual(unknown['context']['sleepiness'],'unknown')
        self.assertEqual(unknown['patient']['followup']['level'],'observe')

    def test_patient_comparison_zero_baseline_missing_and_calendar_alignment(self):
        a={'settled_days':7,'calendar_days':7,'frequency':0,'mean_minutes':360}
        b=a|{'frequency':2,'mean_minutes':300}
        self.assertEqual(compare(b,a)['direction'],'up')
        self.assertIsNone(compare(b,a)['percent'])
        self.assertFalse(compare(a,b|{'settled_days':2})['eligible'])
        self.assertFalse(compare(a,b,overlap=True)['eligible'])
        self.assertEqual(previous_year('2024-02-29'),'2023-02-28')
        # Rising vs previous but falling vs year must remain distinct.
        rows=[row(f'2025-09-{n:02}',360,24) for n in range(1,8)]+[row(f'2026-08-{n:02}',360,6) for n in range(25,32)]+[row(f'2026-09-{n:02}',360,12) for n in range(1,8)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        r=build_report(ds,'2026-09-01','2026-09-07')
        self.assertEqual(r['patient']['comparisons']['previous']['direction'],'up')
        self.assertEqual(r['patient']['comparisons']['year']['direction'],'down')

    def test_mobile_export_escapes_notes_and_keeps_unknowns_and_metric_limits(self):
        rows=[row('2026-09-01',360,0),row('2026-09-02',None,20,True)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        r=build_report(ds,'2026-09-01','2026-09-03',{'note':'<img src=x onerror=alert(1)>健康备注'})
        exported=mobile_html(r)
        self.assertNotIn('<img',exported)
        self.assertIn('&lt;img',exported)
        self.assertIn('未填写',exported)
        self.assertIn('初步',exported)
        self.assertIn('尚未与原厂',exported)
        self.assertNotIn('<script',exported)
        self.assertEqual([p['state'] for p in r['patient']['trend']],['settled','pending','missing'])
        self.assertIsNone(r['patient']['trend'][1]['frequency'])

    def test_english_locale_covers_json_markdown_html_and_mobile_exports(self):
        rows=[row(f'2026-09-{n:02}',360,n) for n in range(1,8)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        report=build_report(ds,'2026-09-01','2026-09-07',{'note':'<script>alert(1)</script>'},locale='en',changes=[{'id':'english-change','date':'2026-09-01','kind':'mask','note':'mask changed'}])
        self.assertEqual(report['locale'],'en-US')
        self.assertEqual(normalize_locale('fr-FR'),'zh-CN')
        self.assertIn('Average treatment time',report['patient']['detail'])
        self.assertEqual(report['treatment_changes'][0]['kind_label'],'Mask replacement')
        self.assertNotIn('平均戴机',str(report))
        markdown=report_markdown(report)
        self.assertTrue(markdown.startswith('# PAP treatment record review\n'))
        self.assertIn('Questions for follow-up',markdown)
        self.assertIn('Patient-recorded treatment changes',markdown)
        rendered=report_html(report)
        self.assertIn('<html lang="en-US">',rendered)
        self.assertNotIn('<script>',rendered)
        self.assertIn('&lt;script&gt;',rendered)
        self.assertIn('Patient-recorded treatment changes',rendered)
        mobile=mobile_html(report)
        self.assertIn('<html lang="en-US">',mobile)
        self.assertIn('Scope and sources',mobile)

    def treatment_periods(self, current_count, previous_count, current_minutes=360, year_count=6):
        rows=[row(f'2025-09-{n:02}',360,year_count) for n in range(1,8)]
        rows += [row(f'2026-08-{n:02}',360,previous_count) for n in range(25,32)]
        rows += [row(f'2026-09-{n:02}',current_minutes,current_count) for n in range(1,8)]
        return SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})

    def test_directional_assessment_without_symptoms_and_conflicting_year_trend(self):
        r=build_report(self.treatment_periods(12,13),'2026-09-01','2026-09-07')
        a=r['patient']['assessment']
        self.assertEqual(a['state'],'stable')
        self.assertIn('略有改善',a['title'])
        self.assertTrue(a['signals']['year_rising'])
        self.assertIn('长期变化',r['patient']['followup']['title'])
        self.assertEqual(r['context']['sleepiness'],'unknown')
        self.assertIn(a['title'],r['summary'])
        self.assertIn(a['title'],mobile_html(r))

    def test_rising_and_high_residual_signals_prompt_action(self):
        # 2 -> 4/h: material rise below the screening line still raises attention.
        r=build_report(self.treatment_periods(24,12),'2026-09-01','2026-09-07')
        self.assertEqual(r['patient']['assessment']['state'],'watch')
        self.assertIn('可能在变差',r['patient']['title'])
        # 18 -> 12/h: decline alone must not produce an improvement reassurance.
        r=build_report(self.treatment_periods(72,108),'2026-09-01','2026-09-07')
        self.assertEqual(r['patient']['assessment']['state'],'review')
        self.assertEqual(r['patient']['followup']['level'],'review')

    def test_declining_events_do_not_hide_short_usage_or_symptoms(self):
        r=build_report(self.treatment_periods(6,60,current_minutes=120),'2026-09-01','2026-09-07')
        self.assertTrue(r['patient']['assessment']['signals']['falling'])
        self.assertEqual(r['patient']['assessment']['state'],'support')
        r=build_report(self.treatment_periods(12,30),'2026-09-01','2026-09-07',{'sleepiness':'yes'})
        self.assertEqual(r['patient']['assessment']['state'],'review')

    def test_zero_use_has_no_favorable_assessment(self):
        r=build_report(self.treatment_periods(0,12,current_minutes=0),'2026-09-01','2026-09-07')
        self.assertIsNone(r['current']['frequency'])
        self.assertEqual(r['patient']['assessment']['state'],'support')

    def test_variability_and_freshness_respect_selected_range(self):
        rows=[row(f'2026-09-{n:02}',360,36 if n in (1,3,5) else 0) for n in range(1,8)]
        rows += [row('2026-09-08',None,100,True),row('2026-09-09',0,100),row('2026-09-10',360,0)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        r=build_report(ds,'2026-09-01','2026-09-09')
        v=r['patient']['variability']
        self.assertEqual((v['evaluable_days'],v['high_days'],v['short_days']),(7,3,1))
        self.assertEqual(v['pattern'],'repeated')
        self.assertEqual(r['patient']['freshness']['selected_through'],'2026-09-09')
        self.assertEqual(r['patient']['freshness']['latest_settled'],'2026-09-10')
        self.assertEqual(len(v['review_dates']),3)

    def test_change_comparison_windows_and_export_escaping(self):
        ds=self.treatment_periods(12,24)
        changes=[{'id':'a','date':'2026-09-01','kind':'mask','note':'<img src=x>更换面罩'},
                 {'id':'b','date':'2026-09-02','kind':'illness','note':'鼻塞'}]
        r=build_report(ds,'2026-09-01','2026-09-07',changes=changes)
        change=next(c for c in r['treatment_changes'] if c['id']=='a')
        comp=change['comparison']
        self.assertTrue(comp['eligible'])
        self.assertEqual(comp['before']['start'],'2026-08-25')
        self.assertEqual(comp['after']['end'],'2026-09-07')
        self.assertEqual(comp['frequency_delta'],-2)
        self.assertEqual(comp['overlapping_changes'],1)
        self.assertIn('不代表因果',comp['text'])
        for exported in (report_html(r),mobile_html(r)):
            self.assertIn('更换面罩',exported)
            self.assertIn('&lt;img',exported)
            self.assertNotIn('<img',exported)
            self.assertIn('2026-08-25',exported)

    def test_change_with_pending_days_does_not_claim_effect(self):
        rows=[row(f'2026-09-{n:02}',360,6) for n in range(1,9)]+[row('2026-09-09',None,30,True)]
        ds=SimpleNamespace(catalog={'device':{'model':'TEST'}},overview=lambda:{'days':rows})
        changes=[{'id':'a','date':'2026-09-08','kind':'clinician','note':''}]
        r=build_report(ds,'2026-09-01','2026-09-09',changes=changes)
        comp=r['treatment_changes'][0]['comparison']
        self.assertFalse(comp['eligible'])
        self.assertEqual(comp['after']['settled_days'],1)
        self.assertIsNone(comp['frequency_delta'])
        self.assertEqual(build_report(ds,'2026-09-01','2026-09-07',changes=changes)['treatment_changes'],[])

if __name__=='__main__':unittest.main()
