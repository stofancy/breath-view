# 同类软件参考：保持使用者视角，先核对数据口径

日期：2026-09-13。范围：只读初审；尚未用 OSCAR 导入本机同一份 U-20A 数据做输出对账。未修改解析器或线上判断规则。

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
