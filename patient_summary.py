"""Directional, provisional treatment assessment shared by GUI and exports.

The unverified device frequency may trigger conservative follow-up prompts;
it never establishes an AHI diagnosis, severity grade or titration prescription.
"""
from datetime import date, timedelta
from i18n import ASSESSMENT_RULES_EN, CONTEXT_FIELDS_EN, GLOSSARY_EN, QUESTIONS_EN, normalize_locale

GLOSSARY = {
    'ahi': ('AHI · 呼吸暂停低通气指数', '睡眠监测中，每睡一小时发生的呼吸暂停与低通气次数。是评估睡眠呼吸暂停的核心指标之一，还要结合血氧和症状。本软件尚不能从这张卡确认原厂 AHI。'),
    'frequency': ('呼吸事件指数 · 估算', '暂停与低通气的设备条目总数 ÷ 已结算摘要的用机小时数，用来观察治疗方向；不以留存波形长度代替用机时间。其他软件若按不同使用时段计时，结果可能不同。事件与摘要时长已用本机数据和 OSCAR 底层解析交叉核对。原厂 AHI 的计算口径仍需核对，不用戴机后的指数给原始病情分级。'),
    'assessment': ('初步判断与把握程度', '综合呼吸事件水平、前后趋势、戴机时长和已填写的感受给出倾向判断。把握程度说明当前证据够不够，并非病情概率；症状未填写时只判断设备所反映的治疗方向。'),
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


def compare(current, other, overlap=False, locale='zh-CN'):
    from analysis_report import number
    locale = normalize_locale(locale)
    eligible = not overlap and all(p['settled_days'] >= 7 and p['settled_days'] / p['calendar_days'] >= .7 for p in (current, other))
    eligible = eligible and current['frequency'] is not None and other['frequency'] is not None
    result = {'eligible': eligible, 'period': other, 'direction': 'unknown', 'delta': None, 'percent': None, 'minutes_delta': None}
    if not eligible:
        result['text'] = ('Periods overlap; comparison deferred' if overlap else 'Not enough usable records; comparison deferred') if locale == 'en-US' else ('期间重叠，暂不比较' if overlap else '可用记录不足，暂不比较')
        return result
    delta = current['frequency'] - other['frequency']
    # Describe at the displayed precision; do not call tiny rounded differences
    # improvement or use a made-up clinical significance threshold.
    displayed = round(current['frequency'], 2) - round(other['frequency'], 2)
    direction = 'up' if displayed > 0 else 'down' if displayed < 0 else 'same'
    percent = delta / other['frequency'] * 100 if other['frequency'] else None
    text = ({'up': 'Entry frequency increased', 'down': 'Entry frequency decreased', 'same': 'Entry frequency is similar'} if locale == 'en-US' else {'up': '记录频率上升', 'down': '记录频率下降', 'same': '记录频率相近'})[direction]
    if direction != 'same':
        text += f" {abs(percent):.1f}%" if percent is not None else (f" {number(abs(delta))} entries/hour (previous value was 0)" if locale == 'en-US' else f" {number(abs(delta))} 条目/小时（前值为 0）")
    result.update(direction=direction, delta=delta, percent=percent, minutes_delta=current['mean_minutes']-other['mean_minutes'], text=text)
    return result


def previous_year(value):
    d = date.fromisoformat(value)
    try:
        return d.replace(year=d.year-1).isoformat()
    except ValueError:  # Feb 29 -> Feb 28, with the actual window disclosed.
        return d.replace(year=d.year-1, day=28).isoformat()


# Transparent software screening thresholds, not validated diagnostic cutoffs.
ASSESSMENT_RULES = [
    '事件关注线：估算条目频率达到 5/h，或至少 3 个且占已结算日 20% 的日期达到 5/h，提示核对残余事件。5/h 仅借鉴残余 AHI 常见复核范围；该条目指标未与原厂校准，因此这是软件筛查提示，不是诊断分界，低于它也不证明治疗充分。',
    '明显变化：前后期间具备比较条件，且频率绝对变化至少 0.5/h、相对变化至少 20%；其余非零变化称小幅变化。两个条件是减少对波动过度解读的软件规则，不是已验证的临床显著性标准。',
    '佩戴关注：至少 3 个且占已结算日 30% 的日期少于 4 小时，或平均戴机比自报睡眠短至少 1 小时，或较前期减少至少 1 小时且降幅至少 20%，提示可能未覆盖全部睡眠；不把 4 小时当作足够治疗，也不把时长差当作精确的未治疗时间。',
    '先看症状和使用障碍，再综合事件与趋势。少于 7 个已结算日或覆盖率低于 70% 时，趋势把握较低；有症状或明显事件线索仍会给出建议，不等待记录凑齐。整体判断把握最高标为中等，等待原厂数据和临床对照。',
]


def material_change(comp):
    return (comp['eligible'] and abs(comp['delta']) >= .5
            and (comp['percent'] is None or abs(comp['percent']) >= 20))


def _assess_en(report, comparisons, rows):
    """Build the English assessment while keeping the decision rules identical."""
    from analysis_report import CONTEXT_FIELDS, minutes, number
    p, c = report['current'], report['context']
    comp, year = comparisons['previous'], comparisons['year']
    enough = p['settled_days'] >= 7 and p['settled_days'] / p['calendar_days'] >= .7
    positive = [r for r in rows if p['start'] <= r['date'] <= p['end'] and not r['current'] and r['minutes'] is not None and r['minutes'] > 0]
    high_days = sum(sum(r['counts'].values()) / (r['minutes'] / 60) >= 5 for r in positive)
    frequent = ((p['frequency'] is not None and p['frequency'] >= 5)
                or (high_days >= 3 and high_days / max(p['settled_days'], 1) >= .2))
    short_days = p['under4_days'] >= 3 and p['under4_days'] / max(p['settled_days'], 1) >= .3
    sleep_gap = (c['sleep_hours'] is not None and p['mean_minutes'] is not None
                 and c['sleep_hours'] * 60 - p['mean_minutes'] >= 60)
    usage_drop = (comp['eligible'] and comp['minutes_delta'] <= -60
                  and -comp['minutes_delta'] / max(comp['period']['mean_minutes'], 1) >= .2)
    zero_use = p['settled_days'] >= 3 and p['total_minutes'] == 0
    symptoms = [CONTEXT_FIELDS_EN[k] for k in ('unrefreshed', 'sleepiness', 'gasping') if c[k] == 'yes']
    problems = [CONTEXT_FIELDS_EN[k] for k in ('mask_problem', 'mask_off') if c[k] == 'yes']
    rising = material_change(comp) and comp['direction'] == 'up'
    falling = material_change(comp) and comp['direction'] == 'down'
    year_rising = material_change(year) and year['direction'] == 'up'
    use_concern = bool(short_days or sleep_gap or usage_drop or zero_use)
    reasons = []
    if p['frequency'] is not None:
        reasons.append(f"About {number(p['frequency'])} respiratory entries/hour during treatment; {high_days} recorded days reached the software's event attention line.")
    if comp['eligible']:
        reasons.append('Compared with the previous period: ' + comp['text'] + '.')
    if year['eligible']:
        reasons.append('Compared with the same period last year: ' + year['text'] + '.')
    reasons.append(f"Average treatment time was {minutes(p['mean_minutes'], 'en-US')}; {p['settled_days']}/{p['calendar_days']} days had a usable summary.")
    if sleep_gap:
        reasons.insert(0, f"Average treatment time was about {c['sleep_hours'] * 60 - p['mean_minutes']:.0f} minutes shorter than self-reported sleep, so the untreated sleep window should be checked.")
    elif short_days:
        reasons.insert(0, f"{p['under4_days']} recorded days had less than 4 hours of treatment; treatment coverage should be checked first.")
    elif usage_drop:
        reasons.insert(0, f"Average treatment time was about {-comp['minutes_delta']:.0f} minutes shorter than the previous period; fewer events may partly reflect a shorter treatment window.")
    if symptoms:
        reasons.insert(0, 'You reported: ' + '; '.join(symptoms) + '.')
    if problems:
        reasons.insert(0, 'You reported: ' + '; '.join(problems) + '.')

    if c['drowsy_driving'] == 'yes':
        state, brief, title = 'priority', 'Seek care promptly', 'Drowsiness is affecting safety and needs prompt attention'
        f = dict(level='priority', title='Contact a clinician promptly and avoid drowsy driving', reason='You reported difficulty staying awake while driving or operating equipment.', action='Do not drive or operate dangerous equipment when drowsy. Arrange another way to travel and contact a clinician promptly.', refs=['NIH-LIVING'])
    elif symptoms:
        state, brief = 'review', 'Schedule a follow-up'
        title = 'Residual breathing symptoms may remain; consider a follow-up' if frequent or c['gasping'] == 'yes' else 'Recovery after sleep is still not ideal; discuss possible causes at follow-up'
        why = 'Respiratory entries and ongoing symptoms both warrant review.' if frequent else 'Even with few recorded events, persistent sleepiness or unrefreshing sleep deserves attention and may involve insufficient sleep, incomplete treatment coverage or another sleep issue.'
        f = dict(level='review', title='Schedule a sleep-clinic appointment', reason=why, action='Bring this summary and the original sleep-study report. Discuss symptoms, all-night use and whether further testing is needed.', refs=['AASM2021'])
    elif frequent:
        state, brief = ('review', 'Review the data') if enough else ('watch', 'Events are elevated')
        title = 'The record suggests more residual respiratory events; review it' if enough else 'The record suggests elevated events; check and continue observing'
        f = dict(level='review' if enough else 'watch', title='Arrange a follow-up to review the record' if enough else 'Continue recording; contact the clinic if the pattern persists', reason=f"The period estimates {number(p['frequency'])} entries/hour, with {high_days} days reaching the event attention line.", action='First check mask fit, treatment coverage and the manufacturer AHI. If the value stays high or sleepiness/gasping continues, contact a sleep clinic.', refs=['AASM2021', 'ATS2013'])
    elif problems or use_concern:
        state, brief, title = 'support', 'Focus on treatment coverage', 'Treatment may not cover all sleep; improve consistent use first'
        f = dict(level='support', title='Address mask and treatment-time barriers first', reason='There are clues of mask discomfort, removal, short use or reduced treatment time that may limit coverage.', action='Check bedtime, naps and mask-off periods. Contact equipment support for mask discomfort; arrange a clinic visit if use remains difficult or sleepiness continues.', refs=['ATS-PAP', 'ATS-MASK'])
    elif rising:
        state, brief, title = 'watch', 'Possible worsening trend', 'Respiratory entries rose clearly; treatment control may be changing'
        f = dict(level='watch', title='Check recent changes and consider an earlier follow-up', reason='Entry frequency shows a clear rise from the previous period and is worth checking.', action='Review mask fit, nasal congestion, schedule and treatment-change dates. If the rise continues for another week or symptoms appear, contact a sleep clinic.', refs=['ATS2013', 'AASM2021'])
    elif p['frequency'] is None:
        state, brief, title = 'limited', 'Add more records', 'Collect valid treatment records before judging direction'
        f = dict(level='unknown', title='Confirm the data and actual use first', reason='There is not yet a usable treatment record from which to calculate event frequency.', action='Update the SD-card data and check recent device use. Contact equipment support or a clinic if using the device is difficult.', refs=['ATS-PAP'])
    elif not enough:
        state, brief, title = 'limited', 'Watch the direction', 'No strong signal yet; continue for a few more nights'
        f = dict(level='observe', title='Continue recording and pay attention to how you feel after sleep', reason='The current records do not trigger an event or coverage prompt, but the period is short.', action='Use the device as prescribed and record how you feel after the next few nights. Contact a clinician earlier if sleepiness or gasping persists.', refs=['ATS-PAP', 'AASM2021'])
    else:
        state, brief = ('improving', 'Possibly improving') if falling else ('stable', 'Generally stable')
        title = 'Respiratory control may be improving; keep going' if falling else 'Overall stable recently, with a small improvement from the previous period' if comp['eligible'] and comp['direction'] == 'down' else 'Overall stable recently; watch the small rise' if comp['eligible'] and comp['direction'] == 'up' else 'The current respiratory trend is generally stable'
        if year_rising:
            f = dict(level='watch', title='Observe for now and discuss the longer-term change at follow-up', reason='There is no clear recent worsening, but the entry frequency is higher than the same period last year and should be checked.', action='Continue using the device as prescribed and record how you feel after sleep. Contact the clinic sooner if the frequency keeps rising or symptoms appear.', refs=['ATS2013', 'AASM2021'])
        else:
            f = dict(level='routine', title='Observe and follow the existing plan', reason='The current record does not trigger a clear event-increase or treatment-coverage prompt, so the numbers do not by themselves suggest an earlier visit.', action='Continue using the device as prescribed. Contact a clinician sooner if marked sleepiness, unrefreshing sleep or gasping continues.', refs=['ATS-PAP', 'AASM2021'])
    answered = sum(c[k] != 'unknown' for k in CONTEXT_FIELDS)
    confidence = 'Moderate · device trend' if enough else 'Low · limited records'
    confidence_note = f"Summaries cover {p['settled_days']}/{p['calendar_days']} days; {answered}/{len(CONTEXT_FIELDS)} self-report items are answered. This is a directional assessment, not a probability or diagnosis. The mapping between device entries and the manufacturer AHI still needs checking; unanswered symptoms were not treated as absent."
    return dict(state=state, brief=brief, title=title, followup=f, reasons=reasons[:5], confidence=confidence,
                confidence_note=confidence_note, rules=ASSESSMENT_RULES_EN,
                signals=dict(frequent=frequent, high_days=high_days, coverage_concern=use_concern, rising=rising, falling=falling, year_rising=year_rising))


def assess(report, comparisons, rows, locale='zh-CN'):
    if normalize_locale(locale) == 'en-US':
        return _assess_en(report, comparisons, rows)
    from analysis_report import CONTEXT_FIELDS, minutes, number
    p, c = report['current'], report['context']
    comp, year = comparisons['previous'], comparisons['year']
    enough = p['settled_days'] >= 7 and p['settled_days']/p['calendar_days'] >= .7
    positive = [r for r in rows if p['start'] <= r['date'] <= p['end'] and not r['current'] and r['minutes'] is not None and r['minutes'] > 0]
    high_days = sum(sum(r['counts'].values())/(r['minutes']/60) >= 5 for r in positive)
    frequent = ((p['frequency'] is not None and p['frequency'] >= 5)
                or (high_days >= 3 and high_days/max(p['settled_days'],1) >= .2))
    # Signals concern treatment coverage; they are not measurements of sleep.
    short_days = p['under4_days'] >= 3 and p['under4_days']/max(p['settled_days'],1) >= .3
    sleep_gap = (c['sleep_hours'] is not None and p['mean_minutes'] is not None
                 and c['sleep_hours']*60-p['mean_minutes'] >= 60)
    usage_drop = (comp['eligible'] and comp['minutes_delta'] <= -60
                  and -comp['minutes_delta']/max(comp['period']['mean_minutes'],1) >= .2)
    zero_use = p['settled_days'] >= 3 and p['total_minutes'] == 0
    symptoms = [CONTEXT_FIELDS[k] for k in ('unrefreshed','sleepiness','gasping') if c[k] == 'yes']
    problems = [CONTEXT_FIELDS[k] for k in ('mask_problem','mask_off') if c[k] == 'yes']
    rising = material_change(comp) and comp['direction']=='up'
    falling = material_change(comp) and comp['direction']=='down'
    year_rising = material_change(year) and year['direction']=='up'
    use_concern = bool(short_days or sleep_gap or usage_drop or zero_use)
    reasons = []
    if p['frequency'] is not None:reasons.append(f"戴机期间约 {number(p['frequency'])} 条呼吸事件/小时；{high_days} 个记录日达到软件的事件关注线。")
    if comp['eligible']:reasons.append('比前期：'+comp['text']+'。')
    if year['eligible']:reasons.append('比去年同期：'+year['text']+'。')
    reasons.append(f"记录日平均戴机 {minutes(p['mean_minutes'])}；{p['settled_days']}/{p['calendar_days']} 天有可用摘要。")
    if sleep_gap:reasons.insert(0,f"平均戴机比自报睡眠短约 {c['sleep_hours']*60-p['mean_minutes']:.0f} 分钟，提示需要核对未戴机的睡眠时段。")
    elif short_days:reasons.insert(0,f"{p['under4_days']} 个记录日戴机不足 4 小时，治疗覆盖值得优先检查。")
    elif usage_drop:reasons.insert(0,f"平均戴机比前期少约 {-comp['minutes_delta']:.0f} 分钟，事件变少可能同时受使用时段变化影响。")
    if symptoms:reasons.insert(0,'你报告：'+'、'.join(symptoms)+'。')
    if problems:reasons.insert(0,'你报告：'+'、'.join(problems)+'。')

    if c['drowsy_driving']=='yes':
        state, brief, title = 'priority','优先就医','困倦已经影响安全，需要优先处理'
        f = dict(level='priority',title='尽快联系医生，先避免困倦驾驶',reason='你报告开车或操作设备时难以保持清醒。',action='停止困倦驾驶和危险操作，安排其他出行方式，尽快联系医生评估。',refs=['NIH-LIVING'])
    elif symptoms:
        state, brief = 'review','建议复诊'
        title = '可能仍有残余呼吸问题，建议复诊' if frequent or c['gasping']=='yes' else '睡后恢复仍不理想，建议复诊找原因'
        why = '呼吸事件与持续症状都值得复核。' if frequent else '即使事件记录不多，持续困倦或不解乏也值得处理，可能涉及睡眠不足、佩戴覆盖或其他睡眠问题。'
        f = dict(level='review',title='建议预约睡眠门诊',reason=why,action='带上摘要和原睡眠监测报告，重点讨论症状、整夜佩戴，以及是否需进一步检查。',refs=['AASM2021'])
    elif frequent:
        state, brief = ('review','建议复核') if enough else ('watch','事件偏多')
        title = '可能仍有较多残余呼吸事件，建议复核' if enough else '已有记录提示事件偏多，先核对并继续观察'
        f = dict(level='review' if enough else 'watch',title='建议安排一次复诊核对' if enough else '近期继续记录，持续偏多就联系门诊',reason=f"期间估算 {number(p['frequency'])} 条目/小时，{high_days} 天达到事件关注线。",action='先核对面罩、佩戴和原厂 AHI；若反复偏高或仍困倦、憋醒，联系睡眠门诊。',refs=['AASM2021','ATS2013'])
    elif problems or use_concern:
        state, brief, title = 'support','关注佩戴','治疗可能没有覆盖全部睡眠，先改善佩戴'
        f = dict(level='support',title='优先解决佩戴与使用时长',reason='当前有摘机、不适、短用机或用机时长下降的线索，可能影响治疗覆盖。',action='核对入睡、午睡和摘机时段；有面罩不适时联系设备服务人员，仍难以使用或持续困倦则预约门诊。',refs=['ATS-PAP','ATS-MASK'])
    elif rising:
        state, brief, title = 'watch','有变差迹象','呼吸事件明显上升，治疗效果可能在变差'
        f = dict(level='watch',title='先查近期变化，必要时提前复诊',reason='比前期事件频率出现较明确的上升，值得关注。',action='核对面罩、鼻塞、作息及治疗调整日期；接下来一周仍上升，或出现困倦、憋醒，就联系睡眠门诊。',refs=['ATS2013','AASM2021'])
    elif p['frequency'] is None:
        state, brief, title = 'limited','先补记录','先补充有效使用记录，再看治疗方向'
        f = dict(level='unknown',title='先确认数据和实际使用情况',reason='目前没有可计算事件频率的使用记录。',action='更新 SD 卡数据并核对近期是否戴机；若实际难以使用设备，联系设备服务人员或门诊。',refs=['ATS-PAP'])
    elif not enough:
        state, brief, title = 'limited','先看方向','已有记录暂未突出提示问题，继续积累几晚'
        f = dict(level='observe',title='继续记录，优先留意睡醒感受',reason='现有记录没有触发事件或佩戴关注项，但天数较少。',action='按医嘱使用，记录接下来几晚的睡醒感受；持续困倦或憋醒时提前联系医生。',refs=['ATS-PAP','AASM2021'])
    else:
        state, brief = ('improving','可能改善') if falling else ('stable','偏稳定')
        title = '近期呼吸控制可能改善，继续保持' if falling else '近期总体偏稳定，较前期略有改善迹象' if comp['eligible'] and comp['direction']=='down' else '近期总体偏稳定，留意小幅上升' if comp['eligible'] and comp['direction']=='up' else '目前呼吸控制趋势偏稳定'
        if year_rising:
            f = dict(level='watch',title='先观察，复诊时关注长期变化',reason='近期没有明显恶化迹象，但事件频率比去年同期高，长期变化值得核对。',action='继续按医嘱使用，记录睡醒感受；若频率继续上升或症状出现，提前联系门诊。',refs=['ATS2013','AASM2021'])
        else:
            f = dict(level='routine',title='可先观察，按原计划随访',reason='当前记录未触发明显事件增多或佩戴不足的提示，设备趋势暂未突出提示需要因数字提前复诊。',action='继续按医嘱使用；如果仍明显困倦、不解乏或憋醒，就提前联系医生。',refs=['ATS-PAP','AASM2021'])
    answered=sum(c[k]!='unknown' for k in CONTEXT_FIELDS)
    confidence = '中等 · 设备趋势' if enough else '较低 · 记录较少'
    confidence_note = f"摘要覆盖 {p['settled_days']}/{p['calendar_days']} 天，自述已填 {answered}/{len(CONTEXT_FIELDS)} 项。"+'这是方向性判断，不是概率或确诊；事件与原厂 AHI 的映射仍待核对，未填写的症状没有当作不存在。'
    return dict(state=state,brief=brief,title=title,followup=f,reasons=reasons[:5],confidence=confidence,
                confidence_note=confidence_note,rules=ASSESSMENT_RULES,
                signals=dict(frequent=frequent,high_days=high_days,coverage_concern=use_concern,rising=rising,falling=falling,year_rising=year_rising))

def patient_summary(report, rows, locale='zh-CN'):
    from analysis_report import aggregate, CONTEXT_FIELDS, minutes, number
    locale = normalize_locale(locale)
    fields = CONTEXT_FIELDS_EN if locale == 'en-US' else CONTEXT_FIELDS
    glossary = GLOSSARY_EN if locale == 'en-US' else GLOSSARY
    p, c = report['current'], report['context']
    year = aggregate(rows, previous_year(p['start']), previous_year(p['end']))
    comparisons = {
        'previous': compare(p, report['previous'], locale=locale),
        'year': compare(p, year, overlap=year['end'] >= p['start'], locale=locale),
    }
    symptoms = [fields[k] for k in ('unrefreshed','sleepiness','gasping') if c[k] == 'yes']
    assessment = assess(report, comparisons, rows, locale=locale)
    followup = assessment['followup']
    title = assessment['title']
    detail = f"Average treatment time {minutes(p['mean_minutes'], locale)}; estimated respiratory entry index {number(p['frequency'])} entries/hour." if locale == 'en-US' else f"平均戴机 {minutes(p['mean_minutes'])}；呼吸事件指数约 {number(p['frequency'])} 条目/小时。"
    if c['unrefreshed']=='yes':
        feeling = 'Reported: often still unrefreshed after waking' if locale == 'en-US' else '自述：睡醒后经常仍不解乏'
    elif c['unrefreshed']=='no':
        feeling = 'Reported: not often unrefreshed after waking' if locale == 'en-US' else '自述：没有经常睡醒仍不解乏'
    else:
        feeling = 'How you feel after waking has not been recorded yet' if locale == 'en-US' else '还未记录睡醒后的感受'
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
    if locale == 'en-US':
        if symptoms or c['drowsy_driving'] == 'yes':
            safety = [fields['drowsy_driving']] if c['drowsy_driving'] == 'yes' else []
            questions.append('I still have these concerns: ' + '; '.join(symptoms + safety) + '. Do I need further assessment?')
        if c['mask_problem'] == 'yes' or c['mask_off'] == 'yes':
            questions.append('How should I address discomfort or mask-off periods that affect all-night use?')
        questions.extend(QUESTIONS_EN)
    else:
        if symptoms or c['drowsy_driving']=='yes': questions.append('我仍有这些不适：'+'、'.join(symptoms+([CONTEXT_FIELDS['drowsy_driving']] if c['drowsy_driving']=='yes' else []))+'。是否需要进一步评估？')
        if c['mask_problem']=='yes' or c['mask_off']=='yes': questions.append('不适或摘机影响整夜使用，应该怎样处理？')
        questions.extend(['请核对原厂 AHI、血氧与这里的设备事件记录，当前治疗是否充分？','结合我的症状和历史睡眠监测，是否需要调整随访或复查？'])
    if locale == 'en-US':
        boundary = 'Provisional assessment · ' + assessment['confidence'] + ' · ' + ('includes this period\'s self-report' if any(c[k] != 'unknown' for k in CONTEXT_FIELDS) else 'based mainly on device records; waking experience can be added')
        coverage = f"{p['calendar_days']} days: {p['settled_days']} calculable, {p['pending_days']} pending, {p['missing_days']} missing; {p['wave_days']} with waveforms."
    else:
        boundary = '初步评估 · '+assessment['confidence']+' · '+('已结合本期自述' if any(c[k]!='unknown' for k in CONTEXT_FIELDS) else '以设备记录为主，可补充睡醒感受')
        coverage = f"{p['calendar_days']} 天中，{p['settled_days']} 天可计算，{p['pending_days']} 天未结算，{p['missing_days']} 天缺记录；{p['wave_days']} 天有波形。"
    return {'title':title, 'detail':detail, 'feeling':feeling, 'followup':followup,
            'ahi':{'value':None,'status': 'Device event index is directional; manufacturer AHI needs checking' if locale == 'en-US' else '设备事件指数用于观察方向，原厂 AHI 待核对'},
            'assessment':assessment,
            'boundary':boundary,
            'comparisons':comparisons, 'trend':points, 'glossary':glossary,
            'questions':questions[:4], 'context_labels':fields,
            'latest_settled':last['date'] if last else None,
            'coverage':coverage}
