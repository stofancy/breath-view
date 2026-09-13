#!/usr/bin/env python3
"""Breath View: offline desktop GUI and loopback-only preview server."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import argparse, csv, io, json, secrets, threading, sys, os, logging, time, subprocess, tempfile
from logging.handlers import RotatingFileHandler
from datetime import date
from storage import load, import_source, DEFAULT_HOME, MAX_ARCHIVE_BYTES
from analysis_report import build_report, report_markdown, report_html, validate_context, period
from portable_report import mobile_html, mobile_pdf

ROOT=Path(__file__).resolve().parent
LOG_NAME='breath-view.log'


def configure_logging(home):
    """Write a small, private rotating trace for standalone troubleshooting."""
    home=Path(home).expanduser().resolve()
    home.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=home/LOG_NAME
    handler=RotatingFileHandler(path,maxBytes=2*1024*1024,backupCount=2,encoding='utf-8')
    os.chmod(path,0o600)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(threadName)s] %(message)s',
        handlers=[handler],
        force=True,
    )
    logging.info('startup pid=%s cwd=%s home=%s argv=%s',os.getpid(),Path.cwd(),home,sys.argv)
    return path

class Application:
    def __init__(self,home):
        self.home=Path(home)
        self.data=load(self.home)
        self.lock=threading.RLock()
        self.status={'busy':False,'message':'就绪','error':None}
        logging.info('data loaded=%s source=%s',bool(self.data),self.data.catalog.get('source') if self.data else '')
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
            logging.info('context saved start=%s end=%s',start,end)
    def start_import(self,path, cleanup=False, reserved=False):
        with self.lock:
            if self.status['busy'] and not reserved:raise ValueError('正在导入，请稍候')
            self.status={'busy':True,'message':'准备导入','error':None}
        logging.info('import requested source=%s',Path(path).expanduser())
        def worker():
            try:
                def progress(text):
                    self.status['message']=text
                    logging.info('import progress %s',text)
                data=import_source(path,self.home,progress)
                with self.lock:self.data=data
                self.status={'busy':False,'message':'导入完成','error':None}
                logging.info('import finished source=%s',data.catalog.get('source'))
            except Exception as e:
                self.status={'busy':False,'message':'导入失败','error':str(e)}
                logging.exception('import failed')
            finally:
                if cleanup:Path(path).unlink(missing_ok=True)
        threading.Thread(target=worker,daemon=True).start()


def serve(app,port=0,host='127.0.0.1'):
    remote=host not in ('127.0.0.1','localhost')
    if remote:
        token_path=app.home/'access-token'
        if not token_path.exists():
            with token_path.open('x') as stream:
                os.chmod(token_path,0o600)
                stream.write(secrets.token_urlsafe(32))
        token=token_path.read_text().strip()
        if len(token)<32 or not all(c.isalnum() or c in '-_' for c in token):raise ValueError('访问令牌格式无效')
    else:token=secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,value,status=200,kind='application/json; charset=utf-8',filename=None):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode() if kind.startswith('application/json') else value
            started=getattr(self,'_request_started',None)
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(raw)))
            if filename:
                self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
            if started is not None:
                logging.info('http %s %s status=%s bytes=%s duration_ms=%.1f',self.command,urlparse(self.path).path.replace(token,'[access]'),status,len(raw),(time.monotonic()-started)*1000)
        def route(self):
            url=urlparse(self.path)
            prefix='/'+token+'/'
            if not url.path.startswith(prefix):return None,None
            return url.path[len(prefix):],parse_qs(url.query)
        def do_GET(self):
            self._request_started=time.monotonic()
            route,q=self.route()
            if route is None:return self.respond({'error':'Not found'},404)
            try:
                if route=='api/status':return self.respond({**app.status,'local_paths':not remote})
                # Build a consistent snapshot under the data lock, then release it
                # before starting PDF rendering so navigation stays responsive.
                if route in ('api/mobile.html','api/mobile.pdf'):
                    with app.lock:
                        if not app.data:raise ValueError('请先导入设备数据')
                        start=q.get('start',[''])[0];end=q.get('end',[''])[0]
                        report=build_report(app.data,start,end,app.get_context(start,end))
                    if route.endswith('.pdf'):
                        logging.info('mobile pdf export started start=%s end=%s',start,end)
                        raw=mobile_pdf(report)
                        return self.respond(raw,kind='application/pdf',filename=f'pap-phone-{start}-{end}.pdf')
                    return self.respond(mobile_html(report).encode(),kind='text/html; charset=utf-8',filename=f'pap-phone-{start}-{end}.html')
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
            except (ValueError,OSError,KeyError,subprocess.TimeoutExpired) as e:
                logging.exception('GET failed route=%s',route)
                self.respond({'error':str(e)},400)
        def do_POST(self):
            self._request_started=time.monotonic()
            route,q=self.route()
            if route not in ('api/import','api/context','api/upload'):return self.respond({'error':'Not found'},404)
            origin=self.headers.get('Origin')
            if origin and origin not in ('http://'+self.headers.get('Host',''), 'https://'+self.headers.get('Host','')):
                return self.respond({'error':'Forbidden'},403)
            if route=='api/upload':
                upload=None
                with app.lock:
                    if app.status['busy']:return self.respond({'error':'正在导入，请稍候'},409)
                    app.status={'busy':True,'message':'正在接收 ZIP','error':None}
                try:
                    if self.headers.get('Content-Type') not in ('application/zip','application/octet-stream'):raise ValueError('请上传 ZIP 文件')
                    n=int(self.headers.get('Content-Length','0'))
                    if not 0<n<=MAX_ARCHIVE_BYTES:raise ValueError('ZIP 文件大小须在 1 字节至 8 GiB 之间')
                    self.connection.settimeout(120)
                    with tempfile.NamedTemporaryFile(prefix='.upload-',suffix='.zip',dir=app.home,delete=False) as stream:
                        upload=Path(stream.name)
                        remaining=n
                        while remaining:
                            chunk=self.rfile.read(min(1024*1024,remaining))
                            if not chunk:raise ValueError('上传中断，请重新上传')
                            stream.write(chunk);remaining-=len(chunk)
                            app.status['message']=f'正在接收 ZIP · {(n-remaining)*100//n}%'
                    app.start_import(upload,cleanup=True,reserved=True)
                    upload=None
                    return self.respond({'started':True})
                except (ValueError,OSError) as e:
                    app.status={'busy':False,'message':'上传失败','error':str(e)}
                    logging.exception('upload failed')
                    return self.respond({'error':str(e)},400)
                finally:
                    if upload:upload.unlink(missing_ok=True)
            if route=='api/import' and remote:return self.respond({'error':'请通过 ZIP 上传本机数据'},403)
            if self.headers.get('Content-Type')!='application/json':return self.respond({'error':'JSON required'},415)
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<8192:raise ValueError('请求长度无效')
                payload=json.loads(self.rfile.read(n))
                if route=='api/import':
                    app.start_import(payload['path']);self.respond({'started':True})
                else:
                    logging.info('context save requested start=%s end=%s',payload.get('start'),payload.get('end'))
                    app.save_context(payload['start'],payload['end'],payload['context'])
                    self.respond({'saved':True})
            except (ValueError,KeyError,TypeError,OSError) as e:
                logging.exception('POST failed route=%s',route)
                self.respond({'error':str(e)},400)
    server=ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}/{token}/'
    logging.info('server listening url=%s',url)
    return server,url


def main():
    parser=argparse.ArgumentParser(description='息览 · BMC 呼吸机数据查看器')
    parser.add_argument('--home',type=Path,default=DEFAULT_HOME)
    parser.add_argument('--import-card',type=Path)
    parser.add_argument('--serve',action='store_true',help='只启动本地浏览器服务')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--host',default='127.0.0.1',help='服务监听地址，NAS 使用 0.0.0.0')
    parser.add_argument('source',nargs='?',type=Path,help='打开文件夹、.USR 或 ZIP')
    args=parser.parse_args()
    if args.import_card:
        configure_logging(args.home)
        data=import_source(args.import_card,args.home,lambda s:print(s,flush=True))
        print(json.dumps({'days':len(data.days),'wave_days':len(data.catalog['spans']),'invalid':data.catalog['invalid_packets']},ensure_ascii=False))
        return
    log_path=configure_logging(args.home)
    logging.info('mode=%s log=%s', 'serve' if args.serve else 'gui',log_path)
    app=Application(args.home)
    if not args.serve and args.host!='127.0.0.1':parser.error('桌面模式仅支持本机监听')
    server,url=serve(app,args.port,args.host)
    if args.source:app.start_import(args.source)
    if args.serve:
        print(url,flush=True)
        try:threading.Event().wait()
        except KeyboardInterrupt:server.shutdown()
        return
    from PySide6.QtWidgets import QApplication,QMainWindow,QToolBar,QFileDialog
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile
    from PySide6.QtCore import QUrl, qVersion
    from PySide6.QtGui import QAction,QIcon,QDesktopServices
    qt=QApplication(sys.argv)
    qt.setApplicationName('息览 · Breath View')
    qt.setWindowIcon(QIcon(str(ROOT/'web/icon.svg')))
    logging.info('qt initialized version=%s platform=%s',qVersion(),os.environ.get('QT_QPA_PLATFORM','default'))
    win=QMainWindow();win.setWindowTitle('息览 · 呼吸机数据');win.resize(1440,1000)
    view=QWebEngineView()
    # Off-the-record profile: no medical data left in an embedded browser cache.
    profile=QWebEngineProfile(view)
    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self,target,kind,is_main):
            logging.info('navigation request url=%s main=%s kind=%s',target.toString(),is_main,kind)
            if target.scheme() in ('http','https') and target.host()!='127.0.0.1':
                QDesktopServices.openUrl(target)
                return False
            return super().acceptNavigationRequest(target,kind,is_main)
        def javaScriptConsoleMessage(self,level,message,line_number,source_id):
            logging.info('js console level=%s source=%s line=%s message=%s',level,source_id,line_number,message)
            super().javaScriptConsoleMessage(level,message,line_number,source_id)
    page=LocalPage(profile,view);view.setPage(page)
    view.loadStarted.connect(lambda:logging.info('web load started'))
    view.loadProgress.connect(lambda value:logging.info('web load progress=%s',value) if value in (0,25,50,75,100) else None)
    view.loadFinished.connect(lambda ok:logging.info('web load finished ok=%s url=%s',ok,view.url().toString()))
    page.renderProcessTerminated.connect(lambda status,code:logging.error('web render process terminated status=%s exit_code=%s',status,code))
    def download(item):
        suggested=Path(item.downloadFileName() or 'breath-export.csv').name
        suffix=Path(suggested).suffix.lower()
        file_filter={'.pdf':'手机 PDF (*.pdf)','.html':'HTML 报告 (*.html)','.md':'Markdown 报告 (*.md)','.csv':'CSV 摘要 (*.csv)'}.get(suffix,'所有文件 (*)')
        logging.info('download save dialog opened filename=%s',suggested)
        target,_=QFileDialog.getSaveFileName(win,'保存报告或摘要',str(Path.home()/'Documents'/suggested),file_filter)
        logging.info('download save dialog closed selected=%s',bool(target))
        if target:
            item.stateChanged.connect(lambda state:logging.info('download state=%s filename=%s',state,suggested))
            item.setDownloadDirectory(str(Path(target).parent));item.setDownloadFileName(Path(target).name);item.accept()
    profile.downloadRequested.connect(download)
    win.setCentralWidget(view)
    toolbar=QToolBar();toolbar.setMovable(False);win.addToolBar(toolbar)
    choose=QAction('选择 SD 卡 / 备份文件夹',win)
    def select():
        logging.info('native folder dialog opened')
        path=QFileDialog.getExistingDirectory(win,'选择含有 .USR 文件的 SD 卡根目录','/run/media')
        logging.info('native folder dialog closed selected=%s',bool(path))
        if path:view.page().runJavaScript('window.chooseFolder('+json.dumps(path)+')')
    choose.triggered.connect(select);toolbar.addAction(choose)
    open_file=QAction('打开 .USR / ZIP',win)
    def select_file():
        path,_=QFileDialog.getOpenFileName(win,'打开呼吸机数据',str(Path.home()),'呼吸机数据 (*.USR *.usr *.zip *.ZIP)')
        if path:view.page().runJavaScript('window.chooseFolder('+json.dumps(path)+')')
    open_file.triggered.connect(select_file);toolbar.addAction(open_file)
    refresh=QAction('刷新视图',win)
    refresh.triggered.connect(lambda:(logging.info('manual refresh requested'),view.reload()))
    toolbar.addAction(refresh)
    toolbar.setStyleSheet('QToolBar { background:#e7ebee; padding:3px; border:0; } QToolButton { padding:5px 10px; color:#334b5c; }')
    view.setUrl(QUrl(url));win.show()
    logging.info('gui shown url=%s',url)
    qt.aboutToQuit.connect(lambda:logging.info('application quitting'))
    qt.aboutToQuit.connect(server.shutdown)
    sys.exit(qt.exec())

if __name__=='__main__':main()
