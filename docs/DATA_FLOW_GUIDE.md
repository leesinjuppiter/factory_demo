# V1.3 数据流图解

图示用于整理模块输入输出。当前代码与历史性能材料分开，图中没有真实机器人或已完成的 OpenVINO/TensorRT。

## 1. 系统职责

<!-- DIAGRAM:01-architecture -->

主线为来源、Runner、推理、数据库；展示支路为已提交结果、Presentation、预览工作线程、WS/HTTP、浏览器stream、纯画布。管理HTTP、展示WS和历史查询分别使用不同职责入口。

## 2. 单帧保存与发布

<!-- DIAGRAM:02-frame-pipeline -->

保存成功后才发布。预览可跳过旧请求，待检图片不因此丢弃。文件与数据库不是跨介质事务；回执与业务提交也没有分布式原子性。

## 3. 模型数据变换

<!-- DIAGRAM:03-inference-transform -->

模型输出恢复原图像素后，展示投影补充中心点与几何方向。HBB/正方形无有效方向，近方形可靠性尚未现场标定。角度不等于机械末端姿态。

## 4. 浏览器显示

<!-- DIAGRAM:04-display-sequence -->

frame_key 标识采集帧，stream_session_id 标识运行；preview 描述实际图片尺寸与变换。旧连接、旧帧、失败图片不能覆盖当前画面。纯画布不fetch，图片URL和Blob释放归stream。

## 5. 历史和导出

<!-- DIAGRAM:05-history-export -->

历史适配层将旧Frame转换为画布输入；原图读取仍依赖历史数据库及runtime快照，不走最新预览缓存。不调用模型重新预测。

## 6. 持续落盘来源

相机/模拟器写.part → 图片关闭并发布最终名 → 发布.ready.json → InboxSource周期扫描与校验 → Runner处理 → 业务提交 → 私有回执。源文件不自动删除；持续任务total=null，停止须由后台请求。详见[落盘来源](CAMERA_INBOX.md)。
