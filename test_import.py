import tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from storage import import_source

class ImportTests(unittest.TestCase):
    def test_zip_nested_and_selected_files(self):
        with tempfile.TemporaryDirectory() as root:
            z=Path(root)/'card.zip'
            with zipfile.ZipFile(z,'w') as f:
                f.writestr('backup/card/A.USR',b'summary');f.writestr('backup/card/A.000',b'wave');f.writestr('backup/card/unused.log',b'ignored')
            def inspect(folder,*args,**kwargs):
                self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),['A.000','A.USR'])
                self.assertEqual((Path(folder)/'A.000').read_bytes(),b'wave')
                return 'ok'
            with patch('storage.import_card',side_effect=inspect):self.assertEqual(import_source(z,root),'ok')
            self.assertFalse(list(Path(root).glob('.unzip-*')))

    def test_unsafe_or_ambiguous_zip_does_not_import(self):
        for names in [('A.USR','../bad'),('A.USR','other/B.USR'),('no.txt',)]:
            with tempfile.TemporaryDirectory() as root:
                z=Path(root)/'card.zip'
                with zipfile.ZipFile(z,'w') as f:
                    for name in names:f.writestr(name,b'x')
                with patch('storage.import_card') as importer:
                    with self.assertRaises(ValueError):import_source(z,root)
                    importer.assert_not_called()
                self.assertFalse(list(Path(root).glob('.unzip-*')))

    def test_usr_opens_siblings(self):
        with tempfile.TemporaryDirectory() as root:
            usr=Path(root)/'A.USR';usr.write_bytes(b'x')
            with patch('storage.import_card',return_value='ok') as importer:
                self.assertEqual(import_source(usr,root),'ok')
                self.assertEqual(importer.call_args.args[0],Path(root))

if __name__=='__main__':unittest.main()
