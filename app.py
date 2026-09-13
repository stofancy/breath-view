#!/usr/bin/env python3
"""Breath View: offline desktop GUI and loopback-only preview server."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import argparse, csv, io, json, secrets, threading, sys, os
from datetime import date
from storage import load, import_card, DEFAULT_HOME
from analysis_report import build_report, report_markdown, report_html, validate_context, period

ROOT=Path(__file__).resolve().parent

class Application:
    def __init__(self,home):
        self.home=Path(home)
        self.data=load(self.home)
        self.lock=threading.RLock()
        self.status={'busy':False,'message':'就绪','error':None}
    def context_key(self,start,end):
        period(start,end)
        if not self.data:raise ValueError('请先导入设备数据')
        return self.data.catalog['device']['serial']+'|'+start+'|'+end
    def read_contexts(self):
        path=self.home/'patient-contexts.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    def get_context(self,start,end):
        return self.read_contexts().get(self.context_key(start,end),{})
    def save_context(self,start,end,value):
        with self.lock:
            key=self.context_key(start,end)
            values=self.read_contexts()
            values[key]=validate_context(value)
            self.home.mkdir(parents=True,exist_ok=True,mode=0o700)
            temp=self.home/'patient-contexts.tmp'
            with temp.open('w',encoding='utf-8') as stream:
                os.chmod(temp,0o600)
                json.dump(values,stream,ensure_ascii=False,allow_nan=False)
            os.replace(temp,self.home/'patient-contexts.json')
    def start_import(self,path):
        with self.lock:
            if self.status['busy']:raise ValueError('正在导入，请稍候')
            self.status={'busy':True,'message':'准备导入','error':None}
        def worker():
            try:
                def progress(text):self.status['message']=text
                data=import_card(path,self.home,progress)
                with self.lock:self.data=data
                self.status={'busy':False,'message':'导入完成','error':None}
            except Exception as e:
                self.status={'busy':False,'message':'导入失败','error':str(e)}
        threading.Thread(target=worker,daemon=True).start()


def serve(app,port=0):
    token=secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,value,status=200,kind='application/json; charset=utf-8',filename=None):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode() if kind.startswith('application/json') else value
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(raw)))
            if filename:
                self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        def route(self):
            url=urlparse(self.path)
            prefix='/'+token+'/'
            if not url.path.startswith(prefix):return None,None
            return url.path[len(prefix):],parse_qs(url.query)
        def do_GET(self):
            route,q=self.route()
            if route is None:return self.respond({'error':'Not found'},404)
            try:
                if route=='api/status':return self.respond(app.status)
                if route.startswith('api/'):
                    with app.lock:
                        if not app.data:return self.respond({'empty':True})
                        if route=='api/overview':return self.respond(app.data.overview())
                        if route in ('api/report','api/report.md','api/report.html'):
                            start=q.get('start',[''])[0];end=q.get('end',[''])[0]
                            report=build_report(app.data,start,end,app.get_context(start,end))
                            if route.endswith('.html'):
                                return self.respond(report_html(report).encode(),kind='text/html; charset=utf-8',filename=f'pap-review-{start}-{end}.html')
                            if route.endswith('.md'):
                                return self.respond(report_markdown(report).encode(),kind='text/markdown; charset=utf-8',filename=f'pap-review-{start}-{end}.md')
                            return self.respond(report)
                        if route=='api/day':return self.respond(app.data.detail(q.get('date',[''])[0],q.get('start',[None])[0],q.get('end',[None])[0]))
                        if route=='api/export':
                            days=app.data.overview()['days']
                            start=date.fromisoformat(q.get('start',[days[0]['date']])[0]).isoformat()
                            end=date.fromisoformat(q.get('end',[days[-1]['date']])[0]).isoformat()
                            if start>end:raise ValueError('开始日期晚于结束日期')
                            s=io.StringIO();w=csv.writer(s)
                            w.writerow(['治疗日（中午起）','设备使用分钟（历史摘要）','OSA记录条目','CSA记录条目','HYP记录条目','事件记录频率（条目每小时，估算）','保留波形','摘要状态'])
                            for d in days:
                                if start<=d['date']<=end:
                                    w.writerow([d['date'],d['minutes'],*[d['counts'][k] for k in ('OSA','CSA','HYP')],d['index'],'有' if d['wave'] else '无','未结算' if d['current'] else '已结算'])
                            return self.respond(('\ufeff'+s.getvalue()).encode(),kind='text/csv; charset=utf-8',filename=f'breath-summary-{start}-{end}.csv')
                    return self.respond({'error':'Not found'},404)
                assets={'':('index.html','text/html; charset=utf-8'),'app.js':('app.js','text/javascript; charset=utf-8'),'report.js':('report.js','text/javascript; charset=utf-8'),'style.css':('style.css','text/css; charset=utf-8'),'icon.svg':('icon.svg','image/svg+xml')}
                if route not in assets:return self.respond({'error':'Not found'},404)
                name,kind=assets[route]
                return self.respond((ROOT/'web'/name).read_bytes(),kind=kind)
            except (ValueError,OSError,KeyError) as e:self.respond({'error':str(e)},400)
        def do_POST(self):
            route,q=self.route()
            # Random capability URL + no CORS + same-origin JSON requests.
            if route not in ('api/import','api/context'):return self.respond({'error':'Not found'},404)
            if self.headers.get('Content-Type')!='application/json':return self.respond({'error':'JSON required'},415)
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':return self.respond({'error':'Forbidden'},403)
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<8192:raise ValueError('请求长度无效')
                payload=json.loads(self.rfile.read(n))
                if route=='api/import':
                    app.start_import(payload['path']);self.respond({'started':True})
                else:
                    app.save_context(payload['start'],payload['end'],payload['context'])
                    self.respond({'saved':True})
            except (ValueError,KeyError,TypeError,OSError) as e:self.respond({'error':str(e)},400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server,f'http://127.0.0.1:{server.server_port}/{token}/'


def main():
    parser=argparse.ArgumentParser(description='息览 · BMC 呼吸机数据查看器')
    parser.add_argument('--home',type=Path,default=DEFAULT_HOME)
    parser.add_argument('--import-card',type=Path)
    parser.add_argument('--serve',action='store_true',help='只启动本地浏览器服务')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    if args.import_card:
        data=import_card(args.import_card,args.home,lambda s:print(s,flush=True))
        print(json.dumps({'days':len(data.days),'wave_days':len(data.catalog['spans']),'invalid':data.catalog['invalid_packets']},ensure_ascii=False))
        return
    app=Application(args.home)
    server,url=serve(app,args.port)
    if args.serve:
        print(url,flush=True)
        try:threading.Event().wait()
        except KeyboardInterrupt:server.shutdown()
        return
    from PySide6.QtWidgets import QApplication,QMainWindow,QToolBar,QFileDialog
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QAction,QIcon,QDesktopServices
    qt=QApplication(sys.argv)
    qt.setApplicationName('息览 · Breath View')
    qt.setWindowIcon(QIcon(str(ROOT/'web/icon.svg')))
    win=QMainWindow();win.setWindowTitle('息览 · 呼吸机数据');win.resize(1440,1000)
    view=QWebEngineView()
    # Off-the-record profile: no medical data left in an embedded browser cache.
    profile=QWebEngineProfile(view)
    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self,target,kind,is_main):
            if target.scheme() in ('http','https') and target.host()!='127.0.0.1':
                QDesktopServices.openUrl(target)
                return False
            return super().acceptNavigationRequest(target,kind,is_main)
    page=LocalPage(profile,view);view.setPage(page)
    def download(item):
        suggested=Path(item.downloadFileName() or 'breath-export.csv').name
        suffix=Path(suggested).suffix.lower()
        file_filter={'.html':'HTML 报告 (*.html)','.md':'Markdown 报告 (*.md)','.csv':'CSV 摘要 (*.csv)'}.get(suffix,'所有文件 (*)')
        target,_=QFileDialog.getSaveFileName(win,'保存报告或摘要',str(Path.home()/'Documents'/suggested),file_filter)
        if target:
            item.setDownloadDirectory(str(Path(target).parent));item.setDownloadFileName(Path(target).name);item.accept()
    profile.downloadRequested.connect(download)
    win.setCentralWidget(view)
    toolbar=QToolBar();toolbar.setMovable(False);win.addToolBar(toolbar)
    choose=QAction('选择 SD 卡 / 备份文件夹',win)
    def select():
        path=QFileDialog.getExistingDirectory(win,'选择含有 .USR 文件的 SD 卡根目录','/run/media')
        if path:view.page().runJavaScript('window.chooseFolder('+json.dumps(path)+')')
    choose.triggered.connect(select);toolbar.addAction(choose)
    refresh=QAction('刷新视图',win);refresh.triggered.connect(view.reload);toolbar.addAction(refresh)
    toolbar.setStyleSheet('QToolBar { background:#e7ebee; padding:3px; border:0; } QToolButton { padding:5px 10px; color:#334b5c; }')
    view.setUrl(QUrl(url));win.show()
    qt.aboutToQuit.connect(server.shutdown)
    sys.exit(qt.exec())

if __name__=='__main__':main()
