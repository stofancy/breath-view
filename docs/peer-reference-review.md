# 同类软件参考：保持使用者视角，先核对数据口径

日期：2026-09-13。下面“已确认”为初审历史记录；当前已完成原版 OSCAR 底层解析运行对账及息览修正，最新结果见文末与 `oscar-runtime-validation.md`。完整 GUI/数据库链路不在本轮验证范围内。

## 已确认

- FORMAT.md 已引用 BmcCpapData，因此它不是全新的证据来源。其 README 中 BMC 不支持 OSCAR 的描述属于早期背景；OSCAR 官方 2.0/2.0.1 发行说明已列出 BMC 支持与修复。
- 初审 OSCAR-SQL master 的 bmcDataParsing.cpp / bmc_loader.cpp：历史 0x83/0x84/0x87 分别映射 OSA/HYP/CSA，与息览一致；第三字节按 DurationSeconds 导入，而息览保留分钟聚合的可能性。单凭源码还不能证明 U-20A 上每条就是一个独立事件。
- bmcDataParsing.h 将流量定义为 int16_t；息览当前为 unsigned16。流量缩放均为 0.1。应以同一批有效 U-20A 波形包验证负值与异常值影响，再改实现。
- OSCAR legacy 结构将 0x04 标为 EPAP、0x06 标为 IPAP；FORMAT.md 原参考称 0x04 为 IPAP。息览界面暂称设备压力通道，避免错误地绑定临床含义。需要核实通道与设备模式。
- OSCAR 按波形间隔拆分 session，并对缺失波形与 USR 时长进行处理；息览以治疗日摘要分钟数作频率分母。两者结果不同不一定是事件识别错误，首先应核对分母及缺失时段。
- OSCAR legacy 流量存在非零基线的注释，不应直接用流量零交叉推算呼吸次数。

## 优先级

1. 同卡、同夜对账：已结算/未结算、完整/残缺波形、夜间多次开关机各选一个样本。比较事件数、类型、时间、时长、使用分钟、流量符号、压力与漏气缩放。OSCAR 与原厂 PAP Link/设备屏幕可用时交叉核对，不能把任何单一工具当绝对真值。
2. 在证据足够后决定能否把估算记录频率升级成设备残余 AHI；不能把戴机后的指数当作未经治疗的严重程度。
3. 患者首页保持三件事：治疗控制得怎样、比以前怎样、下一步做什么。拆开呼吸控制、使用覆盖、主观恢复感，不虚构综合睡眠分数或睡眠分期。
4. 优先补充治疗时间轴（记录到的开关机/缺失/事件聚集），不要把停机等同醒来；漏气与压力的关联放在展开分析中。
5. 医生摘要补充机器模式/设置与变化日期、指标来源和可计算范围；前提是设置解析经过本机验证。术语继续以 tooltip 解释。

## 来源

- https://github.com/riaancillie/BmcCpapData
- https://www.sleepfiles.com/OSCAR/
- https://gitlab.com/CrimsonNape/OSCAR-SQL/-/blob/master/oscar/SleepLib/loader_plugins/bmcDataParsing.cpp
- https://gitlab.com/CrimsonNape/OSCAR-SQL/-/blob/master/oscar/SleepLib/loader_plugins/bmcDataParsing.h
- https://gitlab.com/CrimsonNape/OSCAR-SQL/-/blob/master/oscar/SleepLib/loader_plugins/bmc_loader.cpp

源码初审针对抓取时的 master，不等于确认上述代码均已包含在 2.0.1 安装包中。不直接复制第三方解析代码；若引入其实现需另行核对许可证。

## 2026-09-13 有界修正交付

- 固定对照源码：oscar-sql `53c45136af4ae70fea1188b39da43e813a4a5d67`；2.0.1 发行版与此开发版本不可混称。
- 已增加独立 epap（0x04 / 2）与 ipap（0x06 / 2）曲线及中位数/P95，保留 pressure == epap 兼容键；文档改正旧 IPAP 标注。界面和医生参考报告同步展示两通道，通道含义明确为 OSCAR legacy 解释。
- 单夜必要实测：2026-09-11 EPAP 中位数/P95 6.5/8.5，IPAP 9.0/11.0 cmH2O。没有改动原始快照，不需要重新导入。
- 事件类型和第三字节时长解析与 OSCAR 一致；OSCAR 事件列表保存结束时刻并不能证明息览显示记录分钟错误。保留分钟精度与分钟范围阴影，不捏造秒级起止。
- 分母暂不改：息览用已结算 USR 用机分钟数，OSCAR 用 session/MaskOn 时段。缺失波形时不能用短波形覆盖时长替代全天摘要分母。tooltip 已说明此差异，未提升为已核验 AHI。
- 解析代理扫描当前快照未发现有符号负流量样本；不据此泛化所有 BMC 机型，不做不必要的符号改动。
- 通过 24 项现有及必要解析测试、JavaScript 语法检查、单夜真实报告双通道输出检查。尚未据此宣称完成 OSCAR 实际导入对账。

## 本地源码参考仓库

2026-09-13 已将两个仓库克隆到本机，后续研究优先使用本地搜索和读取，不再逐文件从网页抓取。当前使用浅克隆，包含完整工作树；仅在需要新版本或历史追溯时更新或补充历史。

- `/home/ztmdsbt/workspaces/references/OSCAR-code`：`64c5e90a26f91fb15868bcfcccde0c1e1522ac86`
- `/home/ztmdsbt/workspaces/references/oscar-sql`：`53c45136af4ae70fea1188b39da43e813a4a5d67`

两者均来自 `https://gitlab.com/CrimsonNape/` 下对应仓库，与本轮研究引用的版本一致。

## 可重复生成的对账基线

`tools/export_comparison_baseline.py --output <本地私有JSON路径> <日期...>` 从已有快照导出事件、摘要分钟、保留波形秒数、重复时间戳、连续记录段和通道统计，不读取或写入 SD 卡。输出仅代表息览，不能当作 OSCAR 通过验证的证明。

本轮选取 2026-09-11（已结算且有波形）、09-05（无波形）、09-12（未结算）、08-07（仅保留 86 秒波形）、09-06（有重复时间戳和间隙）。私有结果保存在 `/home/ztmdsbt/.cache/breath-view-reference/comparison-baseline-detailed.json`，不提交真实治疗数据。连续记录段不等于开关机或醒来次数。

## 开发版时长口径的源码风险

本地 `oscar-sql` 固定版本的 `BmcData::ReadDateSession()`（`bmcDataParsing.cpp`）会将最后一个波形段结束时间至少延长到“最后一段开始 + 整天 USR 分钟数”；前面的段仍保留。legacy loader 的 `findStableEndMs()` 直接使用该结束时间，作为 MaskOn 的结束。多段记录可能因此重复计入一部分时长。这是源码推导，尚未当作实际 OSCAR 运行缺陷定论。

例如息览 2026-09-11 有三段记录。若 OSCAR 读取相同三段，按上述代码推导的 MaskOn 总时长约 443.87 分钟，USR 为 379 分钟。实际运行对账时要核对段列表和分母，不能仅为匹配 OSCAR 最终指数而改变 USR 分母。该发现不改变息览当前患者判断。

## 重复秒波形修正已部署

当前卡 2026-09-06 的 231 个同秒包以及 08-09 的 242 个同秒包都含有不同的流量样本，不能按时间戳删除。已保留样本，记录段采用 >=5 秒前向跳变切分，绘图仍按真实缺样断线；展开的流量点按时间稳定排序，避免倒序折线。波形名义秒数不等于独立时间轴覆盖或睡眠时长，界面和报告已注明每包按 1 秒估算。

24 项必要测试通过。NAS 部署 `breath-view:4e0da6f`；直接读取部署后的 09-06 API 确认 21601 个有效波形包、231 个同秒包、3 个记录段（原先为 21370 秒、233 段）。容器运行且重启次数为 0，前版本容器保留为 `breath-view-before-waveform`。事件摘要和患者判断分母未更改，不需要重新导入。

修正后私有基线为 `/home/ztmdsbt/.cache/breath-view-reference/comparison-baseline-corrected.json`；旧基线保留供回看。

## 最终解析对账结论

原版 `ReadDateSession()` 实际复现了 09-11、09-06 最后记录段分别延长 3840 秒和 6172 秒的行为；保留息览的 USR 分母，不为匹配开发版 OSCAR 而扩大使用时长。三晚 10 段的七个通道原始统计和包数一致；08-07 息览额外保留 86 秒来自完整包扫描，OSCAR 的 crumb 读取路径在时间回跳处停止，返回零包。没有因此删除息览已经可靠提取的有效波形。全部 1114 天的 10652 条事件及摘要时长一致。

最终功能镜像 `breath-view:af8f70c`，本轮没有要求用户额外执行 GUI 导入。详细实验与私有产物路径见 `docs/oscar-runtime-validation.md`。
