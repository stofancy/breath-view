import json
import struct
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
import numpy as np
from reader import parse_usr, timestamps, index_waveforms, Dataset, packed_date
from storage import import_card, load


def usr_bytes():
    start=0x102340
    body=bytearray(69)
    body[0]=0xe1
    struct.pack_into('<H',body,7,(26<<9)|(9<<5)|11)
    struct.pack_into('<H',body,15,360)
    body+=b'\xff'*5
    for kind,payload in [(0x83,bytes([15,29,17])),(0x84,bytes([16,3,10])),(0x87,bytes([20,7,10]))]:
        body+=struct.pack('<BHH',kind,1,0)+payload
    struct.pack_into('<I',body,1,start+len(body))
    b=bytearray(start)+body
    b[0x2296:0x2296+6]=b'U-20A\0'
    b[0x42e]=0xf4
    struct.pack_into('<H',b,0x431,(26<<9)|(9<<5)|12)
    b[0x441]=255
    struct.pack_into('<I',b,0x102338,1)
    return b


def packet(hour,minute,second,flow=300):
    p=bytearray(256)
    struct.pack_into('<HHHH',p,0,0xaaaa,1,15,20)
    struct.pack_into('<25H',p,108,*([flow]*25))
    struct.pack_into('<H',p,196,123)
    struct.pack_into('<H',p,198,420)
    struct.pack_into('<H',p,202,65)
    struct.pack_into('<H',p,208,15)
    struct.pack_into('<HBBBBBB',p,248,2026,9,12,hour,minute,second,6)
    return p


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.usr=self.root/'test.USR';self.usr.write_bytes(usr_bytes())
    def tearDown(self):self.tmp.cleanup()
    def test_historical_and_current_distinct(self):
        info,days=parse_usr(self.usr)
        self.assertEqual(info['model'],'BMC U-20A')
        self.assertEqual(days['2026-09-11']['minutes'],360)
        self.assertEqual([e['kind'] for e in days['2026-09-11']['events']],['OSA','HYP','CSA'])
        self.assertIsNone(days['2026-09-12']['minutes'])
        self.assertEqual(days['2026-09-11']['events'][0]['second'],55740)
    def test_truncated_rejected(self):
        b=usr_bytes();self.usr.write_bytes(b[:-1])
        with self.assertRaises(ValueError):parse_usr(self.usr)
    def test_cycle_pointer_rejected(self):
        b=usr_bytes();struct.pack_into('<I',b,0x102341,0x102340);self.usr.write_bytes(b)
        with self.assertRaises(ValueError):parse_usr(self.usr)
    def test_unknown_model_rejected(self):
        b=usr_bytes();b[0x2296:0x2296+5]=b'X-99A';self.usr.write_bytes(b)
        with self.assertRaises(ValueError):parse_usr(self.usr)
    def test_invalid_calendar_date(self):
        p=packet(1,2,3);p[250]=2;p[251]=30
        _,good=timestamps(np.frombuffer(p,dtype='u1').reshape(-1,256))
        self.assertFalse(good[0])
    def test_noon_boundary_gaps_duplicates_scaling(self):
        first=packet(12,0,0,flow=300)
        duplicate=packet(12,0,0,flow=400)
        self.assertNotEqual(first,duplicate)
        raw=packet(11,59,59)+first+duplicate+packet(12,0,2)+packet(12,0,8)+bytes(256)
        (self.root/'test.000').write_bytes(raw)
        spans,invalid=index_waveforms(self.root)
        self.assertEqual(set(spans),{'2026-09-11','2026-09-12'});self.assertEqual(invalid,1)
        info,days=parse_usr(self.usr)
        ds=Dataset(self.root,{'days':days,'spans':spans})
        d=ds.detail('2026-09-12',0,10)
        self.assertEqual(d['wave_seconds'],4);self.assertEqual(d['duplicates'],1)
        self.assertEqual(d['segments'],[[0,3],[8,9]])
        self.assertEqual(d['stats']['pressure']['median'],7.5)
        self.assertEqual(d['stats']['epap']['median'],7.5)
        self.assertEqual(d['stats']['ipap']['median'],10.0)
        self.assertEqual(d['series']['pressure'],d['series']['epap'])
        self.assertEqual(d['series']['ipap'][0],[0.,10.])
        self.assertEqual(d['stats']['leak']['median'],12.3)
        self.assertEqual(d['series']['flow'][0],[0.,30.])
        self.assertIn([0.,40.],d['series']['flow'])
        self.assertIn([1,None],d['series']['pressure'])
        self.assertIn([3,None],d['series']['pressure'])
        flow_x=[point[0] for point in d['series']['flow']]
        self.assertEqual(flow_x,sorted(flow_x))
    def test_no_wave_is_empty_not_zero(self):
        info,days=parse_usr(self.usr);ds=Dataset(self.root,{'days':days,'spans':{}})
        self.assertEqual(ds.detail('2026-09-11')['series'],{})
    def test_invalid_window(self):
        (self.root/'test.000').write_bytes(packet(12,0,0))
        spans,_=index_waveforms(self.root);_,days=parse_usr(self.usr)
        with self.assertRaises(ValueError):Dataset(self.root,{'days':days,'spans':spans}).detail('2026-09-12',20,10)
    def test_import_preserves_source_and_previous_on_error(self):
        home=self.root/'archive';before=self.usr.read_bytes()
        first=import_card(self.root,home)
        pointer=(home/'current').read_bytes()
        self.assertEqual(self.usr.read_bytes(),before)
        self.usr.write_bytes(b'invalid')
        with self.assertRaises(ValueError):import_card(self.root,home)
        self.assertEqual((home/'current').read_bytes(),pointer)
        self.assertEqual(len(load(home).days),2)
    def test_summary_event_index(self):
        info,days=parse_usr(self.usr)
        ds=Dataset(self.root,{'days':days,'spans':{}})
        self.assertEqual(ds.overview()['days'][0]['index'],0.5)
        self.assertIsNone(ds.overview()['days'][1]['index'])


class ExportTests(unittest.TestCase):
    def test_export_range_and_current_missing_values(self):
        import threading
        import urllib.request
        import urllib.error
        import csv
        import io
        from types import SimpleNamespace
        from app import serve
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.USR';path.write_bytes(usr_bytes())
            _,days=parse_usr(path)
            app=SimpleNamespace(data=Dataset(temp,{'days':days,'spans':{}}),lock=threading.RLock(),get_context=lambda start,end:{})
            server,url=serve(app)
            try:
                with urllib.request.urlopen(url+'api/export?start=2026-09-12&end=2026-09-12') as response:
                    self.assertIn('attachment;',response.headers['Content-Disposition'])
                    rows=list(csv.reader(io.StringIO(response.read().decode('utf-8-sig'))))
                    self.assertEqual(len(rows),2)
                    self.assertEqual(rows[1][0],'2026-09-12')
                    self.assertEqual(rows[1][1],'')
                    self.assertEqual(rows[1][5],'')
                with urllib.request.urlopen(url+'api/report?start=2026-09-11&end=2026-09-11&locale=en-US') as response:
                    report=json.loads(response.read())
                    self.assertEqual(report['locale'],'en-US')
                    self.assertIn('Average treatment time',report['patient']['detail'])
                with urllib.request.urlopen(url+'api/export?start=2026-09-12&end=2026-09-12&locale=en-US') as response:
                    english_rows=list(csv.reader(io.StringIO(response.read().decode('utf-8-sig'))))
                    self.assertEqual(english_rows[0][0],'Treatment day (starts at noon)')
                    self.assertEqual(english_rows[1][7],'Pending')
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(url+'api/export?start=2026-09-12&end=2026-09-11')
                self.assertEqual(caught.exception.code,400)
                caught.exception.close()
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
