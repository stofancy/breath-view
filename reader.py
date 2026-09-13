"""Read-only BMC U-20A decoder. See FORMAT.md for evidence and limitations."""
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
import struct
import numpy as np

VERSION = 1
EVENTS = {0x83: 'OSA', 0x84: 'HYP', 0x87: 'CSA'}

# OSCAR's BMC legacy packet layout identifies byte 0x04 as EPAP and byte 0x06
# as IPAP.  Keep ``pressure`` as the historical API name for the 0x04 channel;
# callers can use the explicit names for new output.  Both raw channels use the
# same /2 scale.  The external channel meaning still needs manufacturer
# verification; see FORMAT.md.
WAVEFORM_FIELDS = {
    'pressure': (2, 2),  # compatibility alias for raw byte 0x04 (EPAP)
    'epap': (2, 2),      # raw byte 0x04
    'ipap': (3, 2),       # raw byte 0x06
    'leak': (98, 10),
    'tidal': (99, 1),
    'ventilation': (101, 10),
    'rate': (104, 1),
}


def packed_date(n):
    return datetime(2000 + (n >> 9), (n >> 5) & 15, n & 31, 12)


def u16(b, p):
    return struct.unpack_from('<H', b, p)[0]


def u32(b, p):
    return struct.unpack_from('<I', b, p)[0]


def event(kind, payload):
    h, m, duration = payload
    if h >= 24 or m >= 60 or duration == 0:
        raise ValueError('呼吸事件的时间或时长无效')
    return {'kind': kind, 'second': h * 3600 + m * 60, 'duration': duration}


def parse_usr(path):
    b = Path(path).read_bytes()
    if len(b) < 0x102340 or b[0x42e] != 0xf4:
        raise ValueError('不是已支持的 BMC USR 格式')
    def string_at(p, size):
        return b[p:p+size].split(b'\0')[0].decode('ascii', errors='replace').strip()
    model = string_at(0x2296, 12)
    # Deliberately refuse unknown variants rather than assign U-20A meanings to them.
    if model != 'U-20A':
        raise ValueError(f'当前仅验证 BMC U-20A，检测到型号：{model}')
    info = {'model': 'BMC ' + model, 'serial': string_at(0x2d, 32)}
    days = {}
    p = 0x102340
    expected = u32(b, 0x102338)
    for _ in range(expected):
        if p + 69 > len(b) or b[p] != 0xe1:
            raise ValueError(f'历史摘要损坏，位置 {p:#x}')
        end = u32(b, p+1)
        if not p + 69 <= end <= len(b):
            raise ValueError('历史摘要指针越界')
        day = packed_date(u16(b, p+7)).strftime('%Y-%m-%d')
        duration = u16(b, p+15)
        if duration > 1440:
            raise ValueError('历史使用时长超过一天')
        q = p+69
        while q+5 <= end and b[q:q+5] != b'\xff'*5:
            q += 5
        if q+5 > end:
            raise ValueError('摘要索引终止符缺失')
        q += 5
        events = []
        while q < end:
            if q+5 > end:
                raise ValueError('摘要消息头被截断')
            kind, count, reserved = struct.unpack_from('<BHH', b, q)
            if not 0x80 <= kind <= 0x8f or reserved != 0:
                raise ValueError('未知摘要消息结构')
            width = 4 if kind in (0x82, 0x86) else 3 if kind in EVENTS else 2
            q += 5
            if q + count*width > end:
                raise ValueError('摘要消息内容被截断')
            if kind in EVENTS:
                events.extend(event(EVENTS[kind], b[i:i+3]) for i in range(q, q+count*3, 3))
            q += count*width
        if day in days:
            raise ValueError('重复的历史治疗日')
        days[day] = {'date': day, 'minutes': duration, 'events': sorted(events, key=lambda e:e['second']), 'current': False}
        p = end
    if p != len(b):
        raise ValueError('历史记录数量与文件长度不一致')
    # Current noon-to-noon record has no verified duration field. Never infer usage
    # from the gap between first and last sample; use retained packet coverage only.
    day = packed_date(u16(b, 0x431)).strftime('%Y-%m-%d')
    q = 0x441
    events = []
    while q < 0x2242 and b[q] != 255:
        kind = b[q]
        q += 1
        size = 3 if kind == 2 else b[q]
        q += kind != 2
        if q+size > 0x2242:
            raise ValueError('当前治疗日消息越界')
        if kind in (7, 8, 9):
            if size != 3:
                raise ValueError('当前治疗日事件长度无效')
            events.append(event({7:'CSA', 8:'OSA', 9:'HYP'}[kind], b[q:q+size]))
        q += size
    if q >= 0x2242:
        raise ValueError('当前治疗日终止符缺失')
    if day not in days:
        days[day] = {'date': day, 'minutes': None, 'events': sorted(events, key=lambda e:e['second']), 'current': True}
    return info, days


def timestamps(a):
    """Seconds on a naive device-clock axis, with no host timezone conversion."""
    y = a[:,248].astype('i4') + a[:,249].astype('i4')*256
    m, d, h, mi, s = [a[:,i].astype('i4') for i in range(250,255)]
    good = (a[:,0] == 170) & (a[:,1] == 170) & (y>=2000) & (y<=2099) & (m>=1) & (m<=12) & (d>=1) & (d<=31) & (h<24) & (mi<60) & (s<60)
    ts = np.zeros(len(a), dtype='i8')
    # Only ~days-per-file Python iterations, never per-packet datetime parsing.
    keys = y*10000+m*100+d
    for key in np.unique(keys[good]):
        match = good & (keys == key)
        try:
            date = datetime(int(key//10000), int(key//100%100), int(key%100))
        except ValueError:
            good[match] = False
            continue
        base = int((date-datetime(1970,1,1)).total_seconds())
        ts[match] = base + h[match]*3600 + mi[match]*60 + s[match]
    return ts, good


def index_waveforms(folder, progress=lambda x:None):
    spans = {}
    invalid = 0
    paths = sorted(Path(folder).glob('*.[0-9][0-9][0-9]'))
    for i, path in enumerate(paths):
        progress(f'解析波形 {i+1}/{len(paths)} · {path.suffix}')
        size = path.stat().st_size
        invalid += int(size % 256 != 0)
        if size < 256:
            continue
        a = np.memmap(path, dtype='u1', mode='r', shape=(size//256,256))
        ts, good = timestamps(a)
        invalid += int((~good).sum())
        keys = (ts-43200)//86400
        keys[~good] = -999999
        cuts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1])+1, len(keys)]
        for start,end in zip(cuts[:-1],cuts[1:]):
            if keys[start] == -999999:
                continue
            day = (datetime(1970,1,1)+timedelta(days=int(keys[start]))).strftime('%Y-%m-%d')
            spans.setdefault(day,[]).append([path.name,int(start),int(end)])
        del a
    return spans, invalid


class Dataset:
    def __init__(self, folder, catalog):
        self.folder = Path(folder)
        self.catalog = catalog
        self.days = catalog['days']
        self._cache_key = None
        self._cache = None

    def packets(self, day):
        if day == self._cache_key:
            return self._cache
        parts = []
        for name,start,end in self.catalog['spans'].get(day,[]):
            with (self.folder/name).open('rb') as f:
                f.seek(start*256)
                raw = f.read((end-start)*256)
            if len(raw) != (end-start)*256:
                raise ValueError('本地波形文件被截断，请重新导入')
            parts.append(np.frombuffer(raw,dtype='u1').reshape(-1,256))
        if not parts:
            return np.empty((0,256),dtype='u1'),np.array([],dtype='i8'),0
        a = np.concatenate(parts)
        ts, valid = timestamps(a)
        a,ts = a[valid],ts[valid]
        # BMC packets are nominally one second each, but the device can emit
        # adjacent packets with the same timestamp (and occasional +2 s
        # steps).  Keep every valid packet: collapsing equal timestamps loses
        # waveform samples and makes the +2 s steps look like session breaks.
        # Stable sorting keeps file order for equal timestamps while retaining
        # the existing chronological ordering across file spans.
        order = np.argsort(ts, kind='stable')
        a,ts = a[order],ts[order]
        duplicates = len(ts)-len(np.unique(ts))
        self._cache_key, self._cache = day,(a,ts,duplicates)
        return self._cache

    def overview(self):
        rows=[]
        for key,d in sorted(self.days.items()):
            counts = Counter(e['kind'] for e in d['events'])
            mins = d['minutes']
            rows.append({'date':key,'minutes':mins,'current':d['current'],
                         'counts':{k:counts[k] for k in ('OSA','CSA','HYP')},
                         'index':round(len(d['events'])/(mins/60),2) if mins and not d['current'] else None,
                         'wave':key in self.catalog['spans']})
        return {k:v for k,v in self.catalog.items() if k not in ('days','spans')} | {'days':rows}

    def detail(self, day, start=None, end=None):
        if day not in self.days:
            raise ValueError('没有这个治疗日')
        a,ts,duplicates = self.packets(day)
        d = dict(self.days[day])
        base = int((datetime.fromisoformat(day)-datetime(1970,1,1)).total_seconds())+43200
        seconds = ts-base
        d.update({'wave_seconds':len(a), 'duplicates':duplicates, 'series':{}, 'segments':[], 'stats':{}})
        if not len(a):
            return d
        # OSCAR's legacy loader starts a new waveform session only after a
        # forward gap of at least five seconds.  Equal timestamps and normal
        # two-second device steps therefore remain in the same segment.
        split = np.r_[0, np.flatnonzero(np.diff(ts)>=5)+1,len(ts)]
        d['segments'] = [[int(seconds[i]),int(seconds[j-1]+1)] for i,j in zip(split[:-1],split[1:])]
        # All units below are documented mappings; pressure sensor ADC is not
        # mislabeled as cmH2O. No guessed SpO2, snore or sleep-stage output.
        words = a.copy().view('<u2').reshape(-1,128)
        for name,(offset,scale) in WAVEFORM_FIELDS.items():
            values = words[:,offset].astype(float)/scale
            # 0xffff is a missing value, never a physiologic measurement.
            values[words[:,offset] == 65535] = np.nan
            if np.isfinite(values).any():
                d['stats'][name] = {'median':round(float(np.nanmedian(values)),2),'p95':round(float(np.nanpercentile(values,95)),2)}
        lo = max(0,float(start)) if start is not None else max(0,int(seconds[0])-60)
        hi = min(86400,float(end)) if end is not None else min(86400,int(seconds[-1])+60)
        if not 0 <= lo < hi <= 86400:
            raise ValueError('无效时间范围')
        d['range'] = [lo,hi]
        select = (seconds>=lo)&(seconds<=hi)
        w,st = words[select],seconds[select]
        # Plot gaps are a property of the packet timeline, not the coarser
        # five-second session segmentation above.  A +2 s packet step leaves
        # one unobserved second even though OSCAR keeps it in one session.
        plot_boundaries = (st[:-1][np.diff(st)>1] + 1).astype(float).tolist()
        def reduce_points(x,y,limit=2200,boundaries=()):
            """Min/max envelope preserves extrema. Gaps remain explicit nulls."""
            if len(x)==0:
                return []
            if len(x)>limit:
                width=int(np.ceil(len(x)/(limit//2)))
                ids=[]
                for i in range(0,len(x),width):
                    vals=y[i:i+width]
                    if np.isfinite(vals).any():
                        ids.extend(sorted(set([i+int(np.nanargmin(vals)),i+int(np.nanargmax(vals))])))
                    else:ids.append(i)
                # Keep points on both sides of every real missing-data interval.
                gaps=np.flatnonzero(np.diff(x)>1)
                ids=np.unique(np.r_[ids,gaps,gaps+1,0,len(x)-1]).astype(int)
                x,y=x[ids],y[ids]
            out=[]
            # Do not infer a gap from downsampling; use original packet times.
            j=0
            for xx,yy in zip(x,y):
                while j<len(boundaries) and boundaries[j]<=xx:
                    if out:out.append([boundaries[j],None])
                    j+=1
                out.append([round(float(xx),3),round(float(yy),2) if np.isfinite(yy) else None])
            return out
        for name,(offset,scale) in WAVEFORM_FIELDS.items():
            v=w[:,offset].astype(float)/scale
            v[w[:,offset]==65535]=np.nan
            d['series'][name]=reduce_points(st,v,boundaries=plot_boundaries)
        if len(w):
            x=(st[:,None]+np.arange(25)/25).ravel()
            # The documented BMC channel is unsigned total flow; do not subtract
            # an invented baseline to turn it into patient flow.
            v=w[:,54:79].astype(float).ravel()/10
            v[w[:,54:79].ravel()==65535]=np.nan
            # Equal-timestamp packets contain distinct samples on the same
            # one-second interval.  Sorting the expanded points prevents the
            # second packet from drawing a backwards line (e.g. 0.96 -> 0.0).
            order=np.argsort(x,kind='stable')
            d['series']['flow']=reduce_points(x[order],v[order],boundaries=plot_boundaries)
        return d
