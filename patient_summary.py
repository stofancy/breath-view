"""Plain-language, descriptive patient view shared by the GUI and exports.

The decoded USR frequency is deliberately never classified using AHI cutoffs.
Symptoms can prompt follow-up even when device entries decrease or equal zero.
"""
from datetime import date, timedelta

GLOSSARY = {
    'ahi': ('AHI · 呼吸暂停低通气指数', '睡眠监测中，每睡一小时发生的呼吸暂停与低通气次数。是评估睡眠呼吸暂停的核心指标之一，还要结合血氧和症状。本软件尚不能从这张卡确认原厂 AHI。'),
    'frequency': ('呼吸事件记录 / 小时', '暂停与低通气的设备条目总数 ÷ 戴机总小时数。条目可能把同一分钟内的事件合在一起，所以暂不能当作 AHI，也不能套用轻、中、重度分级。'),
    'usage': ('平均戴机时间', '有已结算记录的日子，平均用了多久。清醒时也可能戴机，因此不等于睡眠时长；缺失日期没有算成零使用。睡觉和午睡都应按医嘱使用。'),
    'comparison': ('前期与去年同期', '前期是紧挨本期、天数相同的时段；去年同期按同一月日对齐。均用总条目 ÷ 总用机小时比较。至少各有 7 个已结算日、覆盖各自期间 70% 才描述变化；这是数据规则，不是疾病阈值。'),
    'OSA': ('OSA · 阻塞性暂停', '睡觉时上气道变窄或堵住，气流暂停。这里表示设备标记的这一类条目，仍需核对原厂定义。'),
    'CSA': ('CSA · 中枢性暂停', '呼吸驱动暂时不足，呼吸努力暂停。设备标注不等于确诊中枢性睡眠呼吸暂停，也不能据此自行调压。'),
    'HYP': ('HYP · 低通气', '呼吸气流明显减弱，但不一定完全停止。正式睡眠监测还结合血氧下降或觉醒判断；这里是设备条目。'),
    'leak': ('漏气', '面罩或嘴部漏出的气体可能影响舒适度和治疗。本卡通道是否包含面罩正常排气还不确定，不能套用其他品牌的漏气警戒线。'),
    'pressure': ('压力 · cmH₂O', '呼吸机用来撑开气道的压力，单位是厘米水柱。高低本身不表示睡得好坏，设置需结合医生处方。'),
    'p95': ('P95 · 第 95 百分位', '95% 的已保留采样值不超过这个数。不是最高值，也不是目标压力；只有少数日期有波形时，不能代表整个月。'),
    'quality': ('哪些数据能说明睡眠', '这张卡能记录用机与呼吸事件。实际睡眠时间、深睡/REM、觉醒和夜间血氧尚无可用测量；需要结合你的感受，必要时由医生安排睡眠监测。'),
}


def compare(current, other, overlap=False):
    from analysis_report import number
    eligible = not overlap and all(p['settled_days'] >= 7 and p['settled_days'] / p['calendar_days'] >= .7 for p in (current, other))
    eligible = eligible and current['frequency'] is not None and other['frequency'] is not None
    result = {'eligible': eligible, 'period': other, 'direction': 'unknown', 'delta': None, 'percent': None, 'minutes_delta': None}
    if not eligible:
        result['text'] = '期间重叠，暂不比较' if overlap else '可用记录不足，暂不比较'
        return result
    delta = current['frequency'] - other['frequency']
    # Describe at the displayed precision; do not call tiny rounded differences
    # improvement or use a made-up clinical significance threshold.
    displayed = round(current['frequency'], 2) - round(other['frequency'], 2)
    direction = 'up' if displayed > 0 else 'down' if displayed < 0 else 'same'
    percent = delta / other['frequency'] * 100 if other['frequency'] else None
    text = {'up': '记录频率上升', 'down': '记录频率下降', 'same': '记录频率相近'}[direction]
    if direction != 'same':
        text += f" {abs(percent):.1f}%" if percent is not None else f" {number(abs(delta))} 条目/小时（前值为 0）"
    result.update(direction=direction, delta=delta, percent=percent, minutes_delta=current['mean_minutes']-other['mean_minutes'], text=text)
    return result


def previous_year(value):
    d = date.fromisoformat(value)
    try:
        return d.replace(year=d.year-1).isoformat()
    except ValueError:  # Feb 29 -> Feb 28, with the actual window disclosed.
        return d.replace(year=d.year-1, day=28).isoformat()


def patient_summary(report, rows):
    from analysis_report import aggregate, CONTEXT_FIELDS, minutes, number
    p, c = report['current'], report['context']
    year = aggregate(rows, previous_year(p['start']), previous_year(p['end']))
    comparisons = {
        'previous': compare(p, report['previous']),
        'year': compare(p, year, overlap=year['end'] >= p['start']),
    }
    symptoms = [CONTEXT_FIELDS[k] for k in ('unrefreshed','sleepiness','gasping') if c[k] == 'yes']
    if c['drowsy_driving'] == 'yes':
        followup = {'level':'priority', 'title':'尽快联系医生，先避免困倦驾驶', 'reason':'你报告开车或操作设备时难以保持清醒。', 'action':'困倦时停止驾驶和危险操作，安排其他出行方式，并尽快联系医生评估。', 'refs':['NIH-LIVING']}
    elif symptoms:
        followup = {'level':'review', 'title':'建议预约睡眠门诊复诊', 'reason':'你报告：'+'、'.join(symptoms)+'。', 'action':'带上这份摘要与原来的睡眠监测报告，核对是否整夜得到治疗，以及持续不适的原因。', 'refs':['AASM2021']}
    elif c['mask_problem'] == 'yes' or c['mask_off'] == 'yes':
        followup = {'level':'support', 'title':'先处理影响戴机的问题', 'reason':'你报告面罩不适或睡眠中摘机，可能影响整夜使用。', 'action':'联系设备服务人员或睡眠门诊检查佩戴；如果仍影响睡眠或无法持续使用，预约复诊。', 'refs':['ATS-PAP','ATS-MASK']}
    elif not all(c[k] == 'no' for k in CONTEXT_FIELDS):
        followup = {'level':'unknown', 'title':'还需要知道你睡醒后的感受', 'reason':'目前的症状自述不完整，单靠设备数字不能判断是否需要提前复诊。', 'action':'补充下方几项感受；如仍困倦、憋醒或症状重新出现，联系睡眠门诊。', 'refs':['AASM2021']}
    else:
        followup = {'level':'routine', 'title':'按原计划随访，留意症状变化', 'reason':'你没有报告上述持续症状和佩戴问题；这不等于已经确认治疗达标。', 'action':'继续按医嘱使用；首次复核本软件记录时，请医生对照原厂 AHI。若症状重现，提前联系门诊。', 'refs':['AASM2021','ATS2013']}
    change = comparisons['previous']
    if p['frequency'] is None:
        title, detail = '这段期间还没有足够记录', '先导入数据或选择已有使用记录的期间。'
    elif change['eligible']:
        title = {'down':'记录中的呼吸事件比前期少了','up':'记录中的呼吸事件比前期多了','same':'呼吸事件记录与前期相近'}[change['direction']]
        detail = f"每小时 {number(report['previous']['frequency'])} → {number(p['frequency'])} 条目；平均戴机 {minutes(p['mean_minutes'])}。"
    else:
        title, detail = '先看这段时间的治疗记录', f"平均戴机 {minutes(p['mean_minutes'])}；每小时 {number(p['frequency'])} 条呼吸事件记录。"
    if c['unrefreshed']=='yes':
        feeling = '自述：睡醒后经常仍不解乏'
    elif c['unrefreshed']=='no':
        feeling = '自述：没有经常睡醒仍不解乏'
    else:
        feeling = '还未记录睡醒后的感受'
    points = []
    by_day = {r['date']:r for r in rows}
    for n in range(p['calendar_days']):
        day = (date.fromisoformat(p['start'])+timedelta(days=n)).isoformat()
        row = by_day.get(day)
        valid = row is not None and not row['current'] and row['minutes'] is not None
        points.append({'date':day, 'minutes':row['minutes'] if valid else None,
                       'frequency':sum(row['counts'].values())/(row['minutes']/60) if valid and row['minutes']>0 else None,
                       'state':'settled' if valid else 'pending' if row else 'missing'})
    last = next((r for r in reversed(rows) if not r['current'] and r['minutes'] is not None), None)
    questions = []
    if symptoms or c['drowsy_driving']=='yes': questions.append('我仍有这些不适：'+'、'.join(symptoms+([CONTEXT_FIELDS['drowsy_driving']] if c['drowsy_driving']=='yes' else []))+'。是否需要进一步评估？')
    if c['mask_problem']=='yes' or c['mask_off']=='yes': questions.append('不适或摘机影响整夜使用，应该怎样处理？')
    questions.extend(['请核对原厂 AHI、血氧与这里的设备事件记录，当前治疗是否充分？','结合我的症状和历史睡眠监测，是否需要调整随访或复查？'])
    return {'title':title, 'detail':detail, 'feeling':feeling, 'followup':followup,
            'ahi':{'value':None,'status':'本卡尚不能确认原厂 AHI'},
            'boundary':'事件记录变少不等于睡眠一定变好，还要看睡醒后的感受、血氧和实际睡眠。',
            'comparisons':comparisons, 'trend':points, 'glossary':GLOSSARY,
            'questions':questions[:4], 'context_labels':CONTEXT_FIELDS,
            'latest_settled':last['date'] if last else None,
            'coverage':f"{p['calendar_days']} 天中，{p['settled_days']} 天可计算，{p['pending_days']} 天未结算，{p['missing_days']} 天缺记录；{p['wave_days']} 天有波形。"}
