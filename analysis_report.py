"""Evidence-linked review summaries, not an automated diagnosis or titration engine."""
from datetime import date, datetime, timedelta
from statistics import median
import math
import html
from i18n import COMPARISON_RULE_EN, CONTEXT_FIELDS_EN, QUESTIONS_EN, SOURCES_EN, normalize_locale

RULE_VERSION = '2.1'
SOURCES = [
    {'id':'NIH-LIVING','title':'NIH · 睡眠呼吸暂停随访与困倦驾驶','url':'https://www.nhlbi.nih.gov/health/sleep-apnea/living-with'},
    {'id':'NIH-AHI','title':'MedlinePlus · 睡眠监测与 AHI 的含义','url':'https://medlineplus.gov/ency/article/003932.htm'},
    {'id':'AASM2021','title':'AASM 2021 · OSA 长期管理与复查睡眠监测','url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC8314660/'},
    {'id':'ATS2013','title':'ATS 2013 · PAP 使用记录、残余事件与漏气的解释','url':'https://www.thoracic.org/statements/resources/sleep-medicine/CPAP-Adherence-Tracking-Systems.pdf'},
    {'id':'ATS-PAP','title':'ATS · 成人 OSA 的 PAP 治疗与全睡眠时段使用','url':'https://site.thoracic.org/advocacy-patients/patient-resources/positive-airway-pressure-cpap-and-bpap-for-adults-with-obstructive-sleep-apnea'},
    {'id':'ATS-MASK','title':'ATS · PAP 面罩与使用问题的处理','url':'https://site.thoracic.org/advocacy-patients/patient-resources/pap-therapy-quick-tips-for-troubleshooting-to-address-problems-with-use'},
]
CONTEXT_FIELDS = {
    'unrefreshed':'睡醒后经常仍不解乏',
    'sleepiness':'白天困倦持续或加重',
    'mask_problem':'面罩漏气、噪声或口鼻干燥影响使用',
    'mask_off':'睡眠中摘机或醒后未重新戴机',
    'gasping':'戴机后仍反复憋醒或被发现呼吸暂停',
    'drowsy_driving':'开车或操作设备时困得难以保持清醒',
}


def period(start,end):
    lo,hi=date.fromisoformat(start),date.fromisoformat(end)
    if lo>hi:raise ValueError('开始日期晚于结束日期')
    if (hi-lo).days>3660:raise ValueError('分析期间不能超过十年')
    return lo,hi


def validate_context(value):
    if not isinstance(value,dict):raise ValueError('自述内容格式无效')
    result={}
    for key in CONTEXT_FIELDS:
        item=value.get(key,'unknown')
        if item not in ('unknown','yes','no'):raise ValueError('自述选项无效')
        result[key]=item
    hours=value.get('sleep_hours')
    if hours is not None and hours!='':
        if isinstance(hours,bool):raise ValueError('睡眠时长必须是小时数')
        hours=float(hours)
        if not math.isfinite(hours) or not 0<hours<=24:raise ValueError('自报睡眠时长需大于 0 且不超过 24 小时')
    else:hours=None
    result['sleep_hours']=hours
    note=value.get('note','')
    if not isinstance(note,str) or len(note)>2000:raise ValueError('备注最多 2000 字')
    result['note']=note.strip()
    return result


def aggregate(rows,start,end):
    lo,hi=period(start,end)
    selected=[row for row in rows if start<=row['date']<=end]
    settled=[r for r in selected if r['minutes'] is not None and not r['current']]
    # Rates need positive exposure. A zero-duration day never contributes its
    # event count to the numerator without a corresponding denominator.
    rate_rows=[r for r in settled if r['minutes']>0]
    counts={kind:sum(r['counts'][kind] for r in rate_rows) for kind in ('OSA','CSA','HYP')}
    total=sum(r['minutes'] for r in settled)
    n=(hi-lo).days+1
    return {'start':start,'end':end,'calendar_days':n,'record_days':len(selected),'settled_days':len(settled),
            'pending_days':len(selected)-len(settled),'missing_days':n-len(selected),
            'use_days':sum(r['minutes']>0 for r in settled),'total_minutes':total,
            'mean_minutes':total/len(settled) if settled else None,
            'median_minutes':median([r['minutes'] for r in settled]) if settled else None,
            'under4_days':sum(r['minutes']<240 for r in settled),
            'wave_days':sum(r['wave'] for r in selected),'counts':counts,
            'frequency':sum(counts.values())/(total/60) if total>0 else None,
            'zero_duration_event_days':sum(r['minutes']==0 and sum(r['counts'].values())>0 for r in settled),
            'type_rates':{kind:count/(total/60) if total>0 else None for kind,count in counts.items()}}


def minutes(value, locale='zh-CN'):
    if value is None:return 'No usable summary' if normalize_locale(locale) == 'en-US' else '无可用摘要'
    rounded=round(value)
    return f'{rounded//60} h {rounded%60} min' if normalize_locale(locale) == 'en-US' else f'{rounded//60} 小时 {rounded%60} 分'


def number(value,digits=2):return '—' if value is None else f'{value:.{digits}f}'


def build_report(dataset,start,end,context=None,locale='zh-CN'):
    locale = normalize_locale(locale)
    lo,hi=period(start,end)
    rows=dataset.overview()['days']
    current=aggregate(rows,start,end)
    length=(hi-lo).days+1
    previous=aggregate(rows,(lo-timedelta(days=length)).isoformat(),(lo-timedelta(days=1)).isoformat())
    context=validate_context(context or {})
    findings=[]
    def finding(id,title,observed,meaning,action,refs=(),evidence=()):
        findings.append({'id':id,'title':title,'observed':observed,'meaning':meaning,'action':action,'refs':list(refs),'evidence':list(evidence)})
    selected=[r for r in rows if start<=r['date']<=end]
    settled=[r for r in selected if r['minutes'] is not None and not r['current']]
    report={'version':RULE_VERSION,'locale':locale,'generated_at':datetime.now().isoformat(timespec='seconds'),
            'device':dataset.catalog.get('device',{}),'imported_at':dataset.catalog.get('imported_at'),
            'current':current,'previous':previous,'context':context,'findings':findings,'sources':SOURCES}
    if not settled:
        finding('no_summary','无法评价这段期间的用机与事件趋势',
                f"{length} 天中没有已结算摘要；{current['pending_days']} 天未结算，{current['missing_days']} 天无记录。",
                '没有摘要不等于没有使用；波形时长也不等于实际睡眠时长。',
                '先补充设备记录或选择已有历史摘要的期间。')
    else:
        finding('usage','已确认的用机情况',
                f"{length} 天中有 {current['settled_days']} 天已结算摘要，其中 {current['use_days']} 天记录到使用；总计 {minutes(current['total_minutes'])}，记录日平均 {minutes(current['mean_minutes'])}。",
                f"{current['under4_days']} 个已结算日少于 4 小时；4 小时只是描述分档，不代表足够治疗，也不评价整夜是否覆盖。",
                '与实际入睡、起床和午睡时段核对，确认是否在所有睡眠时段使用；若摘机或不适影响使用，先处理影响佩戴的问题。',
                ('ATS-PAP',))
        finding('events','呼吸事件水平与后续关注',
                f"共 {sum(current['counts'].values())} 条事件记录，按使用时间加权为 {number(current['frequency'])} 条目/小时；OSA {current['counts']['OSA']}、CSA {current['counts']['CSA']}、HYP {current['counts']['HYP']}。",
                '这些是设备条目，可能按分钟聚合；没有脑电睡眠时间和独立血氧数据，不能换算为已验证的临床 AHI，也不能据此排除残余睡眠呼吸问题。',
                '复诊时将事件较集中的日期与症状、原厂报告和相应波形一起核对。需要复查睡眠监测与否由医生结合持续症状及无法解释的设备数据判断。',
                ('ATS2013','AASM2021'))
    # Transparent engineering gate for descriptive comparison; no clinical cutoff.
    comparable=all(p['settled_days']>=7 and p['settled_days']/p['calendar_days']>=0.7 for p in (current,previous))
    report['comparison']={'eligible':comparable,'rule':'两期间各至少 7 个已结算日且覆盖率 ≥70%，才生成自动比较文字；这是数据充分性规则，不是医疗阈值。'}
    if comparable:
        change=current['mean_minutes']-previous['mean_minutes']
        rate_change=current['frequency']-previous['frequency'] if current['frequency'] is not None and previous['frequency'] is not None else None
        report['comparison'].update({'minutes_change':change,'frequency_change':rate_change})
        rate_text=f"；事件条目频率从 {number(previous['frequency'])} 到 {number(current['frequency'])} /h" if rate_change is not None else ''
        finding('comparison','与前一等长期间相比',
                f"记录日平均用机从 {minutes(previous['mean_minutes'])} 到 {minutes(current['mean_minutes'])}（{'增加' if change>=0 else '减少'} {abs(change):.0f} 分钟）{rate_text}。",
                f"对照期间为 {previous['start']} 至 {previous['end']}；两期间摘要分别 {previous['settled_days']} / {current['settled_days']} 天。差值为描述性比较，不证明病情改善、恶化或某次调压有效。",
                '如变化与更换面罩、体位、作息或医生调整治疗时间一致，在备注中记录日期，供复诊核对。')
    else:
        finding('comparison_limited','本次不生成前后变化结论',
                f"当前期间 {current['settled_days']}/{length} 天有已结算摘要；前一期间 {previous['settled_days']}/{length} 天。",
                report['comparison']['rule'], '可选择更完整的期间；表中的原始汇总仍可逐项查看。')
    unreadable=sum(sum(r[1] for r in f.get('unreadable_ranges',[])) for f in dataset.catalog.get('files',[]))
    finding('quality','结论的证据覆盖范围',
            f"期间内 {current['wave_days']} / {length} 天有保留波形，{current['missing_days']} 天无摘要，{current['pending_days']} 天未结算。" + (f"当前整个导入快照有 {unreadable/1024/1024:.0f} MiB 文件读取缺口（无法可靠归属到具体日期）。" if unreadable else ''),
            '摘要完整与波形完整是两回事；少量留存波形不能代表整个期间。压力、漏气通道语义仍未与原厂逐项核对。',
            '优先保留原卡和本地副本，复诊携带原厂报告或睡眠监测报告，核对设备时间与缺失记录。')
    # Rank records for human review. No "abnormal" label or made-up diagnostic score.
    candidates=[]
    positive=[r for r in settled if r['minutes']>0]
    def add_candidate(row,reason):
        item=next((c for c in candidates if c['date']==row['date']),None)
        if item:item['reasons'].append(reason)
        else:candidates.append({'date':row['date'],'minutes':row['minutes'],'frequency':row['index'],'counts':row['counts'],'wave':row['wave'],'reasons':[reason]})
    for row in sorted(positive,key=lambda r:sum(r['counts'].values())/r['minutes'],reverse=True)[:3]:
        if sum(row['counts'].values())>0:add_candidate(row,'本期间事件条目频率排序靠前')
    for row in sorted([r for r in settled if r['minutes']<240],key=lambda r:r['minutes'])[:2]:add_candidate(row,'设备使用记录少于 4 小时')
    csa=max(positive,key=lambda r:r['counts']['CSA']/r['minutes'],default=None)
    if csa and csa['counts']['CSA']>0:add_candidate(csa,'本期间 CSA 条目频率最高，需核对原厂类型')
    report['review_days']=candidates
    # Read only up to three selected days; report the sampling explicitly.
    wave_reviews=[]
    for candidate in [c for c in candidates if c['wave']][:3]:
        try:
            d=dataset.detail(candidate['date'])
            gaps=[{'start':a[1],'end':b[0],'minutes':(b[0]-a[1])/60} for a,b in zip(d['segments'][:-1],d['segments'][1:]) if b[0]-a[1]>=300]
            covered_events=sum(any(a<e['second']+60 and b>e['second'] for a,b in d['segments']) for e in d['events'])
            wave_reviews.append({'date':candidate['date'],'wave_seconds':d['wave_seconds'],
                'summary_minutes':candidate['minutes'],'coverage':d['wave_seconds']/(candidate['minutes']*60) if candidate['minutes'] else None,
                'segments':len(d['segments']),'gaps':gaps,'events_with_wave':covered_events,'events':len(d['events']),
                'stats':d['stats'],'duplicates':d['duplicates']})
        except (ValueError,OSError) as error:
            wave_reviews.append({'date':candidate['date'],'error':str(error)})
    report['wave_reviews']=wave_reviews
    if wave_reviews:
        finding('wave_review','已准备重点日期的波形复核资料',
                f"按事件条目频率和短用机记录筛选，仅细看 {len(wave_reviews)} 个有波形日期；逐日列出波形覆盖、压力/漏气分位数、长于 5 分钟的无记录间隔和事件附近是否有数据。",
                '5 分钟用于导航，不代表觉醒标准。记录间隔不等于醒来或摘机；压力/漏气变化与事件共现也不证明因果。',
                '点击日期进入同步波形，结合当晚自述与原厂事件标注，核对事件识别、面罩问题和治疗设置。',('ATS2013',))
    answered=any(context[k]!='unknown' for k in CONTEXT_FIELDS) or context['sleep_hours'] is not None or bool(context['note'])
    report['context_complete']=all(context[k]!='unknown' for k in CONTEXT_FIELDS)
    if not answered:
        finding('context_missing','补充感受可进一步完善判断',
                '尚未填写本期间的白天困倦、面罩问题、摘机情况和自报睡眠时长。',
                '当前先给出基于设备记录的治疗方向，睡醒感受可帮助区分数字改善与实际恢复。',
                '补充下方本期间自述；若症状持续或再次出现，携带报告与睡眠医生讨论随访评估。',('AASM2021',))
    if context['sleep_hours'] and current['mean_minutes'] is not None:
        diff=context['sleep_hours']*60-current['mean_minutes']
        finding('sleep_coverage','用机时长与自报睡眠时长的核对',
                f"自报平均睡眠 {minutes(context['sleep_hours']*60)}；设备记录日平均使用 {minutes(current['mean_minutes'])}，两者相差 {abs(diff):.0f} 分钟（{'睡眠更长' if diff>0 else '用机更长或相等'}）。",
                '两个平均值的统计口径不同；包含清醒戴机、午睡或记忆误差的可能，不能把差值当成确切的未治疗睡眠时间。',
                '记录一周入睡、起床、午睡和摘机时刻，并核对是否有睡着后未使用设备的时段。',('ATS-PAP',))
    if context['sleepiness']=='yes':
        finding('persistent_symptoms','建议与睡眠医生复核持续困倦',
                '本期间自述：白天困倦持续或加重。',
                '即使设备事件条目频率不高，也不能据此排除治疗不足或其他导致困倦的因素。',
                '携带本报告联系睡眠门诊；先核对总睡眠时长、整夜佩戴、面罩和原厂残余事件数据，再由医生判断是否需要进一步评估或复查睡眠监测。',('AASM2021',))
    if context['mask_problem']=='yes':
        finding('mask_issue','优先处理影响使用的面罩问题',
                '本期间自述：面罩漏气、噪声或口鼻干燥影响使用。',
                '本软件的漏气通道尚未验证，低读数不能否定实际不适。',
                '联系设备服务人员或睡眠门诊检查面罩贴合和管路牵拉，记录不适发生时刻供波形对照；治疗压力的改变交由医生评估。',('ATS-MASK',))
    if context['mask_off']=='yes':
        finding('mask_off','需要核对睡眠中的未戴机时段',
                '本期间自述：睡眠中摘机或醒后未重新戴机。',
                '用机期间的事件记录无法描述未戴机时段的呼吸情况。',
                '记录摘机原因与时刻，优先解决面罩不适或其他佩戴障碍，并与医生讨论如何覆盖完整睡眠时段。',('ATS-PAP','ATS-MASK'))
    if current['zero_duration_event_days']:
        finding('inconsistent_summary','存在需要核对的摘要不一致',f"{current['zero_duration_event_days']} 天使用时长为零但记录了事件。",'这些天的事件未进入频率计算。','核对原厂报告与设备时间。')
    for key in ('unrefreshed','gasping','drowsy_driving'):
        if context[key]=='yes':
            finding('symptom_'+key,'需要关注：'+CONTEXT_FIELDS[key],
                    '本期间自述：'+CONTEXT_FIELDS[key]+'。',
                    '设备数字不能代替症状评估。',
                    '困倦时不要驾驶或操作危险设备，尽快联系医生评估。' if key=='drowsy_driving' else '联系睡眠门诊，核对治疗覆盖及持续症状的原因。',
                    ('NIH-LIVING',) if key=='drowsy_driving' else ('AASM2021',))
    report['questions']=[
        '设备原厂报告中的 AHI 和事件类型，与这里的 USR 条目频率是否一致？',
        '实际睡眠（含午睡）是否全程戴机？短用机或记录中断能否由作息、摘机或数据缺失解释？',
        '面罩贴合、管路、干燥或噪声是否影响使用？原厂漏气读数如何定义？',
        '若仍困倦或症状再次出现，是否需要进一步评估，或由医生安排复查睡眠监测？'
    ]
    from patient_summary import patient_summary
    report['patient']=patient_summary(report,rows,locale=locale)
    if locale == 'en-US':
        report['sources'] = SOURCES_EN
        report['comparison']['rule'] = COMPARISON_RULE_EN
        report['questions'] = QUESTIONS_EN
        report['review_days'] = [dict(day, reasons=[_review_reason_en(reason) for reason in day['reasons']]) for day in report['review_days']]
        report['findings'] = _english_findings(report)
    v=report['patient']
    report['summary']=v['title']+'。'+v['detail']+v['followup']['title']+'：'+v['followup']['action']
    if locale == 'en-US':
        report['summary']=v['title']+'. '+v['detail']+' '+v['followup']['title']+': '+v['followup']['action']
    return report


def _review_reason_en(reason):
    return {
        '本期间事件条目频率排序靠前': 'High event-entry frequency in this period',
        '设备使用记录少于 4 小时': 'Device treatment record shorter than 4 hours',
        '本期间 CSA 条目频率最高，需核对原厂类型': 'Highest CSA entry frequency in this period; check the manufacturer classification',
    }.get(reason, reason)


def _english_findings(report):
    """Translate selected findings without changing their decision rules."""
    p, previous, context = report['current'], report['previous'], report['context']
    length = p['calendar_days']
    fields = CONTEXT_FIELDS_EN
    result = []
    for original in report['findings']:
        fid = original['id']
        refs = original['refs']
        if fid == 'no_summary':
            value = (f"There is no settled summary in {length} calendar days; {p['pending_days']} days are pending and {p['missing_days']} have no record.",
                     'No summary does not mean no treatment; retained waveform time is not the same as actual sleep time.',
                     'Add device records or choose a period that contains settled historical summaries.')
        elif fid == 'usage':
            value = (f"{length} calendar days include {p['settled_days']} settled summaries, with treatment recorded on {p['use_days']} days; total {minutes(p['total_minutes'], 'en-US')}, average per recorded day {minutes(p['mean_minutes'], 'en-US')}.",
                     f"{p['under4_days']} settled days are under 4 hours. Four hours is a descriptive bin, not sufficient therapy and not proof that the whole night was covered.",
                     'Compare with actual sleep, wake and nap times to check use during every sleep period. Address mask discomfort or removal that limits use.')
        elif fid == 'events':
            value = (f"There are {sum(p['counts'].values())} event entries, weighted by treatment time to {number(p['frequency'])} entries/hour; OSA {p['counts']['OSA']}, CSA {p['counts']['CSA']}, HYP {p['counts']['HYP']}.",
                     'These are device entries and may be grouped by minute. Without EEG sleep time and independent oxygen data, they cannot be converted to a validated clinical AHI or rule out residual sleep-related breathing problems.',
                     'Review dates with concentrated entries alongside symptoms, the manufacturer report and the corresponding waveform. A clinician should decide whether repeat sleep testing is needed.')
        elif fid == 'comparison':
            change = p['mean_minutes'] - previous['mean_minutes']
            rate_text = f"; event-entry frequency changed from {number(previous['frequency'])} to {number(p['frequency'])}/h" if p['frequency'] is not None and previous['frequency'] is not None else ''
            value = (f"Average treatment time per recorded day changed from {minutes(previous['mean_minutes'], 'en-US')} to {minutes(p['mean_minutes'], 'en-US')} ({'increased' if change >= 0 else 'decreased'} {abs(change):.0f} minutes){rate_text}.",
                     f"The comparison period was {previous['start']} to {previous['end']}; the two periods contain {previous['settled_days']} and {p['settled_days']} settled summaries. This is descriptive and does not prove improvement, worsening or that a pressure change worked.",
                     'If the change coincides with a mask replacement, position, schedule or treatment adjustment, record the date for follow-up.')
        elif fid == 'comparison_limited':
            value = (f"The current period has {p['settled_days']}/{length} settled summaries; the adjacent period has {previous['settled_days']}/{length}.",
                     COMPARISON_RULE_EN,
                     'Choose a more complete period; the raw summaries remain available for review.')
        elif fid == 'quality':
            gap = ' The imported snapshot also contains unreadable file ranges that cannot be assigned reliably to a date.' if '读取缺口' in original['observed'] else ''
            value = (f"{p['wave_days']} / {length} days have retained waveforms, {p['missing_days']} have no summary and {p['pending_days']} are pending.{gap}",
                     'Complete summaries and complete waveforms are different. A small amount of retained waveform cannot represent the whole period, and pressure/leak channel meanings have not been checked item by item against the manufacturer.',
                     'Keep the original card and local copy. Bring the manufacturer report or sleep-study report to follow-up and check device time and missing records.')
        elif fid == 'wave_review':
            value = (f"Event frequency and short-use records selected {len(report['wave_reviews'])} waveform dates for closer review. Each lists waveform coverage, pressure/leak percentiles, gaps longer than 5 minutes and whether event minutes overlap retained data.",
                     'Five minutes is a navigation aid, not an arousal standard. A gap does not prove awakening or mask removal, and co-occurring pressure/leak changes do not prove causation.',
                     'Open the synchronized waveform for each date and compare it with the night\'s experience and the manufacturer event labels.')
        elif fid == 'context_missing':
            value = ('Daytime sleepiness, mask problems, mask-off periods and self-reported sleep time have not been entered for this period.',
                     'The current direction is based mainly on device records. How you feel after sleep can help distinguish a numerical change from actual recovery.',
                     'Add the self-report below. If symptoms persist or return, take the report to a sleep clinician.')
        elif fid == 'sleep_coverage':
            hours = context['sleep_hours']; diff = hours * 60 - p['mean_minutes']
            value = (f"Self-reported average sleep was {minutes(hours * 60, 'en-US')}; average device treatment time was {minutes(p['mean_minutes'], 'en-US')}, a difference of {abs(diff):.0f} minutes ({'sleep time was longer' if diff > 0 else 'treatment time was longer or equal'}).",
                     'The two averages use different definitions and may include awake treatment, naps or recall error. The difference is not an exact untreated-sleep duration.',
                     'For one week, record sleep onset, waking, naps and mask-off times, then check for sleep periods without treatment.')
        elif fid == 'persistent_symptoms':
            value = ('You reported persistent or worsening daytime sleepiness during this period.',
                     'Even a low device-entry frequency cannot rule out insufficient treatment or another cause of sleepiness.',
                     'Contact a sleep clinic with this report. Check total sleep, all-night use, mask fit and manufacturer residual-event data before a clinician decides on further assessment or repeat testing.')
        elif fid == 'mask_issue':
            value = ('You reported mask leak, noise or mouth/nose dryness affecting use during this period.',
                     'The leak channel in this software is not validated; a low displayed value cannot rule out real discomfort.',
                     'Ask equipment support or a sleep clinic to check mask fit and tubing. Record when discomfort occurs for waveform comparison; leave pressure changes to a clinician.')
        elif fid == 'mask_off':
            value = ('You reported removing the mask during sleep or not putting it back on after waking.',
                     'Events recorded while the device is worn cannot describe breathing during mask-off periods.',
                     'Record why and when the mask was removed, address the barrier first and discuss complete sleep-period coverage with a clinician.')
        elif fid == 'inconsistent_summary':
            value = (f"{p['zero_duration_event_days']} days have zero treatment time but contain event entries.",
                     'Those entries were excluded from the frequency denominator.',
                     'Check the manufacturer report and device clock.')
        elif fid.startswith('symptom_'):
            key = fid.removeprefix('symptom_')
            label = fields.get(key, key)
            action = 'When drowsy, do not drive or operate dangerous equipment; contact a clinician promptly.' if key == 'drowsy_driving' else 'Contact a sleep clinic to review treatment coverage and the cause of persistent symptoms.'
            value = (f"You reported: {label}.", 'Device numbers cannot replace symptom assessment.', action)
        else:
            value = (original['observed'], original['meaning'], original['action'])
        result.append({'id': fid, 'title': _finding_title_en(fid), 'observed': value[0], 'meaning': value[1], 'action': value[2], 'refs': refs, 'evidence': original.get('evidence', [])})
    return result


def _finding_title_en(fid):
    return {
        'no_summary': 'Treatment and event trend cannot be assessed for this period',
        'usage': 'Confirmed treatment use',
        'events': 'Respiratory event level and what to check next',
        'comparison': 'Compared with the adjacent period',
        'comparison_limited': 'No before-and-after conclusion for this period',
        'quality': 'Evidence coverage for this conclusion',
        'wave_review': 'Waveform review material prepared for priority dates',
        'context_missing': 'Adding your experience can improve the assessment',
        'sleep_coverage': 'Check treatment time against self-reported sleep time',
        'persistent_symptoms': 'Review persistent sleepiness with a sleep clinician',
        'mask_issue': 'Address the mask problem that affects use first',
        'mask_off': 'Check sleep periods without the mask',
        'inconsistent_summary': 'Summary inconsistency needs checking',
        'symptom_unrefreshed': 'Attention: often still unrefreshed after waking',
        'symptom_gasping': 'Attention: repeated gasping or witnessed pauses',
        'symptom_drowsy_driving': 'Attention: unsafe drowsiness',
    }.get(fid, fid)


def report_markdown(report):
    if normalize_locale(report.get('locale')) == 'en-US':
        return report_markdown_en(report)
    p=report['current'];previous=report['previous']
    lines=['# PAP 治疗记录分析报告','',f"设备：{report['device'].get('model','未知')} · 期间：{p['start']} 至 {p['end']}",
           f"生成：{report['generated_at']} · 数据导入：{report.get('imported_at') or '未记录'} · 规则版本：{report['version']}",
           '', '## 期间结论','',report['summary'],'','> 基于未与原厂逐项核对的设备解析及患者自述；供记录复核，不作为诊断或调压处方。','',
           '## 与前一等长期间比较','',f"前一期间：{previous['start']} 至 {previous['end']}",'',
           '| 指标 | 当前期间 | 前一期间 |','|---|---:|---:|',
           f"| 已结算记录日 | {p['settled_days']}/{p['calendar_days']} | {previous['settled_days']}/{previous['calendar_days']} |",
           f"| 平均使用 | {minutes(p['mean_minutes'])} | {minutes(previous['mean_minutes'])} |",
           f"| 加权事件条目/h | {number(p['frequency'])} | {number(previous['frequency'])} |",'']
    for f in report['findings']:
        lines.extend(['## '+f['title'],'','观察：'+f['observed'],'','解释：'+f['meaning'],'','建议：'+f['action'],''])
    lines+=['## 本期间患者自述','']
    for key,label in CONTEXT_FIELDS.items():lines.append(f"- {label}："+{'yes':'是','no':'否','unknown':'未填写'}[report['context'][key]])
    lines+=['- 平均睡眠时长：'+(str(report['context']['sleep_hours'])+' 小时' if report['context']['sleep_hours'] else '未填写')]
    # Prevent user notes becoming injected Markdown links or markup in exports.
    if report['context']['note']:lines+=['','备注（患者自述）：','',*['    '+line for line in report['context']['note'].splitlines()]]
    lines+=['','## 优先复核日期','']
    for d in report['review_days']:lines.append(f"- {d['date']}：{'; '.join(d['reasons'])}；用机 {minutes(d['minutes'])}；事件 {number(d['frequency'])}/h；{'有' if d['wave'] else '无'}波形")
    lines+=['','## 波形复核资料（有目的的抽样，不外推整个期间）','']
    for d in report['wave_reviews']:
        if 'error' in d:lines.append(f"- {d['date']}：读取失败");continue
        lines.append(f"- {d['date']}：保留波形约 {d['wave_seconds']} 秒（每包按 1 秒计）；相当于摘要时长约 {number(d['coverage']*100 if d['coverage'] is not None else None,0)}%；{len(d['gaps'])} 个至少 5 分钟的记录间隔；{d['events_with_wave']}/{d['events']} 个事件记录分钟与保留波形有交集。")
        for key,label in [('ipap','吸气压力 IPAP cmH2O'),('epap','呼气压力 EPAP cmH2O'),('leak','设备漏气 L/min')]:
            stat=d['stats'].get(key,{})
            lines.append(f"  - {label}：中位数 {number(stat.get('median'))}，P95 {number(stat.get('p95'))}。")
    lines+=['','## 复诊核对问题','',*['- '+q for q in report['questions']],'','## 依据与解释规则','',report['comparison']['rule'],'']
    lines.extend(f"- [{source['title']}]({source['url']})" for source in SOURCES)
    return '\n'.join(lines)+'\n'


def report_markdown_en(report):
    p, previous, context = report['current'], report['previous'], report['context']
    answer = {'yes': 'Yes', 'no': 'No', 'unknown': 'Not answered'}
    lines = [
        '# PAP treatment record review', '',
        f"Device: {report['device'].get('model', 'Unknown')} · Period: {p['start']} to {p['end']}",
        f"Generated: {report['generated_at']} · Data imported: {report.get('imported_at') or 'Not recorded'} · Rule version: {report['version']}",
        '', '## Period conclusion', '', report['summary'],
        '', '> Based on device parsing that has not been checked item by item against the manufacturer and on patient self-report; for record review, not diagnosis or pressure prescription.',
        '', '## Comparison with the adjacent period', '', f"Adjacent period: {previous['start']} to {previous['end']}", '',
        '| Metric | Current period | Adjacent period |', '|---|---:|---:|',
        f"| Settled record days | {p['settled_days']}/{p['calendar_days']} | {previous['settled_days']}/{previous['calendar_days']} |",
        f"| Average treatment time | {minutes(p['mean_minutes'], 'en-US')} | {minutes(previous['mean_minutes'], 'en-US')} |",
        f"| Weighted event entries/hour | {number(p['frequency'])} | {number(previous['frequency'])} |", '',
    ]
    for finding in report['findings']:
        lines.extend(['## ' + finding['title'], '', 'Observation: ' + finding['observed'], '', 'Interpretation: ' + finding['meaning'], '', 'Next step: ' + finding['action'], ''])
    lines += ['## Patient self-report for this period', '']
    for key, label in CONTEXT_FIELDS_EN.items():
        lines.append(f"- {label}: {answer[context[key]]}")
    lines.append('- Average sleep time: ' + (f"{context['sleep_hours']} hours" if context['sleep_hours'] else 'Not answered'))
    if context['note']:
        lines += ['', 'Patient note:', '', *['    ' + line for line in context['note'].splitlines()]]
    lines += ['', '## Dates prioritized for review', '']
    for day in report['review_days']:
        lines.append(f"- {day['date']}: {'; '.join(day['reasons'])}; treatment {minutes(day['minutes'], 'en-US')}; events {number(day['frequency'])}/h; {'waveform available' if day['wave'] else 'no waveform'}")
    lines += ['', '## Waveform review material (purposeful sample, not extrapolated)', '']
    for day in report['wave_reviews']:
        if 'error' in day:
            lines.append(f"- {day['date']}: read failed")
            continue
        lines.append(f"- {day['date']}: {day['wave_seconds']} seconds of retained waveform; about {number(day['coverage'] * 100 if day['coverage'] is not None else None, 0)}% of summary treatment time; {len(day['gaps'])} gaps of at least 5 minutes; {day['events_with_wave']}/{day['events']} event minutes overlap retained waveform.")
        for key, label in [('pressure', 'Pressure cmH2O'), ('leak', 'Device leak L/min')]:
            stat = day['stats'].get(key, {})
            lines.append(f"  - {label}: median {number(stat.get('median'))}, P95 {number(stat.get('p95'))}.")
    lines += ['', '## Questions for follow-up', '', *['- ' + q for q in report['questions']], '', '## Evidence and interpretation rules', '', report['comparison']['rule']]
    lines.extend(f"- [{source['title']}]({source['url']})" for source in report['sources'])
    return '\n'.join(lines) + '\n'


def report_html(report):
    """Standalone report: no scripts, remote assets, or hidden patient data."""
    if normalize_locale(report.get('locale')) == 'en-US':
        return report_html_en(report)
    e=lambda value:html.escape(str(value))
    p=report['current'];prev=report['previous'];context=report['context']
    comparison=''.join(f'<tr><th>{e(name)}</th><td>{e(a)}</td><td>{e(b)}</td></tr>' for name,a,b in [
        ('已结算记录日',f"{p['settled_days']}/{p['calendar_days']}",f"{prev['settled_days']}/{prev['calendar_days']}"),
        ('记录日平均用机',minutes(p['mean_minutes']),minutes(prev['mean_minutes'])),
        ('事件条目 /h（加权，估算）',number(p['frequency']),number(prev['frequency'])),
        ('OSA / CSA / HYP 条目', ' / '.join(str(v) for v in p['counts'].values()), ' / '.join(str(v) for v in prev['counts'].values())),
        ('摘要少于4小时的天数',p['under4_days'],prev['under4_days']),
        ('有保留波形的天数',p['wave_days'],prev['wave_days'])])
    findings=''.join(f"<section><h3>{e(f['title'])}</h3><p><b>观察：</b>{e(f['observed'])}</p><p><b>解释：</b>{e(f['meaning'])}</p><p><b>下一步：</b>{e(f['action'])}</p></section>" for f in report['findings'])
    context_rows=''.join(f"<tr><th>{e(label)}</th><td>{e({'yes':'是','no':'否','unknown':'未填写'}[context[key]])}</td></tr>" for key,label in CONTEXT_FIELDS.items())
    review=''.join(f"<tr><td>{e(d['date'])}</td><td>{e('; '.join(d['reasons']))}</td><td>{e(minutes(d['minutes']))}</td><td>{e(number(d['frequency']))}</td><td>{'有' if d['wave'] else '无'}</td></tr>" for d in report['review_days'])
    waves=[]
    for d in report['wave_reviews']:
        if 'error' in d:waves.append(f"<p>{e(d['date'])}：读取失败。</p>");continue
        ipap=d['stats'].get('ipap',{});epap=d['stats'].get('epap',{});leak=d['stats'].get('leak',{})
        waves.append(f"<section><h3>{e(d['date'])}</h3><p>保留波形约 {d['wave_seconds']} 秒（每包按 1 秒计）；约为摘要时长 {number(d['coverage']*100 if d['coverage'] is not None else None,0)}%；{len(d['gaps'])} 个至少 5 分钟的无记录间隔。{d['events_with_wave']}/{d['events']} 个事件分钟与波形有交集。</p><p>吸气压力 IPAP 中位/P95 {number(ipap.get('median'))}/{number(ipap.get('p95'))} cmH₂O；呼气压力 EPAP 中位/P95 {number(epap.get('median'))}/{number(epap.get('p95'))} cmH₂O；设备漏气中位/P95 {number(leak.get('median'))}/{number(leak.get('p95'))} L/min。</p></section>")
    sources=''.join(f"<li><a href='{e(s['url'])}' rel='noreferrer'>{e(s['title'])}</a></li>" for s in SOURCES)
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PAP 治疗记录分析 {e(p['start'])} — {e(p['end'])}</title>
<style>body{{font:13px/1.8 "Noto Sans CJK SC",sans-serif;color:#20374a;max-width:950px;margin:28px auto;padding:0 24px}}h1{{font-size:23px;margin:0}}h2{{font-size:17px;border-bottom:1px solid #bbc9d3;margin-top:24px}}h3{{font-size:14px;margin:12px 0 5px}}p{{margin:5px 0}}.meta,.note{{font-size:11px;color:#637988}}.summary{{background:#edf3f7;border-left:3px solid #44789a;padding:12px;margin:15px 0}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{border:1px solid #d5dfe6;padding:7px;text-align:left}}th{{background:#f1f5f8;font-weight:500}}section{{break-inside:avoid;border-bottom:1px solid #e0e5e9;padding-bottom:9px}}.self{{white-space:pre-wrap}}a{{color:#225f89}}@page{{size:A4;margin:16mm}}@media print{{body{{margin:0;padding:0;font-size:11px;max-width:none}}.print-hint{{display:none}}h2{{break-after:avoid}}tr{{break-inside:avoid}}thead{{display:table-header-group}}}}</style>
<p class="print-hint">此报告可离线打开。浏览器菜单“打印”可另存为 PDF。</p><h1>PAP 治疗记录分析报告</h1><p class="meta">设备：{e(report['device'].get('model','未知'))} · 期间：{e(p['start'])} 至 {e(p['end'])}<br>生成：{e(report['generated_at'])} · 数据导入：{e(report.get('imported_at'))} · 分析规则 {e(report['version'])}</p>
<div class="summary"><b>期间结论</b><p>{e(report['summary'])}</p></div><p class="note">基于设备解析与患者自述，尚未与原厂逐项核对。供记录复核，不作为诊断或调压处方。</p>
<h2>期间汇总与比较</h2><p class="note">前一期间：{e(prev['start'])} 至 {e(prev['end'])}</p><table><thead><tr><th>指标</th><th>当前期间</th><th>前一期间</th></tr></thead><tbody>{comparison}</tbody></table><p class="note">{e(report['comparison']['rule'])}</p>
<h2>患者自述（本期间）</h2><table>{context_rows}<tr><th>自报每日平均睡眠</th><td>{e(str(context['sleep_hours'])+' 小时' if context['sleep_hours'] else '未填写')}</td></tr></table><p class="self">{e(context['note'] or '无补充备注。')}</p>
<h2>观察、解释与建议</h2>{findings}
<h2>优先复核日期</h2><p class="note">按事件条目频率、短用机记录及 CSA 条目频率筛选；排序不等于异常诊断。</p><table><thead><tr><th>日期</th><th>原因</th><th>用机</th><th>条目/h</th><th>波形</th></tr></thead><tbody>{review or '<tr><td colspan="5">无符合筛选条件的日期。</td></tr>'}</tbody></table>
<h2>重点波形资料（最多3天）</h2>{''.join(waves) or '<p>优先日期没有可用波形。</p>'}<p class="note">压力通道沿用 OSCAR 的 BMC 旧格式解释，待原厂核验。有目的抽样不代表整个期间。记录间隔不等于觉醒；事件分钟与波形有交集不代表识别正确。</p>
<h2>复诊核对问题</h2><ol>{''.join('<li>'+e(q)+'</li>' for q in report['questions'])}</ol><h2>依据</h2><ul>{sources}</ul></html>'''


def report_html_en(report):
    """Render a self-contained English review report."""
    e = lambda value: html.escape(str(value))
    p, previous, context = report['current'], report['previous'], report['context']
    answer = {'yes': 'Yes', 'no': 'No', 'unknown': 'Not answered'}
    comparison = ''.join(f'<tr><th>{e(name)}</th><td>{e(a)}</td><td>{e(b)}</td></tr>' for name, a, b in [
        ('Settled record days', f"{p['settled_days']}/{p['calendar_days']}", f"{previous['settled_days']}/{previous['calendar_days']}"),
        ('Average treatment time', minutes(p['mean_minutes'], 'en-US'), minutes(previous['mean_minutes'], 'en-US')),
        ('Weighted event entries/hour (estimated)', number(p['frequency']), number(previous['frequency'])),
        ('OSA / CSA / HYP entries', ' / '.join(str(v) for v in p['counts'].values()), ' / '.join(str(v) for v in previous['counts'].values())),
        ('Days under 4 hours', p['under4_days'], previous['under4_days']),
        ('Days with retained waveform', p['wave_days'], previous['wave_days']),
    ])
    findings = ''.join(f"<section><h3>{e(finding['title'])}</h3><p><b>Observation:</b> {e(finding['observed'])}</p><p><b>Interpretation:</b> {e(finding['meaning'])}</p><p><b>Next step:</b> {e(finding['action'])}</p></section>" for finding in report['findings'])
    context_rows = ''.join(f"<tr><th>{e(label)}</th><td>{e(answer[context[key]])}</td></tr>" for key, label in CONTEXT_FIELDS_EN.items())
    context_sleep = f"{context['sleep_hours']} hours" if context['sleep_hours'] else 'Not answered'
    review = ''.join(f"<tr><td>{e(day['date'])}</td><td>{e('; '.join(day['reasons']))}</td><td>{e(minutes(day['minutes'], 'en-US'))}</td><td>{e(number(day['frequency']))}</td><td>{'Available' if day['wave'] else 'None'}</td></tr>" for day in report['review_days'])
    waves = []
    for day in report['wave_reviews']:
        if 'error' in day:
            waves.append(f"<p>{e(day['date'])}: read failed.</p>")
            continue
        pressure, leak = day['stats'].get('pressure', {}), day['stats'].get('leak', {})
        waves.append(f"<section><h3>{e(day['date'])}</h3><p>{day['wave_seconds']} seconds of retained waveform; about {number(day['coverage'] * 100 if day['coverage'] is not None else None, 0)}% of summary treatment time; {len(day['gaps'])} gaps of at least 5 minutes. {day['events_with_wave']}/{day['events']} event minutes overlap retained waveform.</p><p>Pressure median/P95 {number(pressure.get('median'))}/{number(pressure.get('p95'))} cmH₂O; device leak median/P95 {number(leak.get('median'))}/{number(leak.get('p95'))} L/min.</p></section>")
    sources = ''.join(f"<li><a href='{e(source['url'])}' rel='noreferrer'>{e(source['title'])}</a></li>" for source in report['sources'])
    return f'''<!doctype html><html lang="en-US"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PAP treatment review {e(p['start'])} — {e(p['end'])}</title>
<style>body{{font:13px/1.8 sans-serif;color:#20374a;max-width:950px;margin:28px auto;padding:0 24px}}h1{{font-size:23px;margin:0}}h2{{font-size:17px;border-bottom:1px solid #bbc9d3;margin-top:24px}}h3{{font-size:14px;margin:12px 0 5px}}p{{margin:5px 0}}.meta,.note{{font-size:11px;color:#637988}}.summary{{background:#edf3f7;border-left:3px solid #44789a;padding:12px;margin:15px 0}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{border:1px solid #d5dfe6;padding:7px;text-align:left}}th{{background:#f1f5f8;font-weight:500}}section{{break-inside:avoid;border-bottom:1px solid #e0e5e9;padding-bottom:9px}}.self{{white-space:pre-wrap}}a{{color:#225f89}}@page{{size:A4;margin:16mm}}@media print{{body{{margin:0;padding:0;font-size:11px;max-width:none}}.print-hint{{display:none}}h2{{break-after:avoid}}tr{{break-inside:avoid}}thead{{display:table-header-group}}}}</style>
<p class="print-hint">This report works offline. Use the browser's Print command to save it as PDF.</p><h1>PAP treatment record review</h1><p class="meta">Device: {e(report['device'].get('model','Unknown'))} · Period: {e(p['start'])} to {e(p['end'])}<br>Generated: {e(report['generated_at'])} · Data imported: {e(report.get('imported_at') or 'Not recorded')} · Analysis rule {e(report['version'])}</p>
<div class="summary"><b>Period conclusion</b><p>{e(report['summary'])}</p></div><p class="note">Based on device parsing and patient self-report; manufacturer definitions have not been checked item by item. For record review, not diagnosis or pressure prescription.</p>
<h2>Period summary and comparison</h2><p class="note">Adjacent period: {e(previous['start'])} to {e(previous['end'])}</p><table><thead><tr><th>Metric</th><th>Current period</th><th>Adjacent period</th></tr></thead><tbody>{comparison}</tbody></table><p class="note">{e(report['comparison']['rule'])}</p>
<h2>Patient self-report for this period</h2><table>{context_rows}<tr><th>Average self-reported sleep</th><td>{e(context_sleep)}</td></tr></table><p class="self">{e(context['note'] or 'No additional note.')}</p>
<h2>Observations, interpretation and next steps</h2>{findings}
<h2>Dates prioritized for review</h2><p class="note">Selected by event-entry frequency, short treatment use and CSA entry frequency; ranking is not an abnormality diagnosis.</p><table><thead><tr><th>Date</th><th>Reason</th><th>Treatment</th><th>Entries/h</th><th>Waveform</th></tr></thead><tbody>{review or '<tr><td colspan="5">No dates matched the selection rules.</td></tr>'}</tbody></table>
<h2>Priority waveform material (up to 3 days)</h2>{''.join(waves) or '<p>No priority date has an available waveform.</p>'}<p class="note">Purposeful sampling does not represent the whole period. A gap does not prove arousal; overlap between event minutes and waveform does not prove correct classification.</p>
<h2>Questions for follow-up</h2><ol>{''.join('<li>'+e(q)+'</li>' for q in report['questions'])}</ol><h2>Evidence</h2><ul>{sources}</ul></html>'''
