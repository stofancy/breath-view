"""Offline phone-sized report. PDF rendering uses the app's existing Qt runtime.

A short-lived offscreen process owns the Qt GUI/font state for PDF rendering;
HTTP threads never touch the desktop's QApplication or block its event loop.
"""
import html
import json
import os
from pathlib import Path
import subprocess
import sys
from analysis_report import minutes, number


def mobile_sections(report):
    e = lambda v: html.escape(str(v))
    p, v, c = report['current'], report['patient'], report['context']
    f = v['followup']
    blocks = []
    comparisons = []
    for key, label in [('previous','前一等长期间'),('year','去年同期')]:
        comp = v['comparisons'][key]; other = comp['period']
        use = ''
        if comp['minutes_delta'] is not None:
            diff = comp['minutes_delta']
            use = f"；平均戴机{'增加' if diff >= 0 else '减少'} {abs(diff):.0f} 分钟"
        comparisons.append(f"<h3>{label} · {e(comp['text'])}</h3><p>{e(other['start'])} 至 {e(other['end'])}，{other['settled_days']}/{other['calendar_days']} 天可计算。</p><p>每小时记录 {number(other['frequency'])} → {number(p['frequency'])}{e(use)}。</p>" if comp['eligible'] else f"<h3>{label}</h3><p>{e(other['start'])} 至 {e(other['end'])}：{e(comp['text'])}（{other['settled_days']}/{other['calendar_days']} 天可计算）。</p>")
    blocks.append(('近期治疗与下一步',f"""
        <div class="lead"><h2>{e(v['title'])}</h2><p>{e(v['detail'])}</p></div>
        <p class="note">{e(v['boundary'])}</p><h3>主要判断依据</h3><ul>{''.join('<li>'+e(reason)+'</li>' for reason in v['assessment']['reasons'][:3])}</ul>
        <h3>需要找医生吗</h3><p><b>{e(f['title'])}</b></p><p>{e(f['reason'])}</p><p>{e(f['action'])}</p>
        {''.join(comparisons)}"""))
    context = ''.join(f"<p><b>{e(label)}</b><br>{ {'yes':'是','no':'否','unknown':'未填写'}[c[key]] }</p>" for key,label in v['context_labels'].items())
    blocks.append(('我的感受与复诊问题',f"""<p class="note">以下为 {e(p['start'])} 至 {e(p['end'])} 的患者自述；未填写保持未知。</p>
        <p><b>平均每天睡眠（含午睡）</b><br>{e(str(c['sleep_hours'])+' 小时' if c['sleep_hours'] is not None else '未填写')}</p>
        {context}<h3>希望医生帮助确认</h3><ol>{''.join('<li>'+e(q)+'</li>' for q in v['questions'])}</ol>"""))
    # Keep long user notes off the leading summary pages. All notes remain included.
    if c['note']:
        blocks.append(('补充备注 · 患者自述','<p>'+e(c['note']).replace('\n','<br>')+'</p>'))
    days = ''.join(f"<p><b>{e(d['date'])}</b> · {number(d['frequency'])} 条目/小时<br>戴机 {e(minutes(d['minutes']))} · {'有' if d['wave'] else '无'}波形<br>{e('；'.join(d['reasons']))}</p>" for d in report['review_days'][:5])
    blocks.append(('供医生核对的数据',f"""
        <p>{e(v['coverage'])}</p><p><b>期间合计</b><br>戴机 {e(minutes(p['total_minutes']))}；{p['use_days']} 天有使用，记录日平均 {e(minutes(p['mean_minutes']))}。</p>
        <p><b>设备事件记录</b><br>OSA 阻塞性暂停 {p['counts']['OSA']} 条<br>CSA 中枢性暂停 {p['counts']['CSA']} 条<br>HYP 低通气 {p['counts']['HYP']} 条</p>
        <p>合计 {sum(p['counts'].values())} 条 ÷ {number(p['total_minutes']/60)} 戴机小时 = {number(p['frequency'])} 条目/小时。</p>
        <h3>重点日期（排序不等于诊断）</h3>{days or '<p>暂无可供筛选的记录。</p>'}
        <p class="note">摘要可能完整而波形缺失；本页只有摘要数字，不包含原始波形。波形与原始卡另行携带或在电脑上核对。</p>"""))
    blocks.append(('解释范围与来源',f"""
        <p>设备：{e(report['device'].get('model','未知'))}<br>数据导入：{e(report.get('imported_at') or '未记录')}<br>生成：{e(report['generated_at'])}<br>解析/分析规则：{e(report['version'])} · 设备时钟</p>
        <h3>这份摘要如何使用</h3><p>从本地 SD 卡副本解析，尚未与原厂逐项核对。事件条目可能按分钟聚合；频率使用戴机时间作分母。缺失和未结算日不作零使用。治疗日从中午 12 点起算。</p>
        <p>{e(report['comparison']['rule'])} 去年同期按同一月日对齐，闰日取 2 月 28 日；重叠期间不自动比较。</p>
        <p>没有已解析的血氧、实际睡眠时长、睡眠分期和觉醒数据；不能判定治疗已达标或自行调整压力。请结合原厂报告、原睡眠监测及症状判断。</p>
        <h3>初步判断如何得出</h3><p>{e(v['assessment']['confidence_note'])}</p><ul>{''.join('<li>'+e(rule)+'</li>' for rule in v['assessment']['rules'])}</ul>
        <h3>主要依据</h3><ul>{''.join('<li><a href="'+e(s['url'])+'">'+e(s['title'])+'</a></li>' for s in report['sources'])}</ul>"""))
    return blocks


def mobile_html(report):
    e = lambda v: html.escape(str(v))
    p = report['current']
    blocks = mobile_sections(report)
    body = ''.join(f'<section><h2 class="section-title">{e(title)}</h2>{content}</section>' if i < 2 else f'<details><summary>{e(title)}</summary>{content}</details>' for i,(title,content) in enumerate(blocks))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>睡眠呼吸治疗复诊摘要 {e(p['end'])}</title>
<style>*{{box-sizing:border-box}}body{{font:16px/1.75 "Noto Sans CJK SC",sans-serif;color:#294553;background:#eef3f4;margin:0;overflow-wrap:anywhere}}main{{max-width:560px;margin:auto;background:#fff;padding:24px 20px;min-height:100vh}}header{{border-top:4px solid #406d7d;padding-top:16px}}h1{{font-size:25px;line-height:1.4;margin:8px 0}}h2{{font-size:21px;line-height:1.5}}h3{{font-size:17px;margin:20px 0 6px}}p{{margin:10px 0}}.kicker,.note{{font-size:13px;color:#637b85}}.lead{{border-left:3px solid #568696;padding:1px 0 1px 14px;margin:18px 0}}.section-title{{font-size:18px;color:#3e697a}}section,details{{border-top:1px solid #cfdbdf;margin-top:24px;padding-top:14px}}summary{{font-weight:bold;cursor:pointer;padding:6px 0}}a{{color:#276884}}li{{margin-bottom:10px}}ul,ol{{padding-left:23px}}footer{{margin-top:30px;font-size:12px;color:#6c8089}}@media print{{body{{background:#fff}}main{{max-width:none;padding:0}}section{{break-before:page}}header+section{{break-before:auto}}details{{display:block}}}}</style></head><body><main><header><div class="kicker">息览 · 手机复诊摘要</div><h1>睡眠呼吸治疗记录</h1><p>{e(p['start'])} 至 {e(p['end'])}<br>{e(report['device'].get('model','未知'))}</p><p class="note">已保存的设备记录与患者自述 · 文件可离线查看</p></header>{body}<footer>序列号不写入此摘要。请同时携带原睡眠监测报告与设备资料。</footer></main></body></html>'''


def pdf_document_html(report, section_index):
    e = lambda v: html.escape(str(v))
    p = report['current'];blocks=mobile_sections(report)
    content=[]
    for i,(title,body) in enumerate(blocks):
        if i != section_index:continue
        content.append(f'<div style="page-break-before:auto"><p class="meta">息览 · 手机复诊摘要 · {i+1}/{len(blocks)} 节</p><h1>{e(title)}</h1><p class="meta">{e(p["start"])} 至 {e(p["end"])} · {e(report["device"].get("model","未知"))}</p>{body}</div>')
    return '''<html><head><meta charset="utf-8"><style>body{font-family:"Droid Sans Fallback";font-size:10.5pt;color:#294553}h1{font-size:18pt;margin-bottom:12px}h2{font-size:14pt}h3{font-size:11.5pt;margin-top:16px;margin-bottom:6px}p{margin-top:6px;margin-bottom:8px;line-height:135%}.meta,.note{font-size:8.5pt;color:#627780}a{color:#276884}li{margin-bottom:8px}</style></head><body>'''+''.join(content)+'</body></html>'


def mobile_pdf(report):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--render-pdf'],
        input=json.dumps(report,ensure_ascii=False,allow_nan=False).encode(),capture_output=True,env=env,timeout=45)
    if result.returncode or not result.stdout.startswith(b'%PDF-'):
        raise ValueError('手机 PDF 生成失败，请重试或先下载离线网页。')
    return result.stdout


def render_pdf_process(report):
    from PySide6.QtGui import QGuiApplication, QPdfWriter, QPageSize, QPageLayout, QTextDocument, QFont, QPainter
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSizeF, QMarginsF
    app = QGuiApplication(['breath-view-pdf'])
    raw=QByteArray();buffer=QBuffer(raw);buffer.open(QIODevice.WriteOnly)
    writer=QPdfWriter(buffer)
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QSizeF(108,240),QPageSize.Millimeter,'Phone'))
    writer.setPageMargins(QMarginsF(8,8,8,8),QPageLayout.Millimeter)
    writer.setTitle('睡眠呼吸治疗复诊摘要')
    writer.setCreator('息览 Breath View')
    painter=None
    # One phone-width page per section, sized to its text. This avoids cutting a
    # Chinese line across a page boundary or creating near-empty continuation pages.
    for i in range(len(mobile_sections(report))):
        doc=QTextDocument();doc.setDefaultFont(QFont('Droid Sans Fallback',10))
        doc.setDocumentMargin(0)
        doc.documentLayout().setPaintDevice(writer)
        doc.setHtml(pdf_document_html(report,i))
        doc.setTextWidth(writer.width())
        height_mm=doc.size().height()*25.4/writer.resolution()+20
        writer.setPageSize(QPageSize(QSizeF(108,max(150,height_mm)),QPageSize.Millimeter,'Phone'))
        if painter is None:painter=QPainter(writer)
        else:writer.newPage()
        doc.drawContents(painter)
    painter.end()
    del writer
    buffer.close()
    sys.stdout.buffer.write(bytes(raw))


if __name__=='__main__':
    if sys.argv[1:] != ['--render-pdf']:raise SystemExit('仅供 PDF 导出子进程调用')
    render_pdf_process(json.load(sys.stdin))
