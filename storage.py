"""Atomic local snapshots; the SD card is only ever opened for reading."""
from pathlib import Path
from datetime import datetime
import json, shutil, tempfile, os, hashlib, errno
from reader import parse_usr, index_waveforms, Dataset, VERSION

DEFAULT_HOME = Path.home()/'.local/share/breath-view'


def import_card(source, home=DEFAULT_HOME, progress=lambda x:None, source_label=None):
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
            progress(f'保存数据 {i+1}/{len(paths)} · {p.name}')
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
                 'imported_at':datetime.now().isoformat(timespec='seconds'),'source':source_label or str(source),'files':manifest}
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


MAX_ARCHIVE_BYTES = 8 * 1024**3


def import_source(source, home=DEFAULT_HOME, progress=lambda x: None):
    """Accept a card folder, its USR entry, or a ZIP; never extract arbitrary paths."""
    import zipfile, stat, re
    from pathlib import PurePosixPath
    source = Path(source).expanduser().resolve()
    if source.is_dir():
        return import_card(source, home, progress)
    if source.suffix.lower() == '.usr':
        return import_card(source.parent, home, progress)
    if source.suffix.lower() != '.zip':
        raise ValueError('请选择数据文件夹、.USR 文件或 ZIP 压缩包')
    Path(home).mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with zipfile.ZipFile(source) as archive, tempfile.TemporaryDirectory(prefix='.unzip-', dir=home) as temp:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(x.file_size for x in entries) > MAX_ARCHIVE_BYTES:
                raise ValueError('压缩包展开后不能超过 8 GiB 或 10000 个文件')
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('压缩包包含不安全的路径或符号链接')
            users = [x for x in entries if not x.is_dir() and PurePosixPath(x.filename).suffix.lower() == '.usr' and '__MACOSX' not in PurePosixPath(x.filename).parts]
            if len(users) != 1:
                raise ValueError('ZIP 中必须恰好有一个 .USR 文件，请只压缩一张 SD 卡的数据')
            usr = PurePosixPath(users[0].filename)
            selected = [x for x in entries if PurePosixPath(x.filename).parent == usr.parent and (x is users[0] or re.fullmatch(re.escape(usr.stem) + r'\.[0-9]{3}', PurePosixPath(x.filename).name))]
            names = set()
            for i, entry in enumerate(selected):
                name = PurePosixPath(entry.filename).name
                if name.lower() in names:
                    raise ValueError('压缩包包含重复的数据文件')
                names.add(name.lower())
                progress(f'解压 {i+1}/{len(selected)} · {name}')
                with archive.open(entry) as src, (Path(temp)/name).open('wb') as dst:
                    shutil.copyfileobj(src, dst, 1024*1024)
            return import_card(temp, home, progress, source_label=source.name)
    except zipfile.BadZipFile as exc:
        raise ValueError('ZIP 文件损坏或尚未上传完整') from exc
