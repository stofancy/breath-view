"""Atomic local snapshots; the SD card is only ever opened for reading."""
from pathlib import Path
from datetime import datetime
import json, shutil, tempfile, os, hashlib, errno
from reader import parse_usr, index_waveforms, Dataset, VERSION

DEFAULT_HOME = Path.home()/'.local/share/breath-view'


def import_card(source, home=DEFAULT_HOME, progress=lambda x:None):
    source=Path(source).expanduser().resolve()
    home=Path(home).resolve()
    if not source.is_dir():
        raise ValueError('请选择 SD 卡根目录或备份文件夹')
    files=list(source.glob('*.USR'))+list(source.glob('*.usr'))
    if len(files)!=1:
        raise ValueError('文件夹中必须恰好有一个 .USR 文件')
    info, _ = parse_usr(files[0])
    home.mkdir(parents=True,exist_ok=True,mode=0o700)
    stage=Path(tempfile.mkdtemp(prefix='.import-',dir=home))
    try:
        paths=[files[0]]+sorted(source.glob(files[0].stem+'.[0-9][0-9][0-9]'))
        manifest=[]
        for i,p in enumerate(paths):
            progress(f'复制到电脑 {i+1}/{len(paths)} · {p.name}')
            before=p.stat()
            digest=hashlib.sha256()
            unreadable=[]
            with p.open('rb') as src,(stage/p.name).open('wb') as dst:
                offset=0
                while offset<before.st_size:
                    length=min(1024*1024,before.st_size-offset)
                    try:
                        block=src.read(length)
                        if len(block)!=length:raise ValueError('源文件提前结束')
                    except OSError as e:
                        if e.errno!=errno.EIO or p==files[0]:raise
                        # Unreadable 1 MiB chunks become invalid packets, never data.
                        # Do not repeatedly hammer failing SD sectors.
                        unreadable.append([offset,length])
                        progress(f'读取失败，跳过损坏区间 · {p.name} @ {offset}')
                        block=bytes(length)
                        src.seek(offset+length)
                    dst.write(block);digest.update(block)
                    offset+=length
            after=p.stat()
            if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:
                raise ValueError('导入时源文件发生变化，请拔出呼吸机后重新导入')
            manifest.append({'name':p.name,'size':before.st_size,'sha256':digest.hexdigest(),'unreadable_ranges':unreadable})
        info,days=parse_usr(stage/files[0].name)
        spans,invalid=index_waveforms(stage,progress)
        for date in spans:
            days.setdefault(date,{'date':date,'minutes':None,'events':[],'current':True})
        catalog={'version':VERSION,'device':info,'days':days,'spans':spans,'invalid_packets':invalid,
                 'imported_at':datetime.now().isoformat(timespec='seconds'),'source':str(source),'files':manifest}
        (stage/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8')
        # Publish only after all files and decoding succeed. Keep previous snapshot
        # until the pointer switches; failed imports leave the previous one usable.
        name='snapshot-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        target=home/name
        stage.rename(target)
        pointer=home/'current.tmp'
        pointer.write_text(name,encoding='utf-8')
        os.replace(pointer,home/'current')
        return Dataset(target,catalog)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise


def load(home=DEFAULT_HOME):
    home=Path(home)
    if not (home/'current').exists():return None
    folder=home/(home/'current').read_text(encoding='utf-8').strip()
    if folder.parent.resolve()!=home.resolve():raise ValueError('本地数据指针无效')
    catalog=json.loads((folder/'catalog.json').read_text(encoding='utf-8'))
    if catalog['version']!=VERSION:raise ValueError('需要重新导入以更新数据格式')
    return Dataset(folder,catalog)
