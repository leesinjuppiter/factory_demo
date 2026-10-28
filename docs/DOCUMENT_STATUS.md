# 文档状态索引

日期：2026-10-28。同一天的文件并不都描述同一实施阶段。阅读时先看状态，不按文件日期推断功能已经实现。

|材料|状态|阅读用途|
|---|---|---|
|V1_3_DECOUPLING.md、PRODUCT.md、ARCHITECTURE.md、CONTRACT.md|V1.3 当前代码职责与约束|新版本使用、协议与教学基线|
|GUIDE.html / web_manual/index.html|当前源文档生成的离线手册|统一阅读、搜索、流程图|
|MODULE_SPLIT.md、INDUSTRIAL_DISPLAY.md|当前展示/管理职责；附 V1.2 历史截图说明|理解界面及兼容约束|
|VERIFICATION.md、evidence/smoke50.json|V1.0 历史验收|50 张真实模型与原始生命周期证据，不是本轮新测|
|PERFORMANCE_OPTIMIZATION_ANALYSIS_20261028.md|基于旧 50 张记录的分析|没有新性能实验，不证明当前生产能力|
|production_proposal/PROPOSAL.md|历史提案|其中 SDK 内存主路线建议未被采用；用户确定先落盘|
|decoupling_analysis/ANALYSIS.md|初始解耦分析|目标设计；应结合后续评审与实际代码阅读|
|decoupling_analysis/REVIEW_DEEPSEEK_20261028.md|已确认决策与评审|落盘来源、本机部署、故障策略待定等依据|
|evidence/v13-validation.json、v13-browser-validation.json、v13-live-flow.json|V1.3 本轮验证|协议、浏览器、真实模型与模拟落盘链路；不能代替42fps验收|

没有设备反馈时，机械臂、带速补偿、抓取准确率和执行时限仍是后续工作。没有目标设备上的真实适配与数值测试时，不将 OpenVINO/TensorRT 写成已支持。
