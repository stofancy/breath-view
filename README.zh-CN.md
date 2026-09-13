# Breath View · 息览

**语言：** [English](README.md) · 简体中文

> 中文翻译供阅读便利；如有措辞差异，以 [English README](README.md) 为准。

Breath View（息览）是一个本地优先的 BMC U-20A PAP/CPAP SD 卡数据查看器。
它以只读方式导入数据副本，展示治疗摘要和保留波形，并生成谨慎、带证据边界的复诊参考。

![息览仪表盘预览](docs/demo-dashboard.png)

> 此预览使用合成的非医疗演示数据。请勿公开包含真实个人日期、设备序列号、症状或治疗指标的截图。

## 功能

- **睡眠概览**：治疗时长、估算的设备事件记录频率、期间比较和患者自述。
- **每日详情**：流量、吸气压力 IPAP、呼气压力 EPAP、漏气和可选通气指标，以及事件标记和波形统计。
- **期间统计**：自定义日期范围，并区分缺失摘要、未结算日期和缺失波形。
- **离线导出**：CSV、自包含 HTML 复诊报告，以及手机尺寸的 HTML/PDF 摘要。
- **治疗时间线**：可选的、按设备隔离的面罩、医生调整、舒适设置和生活变化记录。
- **中英文界面**：支持 `zh-CN` 和 `en-US`，语言选择保存在浏览器本地。

解析器遵循保守原则：设备事件不会被称为已验证的临床 AHI；项目不推测血氧、睡眠分期或压力处方。

## 快速开始

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 导入一个文件夹、一个 .USR 文件，或一张卡的 ZIP 备份。
python3 app.py --import-card /path/to/card

# 启动本地浏览器服务，并把终端打印的地址复制到浏览器。
python3 app.py --serve
```

桌面 GUI 可运行 `./launch.sh`。GUI 提供文件和文件夹选择器；源 SD 卡始终只读，
数据会被复制到本地私有归档。

运行测试：

```sh
python3 -m unittest -v
```

## 数据与隐私

默认归档目录为 `~/.local/share/breath-view/`。导入会创建独立快照，只有完整解析成功后
才切换 `current` 指针；不会自动删除旧快照，也不会修改源 SD 卡。

默认服务只监听回环地址，并使用随机 capability URL。远程部署必须自行增加 TLS 和认证边界；
不要把应用直接暴露到公网，也不要分享包含健康数据的 capability URL。患者自述和治疗时间线
分别存储，并使用私有文件权限；日志不会记录自述内容或备注正文。

请勿提交 `.USR`、编号波形文件、`.idx`、`.evt`、`.log`、导出报告、
`patient-contexts.json`、访问令牌或部署密钥。公开 push 前请检查 `git diff --cached`。

## 支持范围与已知限制

当前验证的输入是 [FORMAT.md](FORMAT.md) 描述的 BMC U-20A 格式。解析使用 USR 摘要和同名
编号波形文件；当前导入路径不使用 `.idx` 和 `.evt` 文件。

事件指数是设备条目数除以已结算治疗小时数得到的估算值。缺失摘要不按零使用处理，
未结算日期不参与平均，保留波形时长不替代摘要中的治疗时长。通道语义和事件分类仍需
逐项与原厂软件比较后，才能支持更强的临床表述。

本项目是记录复核辅助工具，不是医疗器械、诊断工具或治疗处方系统。请与合格的临床医生
讨论结果，遵循制造商说明；不要根据本软件自行修改压力设置。困倦时不要驾驶或操作危险设备。

## 自托管

Docker 镜像在 `8080` 端口提供相同的本地 Web 界面，并将数据持久化到 `/data`：

```sh
docker build -t breath-view .
docker run --rm -p 127.0.0.1:8080:8080 -v breath-view-data:/data breath-view
```

[`deploy/`](deploy/) 中的文件只是公开示例。使用非回环监听前，请替换所有占位符，
把 OAuth 客户端凭据放在 Git 之外，并在可信反向代理处终止 TLS。详见
[`deploy/README.md`](deploy/README.md)。

## 项目说明、贡献与许可

- [FORMAT.md](FORMAT.md)：已解析字段和证据边界。
- [docs/peer-reference-review.md](docs/peer-reference-review.md)：不复制第三方代码的格式比较记录。
- 前端是无依赖的原生 HTML/CSS/JavaScript；后端使用 Python，桌面 GUI/PDF 路径可选用 PySide6。
- 贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题请见 [SECURITY.md](SECURITY.md)。
- 项目采用 [MIT License](LICENSE)。
