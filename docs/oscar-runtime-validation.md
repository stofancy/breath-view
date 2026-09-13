# OSCAR 2.0.1 本机运行验证

日期：2026-09-13

本记录只覆盖“能否在当前 Fedora 主机上隔离启动官方 OSCAR 2.0.1，以及实际导入的阻碍”。没有安装系统软件包、没有编译 OSCAR、没有改动用户已有 OSCAR 配置，也没有写入 SD 卡或上传数据。

## 已验证

主机为 Fedora 44 x86_64。当前没有安装 OSCAR；Flatpak 搜索结果是 1.7.1，不能作为 2.0.1 的对照版本。

选择了官方 Debian 12 x86_64 包，仅下载并解包到实验目录：

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/
```

包文件为：

```text
oscar20_2.0.1-Debian12_amd64-Qt6.deb
```

SHA-256 为：

```text
9aa45a8f14ab520685d098961c875bd6b78e18b88a51527a78ca64c651c4fa56
```

该值与 OSCAR 官方校验文件一致：
<https://www.sleepfiles.com/OSCAR/2.0.1/OSCAR20-2.0.1-checksums.txt>

包的运行时依赖是 `libqt6printsupport6`、`libqt6openglwidgets6`、`libqt6xml6`、`libqt6serialport6` 和 `libqt6sql6`。通过 `ldd` 检查，当前主机能够解析这些动态库，没有发现 `not found`。

使用独立的 XDG 配置、数据、缓存和运行目录，以避免接触用户目录：

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/isolated/
```

在 `QT_QPA_PLATFORM=offscreen QT_OPENGL=software` 下启动 20 秒，进程进入 Qt 事件循环并只输出：

```text
Warning: This plugin does not support propagateSizeHints()
```

随后由测试超时退出（exit 124）。隔离目录没有产生数据库或配置文件。这证明包和 Qt 依赖可以启动到 GUI 事件循环；它没有证明已经导入数据。

## SD 卡文件与 OSCAR 依赖

当前 SD 卡根目录的实际文件组为 `20C03296`：一个 `.USR`、一个 `.idx`、一个 `.evt`、一个 `.log`，以及 `.000` 到 `.029` 共 30 个编号波形文件。`.idx` 约 1.00 GiB；每个编号波形文件约 16 MiB。

下面两类证据要分开看：

| 结论 | 证据性质 |
| --- | --- |
| 当前 OSCAR legacy loader 的目录检测要求恰好一个 `.USR`，并要求同 stem 的 `.idx` 和 `.000` | 已缓存的 `bmcDataParsing.cpp` 源码：`DirectoryHasBmcData()` |
| `.idx` 读取每日设置及 `.nnn` 波形起止文件/偏移，`.USR` 读取会话 | 已缓存的 loader 源码与 `BmcCpapData` 文档 |
| `.evt` 包含会话附加设置，`.log` 是设备日志 | `BmcCpapData` 文档；没有用本机 OSCAR 实际导入确认 |
| OSCAR 2.0.1 支持 BMC G3/B20A legacy，并修复缺失 SD 数据处理 | 官方 2.0.1 发布说明 |

因此，真正用于对账的压缩包应保留整组文件。只选 `.USR` 或只选 `.USR + .000` 会丢失 OSCAR 需要的索引或历史波形；这是导入前的文件完整性判断，不是本机成功导入后的结果。

## 实际导入状态

本轮没有完成真实 OSCAR 导入，也没有生成 OSCAR CSV/SQLite 对账结果。当前可用的界面控制面只暴露浏览器，没有可控制的原生 OSCAR 窗口；主机也没有 `Xvfb`、`xdotool` 或 `wmctrl`。OSCAR 没有在本轮找到可直接传入 SD 路径并完成导入的无 GUI 命令行入口。

所以目前的最小人工验证路径仍是：在可控制的桌面会话中启动解包后的 `OSCAR20`，把数据目录和配置目录指向上述 `isolated/`，在 OSCAR 的导入界面选择 SD 卡根目录，然后导出 2026-09-11、2026-09-05、2026-09-12 三晚的 Daily/Session CSV。若要导出事件级数据，再对导入后的 `oscar.db` 运行 `oscar-sql` 中的 `Notes/Database/oscar_details_csv.py`；该脚本读取 SQLite，不直接读取 SD 卡。

这一步需要用户或具备原生窗口控制能力的后续会话完成；本记录不把源码推断或“进程启动成功”冒充为 OSCAR 已经读取了这张卡。

## 实验产物

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/oscar20_2.0.1-Debian12_amd64-Qt6.deb
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/package-root/usr/bin/OSCAR20
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/offscreen-run.log
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/isolated/
```


## 人工导入入口

已准备桌面快捷方式 `/home/ztmdsbt/桌面/OSCAR 数据核对.desktop`，调用实验目录中的 `launch-isolated.sh`。启动脚本设置独立 XDG 配置、缓存和数据目录；若 OSCAR 首次启动另行询问治疗数据保存位置，请选择 `/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/isolated/OSCAR-Data`。

导入时选择 `/run/media/ztmdsbt/5898-A683` 整个目录。用户只需完成首次资料创建和导入；导入完成后可由主代理定位本地数据库并继续提取对账结果，无需用户手工整理表格。桌面运行输出保存在实验目录的 `desktop-run.log`。本轮仅验证启动脚本语法，尚未验证真实桌面交互与导入成功。
