# OSCAR 2.0.1 本机运行验证

日期：2026-09-13

本记录覆盖“能否在当前 Fedora 主机上隔离启动官方 OSCAR 2.0.1”，以及使用 OSCAR 源码中的 BMC legacy parser 对同一张卡做一次只读验证。没有安装系统软件包、没有编译 OSCAR 主程序、没有改动用户已有 OSCAR 配置，也没有写入 SD 卡或上传数据。

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

## 源码与 headless 路径复核

对 `/home/ztmdsbt/workspaces/references/oscar-sql` 的 commit `53c45136af4ae70fea1188b39da43e813a4a5d67` 做了只读检查：

- `oscar/oscar.pro` 的 `CONFIG+=test` 分支会把程序变成 Qt Test 控制台目标，但现有测试清单中没有 `bmctests.cpp` 或 BMC 测试夹具；直接运行现有测试不会调用 BMC loader。
- `oscar/main.cpp` 的帮助选项只有 `--profile`、`--datadir`、图形引擎选项和 `--help`，没有“导入 SD 卡路径”或“导出报告”的 headless 选项。
- 解包的官方二进制执行 `OSCAR20 --help` 成功退出并打印上述选项；这只确认参数入口，不是数据导入。

为避免安装系统包，已从 Fedora 44 仓库下载并解包一份 Qt6 开发包到实验目录：

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/qt6-qtbase-devel/
```

RPM 为 `qt6-qtbase-devel-6.11.2-2.fc44.x86_64.rpm`，SHA-256 为
`4ed98d17214c37c5116b5c3eb689a1fd821b20dd9ecd3bd039231b6ebe84061b`。
它与主机已有的 `/lib64/libQt6Core.so.6` 版本匹配。使用这套隔离头文件，已将 OSCAR 源码的 `bmcDataParsing.cpp` 与最小 `QCoreApplication` harness 编译成功；没有编译完整 `oscar.pro`，也没有使用 `moc` 或系统安装。

这条较小的 headless 路径已经足够读取 `.USR`、`.idx` 和波形索引起点，因此没有再为完整 GUI/数据库链路引入额外构建成本。源码现状仍没有现成的 BMC 测试二进制或官方导出命令。

## 原版 BMC parser 的一次真实读取

下面的结果来自上面编译的 OSCAR `bmcDataParsing.cpp`，不是息览代码推断，也不是完整 OSCAR GUI 导入或 `oscar.db` 导出。harness 对 SD 根目录只执行了一次 `BmcData::ReadData()`，读取 `.idx`、`.USR`、各编号波形文件的时间戳和索引指向的首包；没有调用 `ReadDateSession()`，所以没有展开完整波形样本。

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/bmc-usr-harness
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/sd-read-result.json
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/sd-read.log
```

运行成功（exit 0，约 2.77 秒），parser 读到 1114 个 USR 会话、366 个 IDX 条目、11 个有效 IDX 条目、466 个波形 crumb，并建立 1114 个会话链接。五个对账夜的 USR 结果如下；`second` 是相对该会话 12:00 起点的秒数，事件顺序是 parser 的原始分类顺序，不能据此判断时间先后。

| 日期 | 当前会话 | USR 分钟 | OSA | HYP | CSA |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-09-11 | 否 | 379 | 3 | 3 | 1 |
| 2026-09-05 | 否 | 389 | 5 | 5 | 2 |
| 2026-09-12 | 是（进行中） | 未知 | 6 | 4 | 1 |
| 2026-08-07 | 否 | 406 | 10 | 7 | 1 |
| 2026-09-06 | 否 | 355 | 8 | 2 | 7 |

五晚的分钟数和 OSA/HYP/CSA 事件数量与息览的 `comparison-baseline-corrected.json` 一致；事件的时间、持续秒数也一致，差异仅是原版 parser 按事件类型分组后输出，息览基线按时间排序。`oscar-five-days.json` 已按 `second` 做稳定排序，便于逐项比较。该结果证明同一份 SD 的 legacy USR 解码路径可以逐项对账，但不等于完整 OSCAR 已完成导入，也不覆盖 OSCAR 的波形切段、统计计算、SQLite 持久化或 GUI 显示。

## 原版 `ReadDateSession()` 的波形与分段验证

随后在同一个独立 harness 中再次调用一次 `ReadData()`，再依次调用五个日期的 `ReadDateSession()`；每个日期只展开一次自己的波形范围，没有在夜间之间重新初始化 parser。结果保存在：

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/bmc-date-harness
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/read-date-result.json
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/read-date-run.log
```

| 日期 | parser 波形包数 | 分段数 | 每段分配事件数 | 最后一段末尾延长 |
| --- | ---: | ---: | --- | ---: |
| 2026-09-11 | 22,795 | 3 | 0 / 1 / 6 | 3,840 秒（64 分钟） |
| 2026-09-05 | 0 | 1 个 EVT-only 段 | 12 | 无波形 |
| 2026-09-12 | 27,410 | 4 | 0 / 8 / 3 / 0 | 无（进行中） |
| 2026-08-07 | 0 | 1 个 EVT-only 段 | 18 | 无波形 |
| 2026-09-06 | 21,601 | 3 | 0 / 0 / 17 | 6,172 秒（102 分 52 秒） |

`ReadDateSession()` 的段末时间是最后一个包的时间戳（包含端点），所以通常比息览基线“末端独占”的记录段结束时间早 1 秒；包数与 corrected baseline 的保留波形秒数相符，09-12 和 09-06 的重复时间戳也被原版 parser 保留。09-05 和 08-07 没有可由该 parser 展开的波形，仍由 USR 事件建立 EVT-only 段，事件数量与息览一致。

这次运行直接读取原始 SD 文件；本次 harness 没有使用息览的现有快照（该快照存在，并对 SD 坏块做过零填充），因此 `raw_stats` 的来源是 SD 上各 `.nnn` 包的 `BmcWaveformPacket::Raw` 字段。每个 legacy 包只统计卡上真实存在的 25 个样本；parser 为扩展数组补的另外 25 个零值没有纳入统计。每个分段都记录了 `IPAP/EPAP/Leak/TidalVolume/MinuteVentilation/RespiratoryRate/SpO2/Pulse/I:E` 标量以及 `PressureWave/Flow/FlowAbnormality` 原始样本的 `median/p95/min/max/sample_count/non_zero_count`。这些是原始存储值，未做临床单位换算或异常哨兵过滤；例如输出中能看到呼吸率 `65535` 和分钟通气量 `-1`，使用时必须按设备编码语义过滤。

末段延长的直接证据是：2026-09-11 最后一段实际包到 `2026-09-12T07:35:00`，parser 按 USR 的 379 分钟把段末设为 `08:39:00`；2026-09-06 实际包到 `2026-09-07T07:54:39`，按 355 分钟把段末设为 `09:37:31`。这两个夜晚分别增加 64 分钟和 1 小时 42 分 52 秒；本次五晚中，延长前最后一个实际包已经晚于最后一个事件，因此事件计数没有因延长而改变，但任何使用 session end 计算治疗窗口或图表横轴的逻辑都会受到影响。

有一个必须保留的差异：2026-08-07 的息览快照保留了 `2026-08-08T01:42:16`–`01:43:42` 的 86 秒波形，而原版 `ReadDateSession()` 返回 0 个波形包。原版 `FindValidSessions()` 为该 USR 会话选择的是 `.018` 的 `14,680,064` 字节位置，crumb 时间为 `2026-08-07T05:53:09`；随后 `ReadWaveforms()` 在环形波形的时间回跳处停止，未到达快照保留的 86 秒区间。这是“OSCAR 原版 loader 与息览快照提取策略不同”的可复核证据，不能简单归因于 SD 文件缺失，也没有把息览的 86 秒冒充为 OSCAR parser 结果。

所以如果还需要核对完整 GUI/SQLite 链路，最小人工验证路径仍是：在可控制的桌面会话中启动解包后的 `OSCAR20`，把数据目录和配置目录指向上述 `isolated/`，在 OSCAR 的导入界面选择 SD 卡根目录，然后导出 2026-09-11、2026-09-05、2026-09-12 三晚的 Daily/Session CSV。若要导出事件级数据，再对导入后的 `oscar.db` 运行 `oscar-sql` 中的 `Notes/Database/oscar_details_csv.py`；该脚本读取 SQLite，不直接读取 SD 卡。当前已经有原版 parser 的自动对账基线，因此人工步骤只负责验证 GUI loader/数据库行为，不必再重复读取 SD 做 USR 统计。

完整 GUI/数据库验证仍需原生窗口操作，但本轮解析对账已自动完成，不要求用户完成这项额外验证才能使用息览。

## 实验产物

```text
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/oscar20_2.0.1-Debian12_amd64-Qt6.deb
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/package-root/usr/bin/OSCAR20
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/offscreen-run.log
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/isolated/
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/qt6-qtbase-devel/
/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/bmc-harness/
```


## 人工导入入口

已准备桌面快捷方式 `/home/ztmdsbt/桌面/OSCAR 数据核对.desktop`，调用实验目录中的 `launch-isolated.sh`。启动脚本设置独立 XDG 配置、缓存和数据目录，并用 `--datadir` 和 `--legacy` 指定隔离数据目录及软件绘图；数据目录为 `/home/ztmdsbt/.cache/breath-view-reference/oscar-runtime/isolated/OSCAR-Data`。

导入时选择 `/run/media/ztmdsbt/5898-A683` 整个目录。用户只需完成首次资料创建和导入；导入完成后可由主代理定位本地数据库并继续提取对账结果，无需用户手工整理表格。桌面运行输出保存在实验目录的 `desktop-run.log`。本轮仅验证启动脚本语法，尚未验证真实桌面交互与导入成功。

## 主代理复核与交付

- 复用 `sd-read-result.json`，对照全部 1114 天、10652 条事件，无事件类型/时间/时长及摘要分钟差异。实验导出器把零分钟输出 null，历史零分钟按等价方式归一化。结果：`bmc-harness/all-usr-comparison.json`。
- 对照 09-11、09-12、09-06 共 10 个记录段：包数以及 EPAP、IPAP、漏气、潮气量、分钟通气量、呼吸率和流量的原始 median/P95/min/max 全部一致。比较保留原始哨兵值，不把它们作为生理值；使用息览快照与 SD parser 的实际输出，不新增 SD 读取。结果：`bmc-harness/waveform-stat-comparison.json`。
- 已修复息览同秒包去重造成的样本丢失和小间隙导致的记录段碎片化，保留真正的绘图缺样，修正了重复秒流量展开后的倒序连线。
- 24 项必要测试通过；患者提示现准确说明 OSCAR 底层解析已交叉核对，未冒称原厂认证或完整 GUI 统计已验证。NAS 发布镜像 `breath-view:af8f70c`。
