# V1.3 API 与通用展示协议

本机单进程推理服务。管理/历史接口保留旧Run/Frame，通用展示使用独立白名单契约；两个结构不能混为同一接口。真实引擎为PyTorch CPU/CUDA FP32，默认CPU，model.device按实际设备返回；OV/TRT unavailable。管理与历史仍经SSH本机隧道；用户明确要求后，新增6006独立只读展示入口，浏览器HTTPS/WSS经AutoDL映射到实例HTTP/WS。协议结构不变，公开入口不代理私有API，见[CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md#7-autodl-6006-只读展示入口)。

## 1. 展示端点

|端点|用途|边界|
|---|---|---|
|GET /api/display/snapshot|当前展示快照，内存读取|不查询历史库；不是一次推理请求|
|WS /api/display/ws|连接时快照，变化时推送|只读；客户端发送消息会被拒绝，不支持生产控制|
|GET /api/display/previews/{id}.jpg|不可变 JPEG 预览|有界内存缓存，过期返回410 PREVIEW_EXPIRED|

无变化约15秒发送heartbeat；服务端每次发送有5秒超时。每客户端队列最多1个待发快照，最多16订阅者。编码工作线程有一个待处理槽，较旧预览可以跳过。缓存最多32项且不超过32MiB，预览宽度最多1024，JPEG质量82。这些是当前资源上限，不是工业帧率承诺。

## 2. Snapshot

```json
{
  "schema_version": "1.0",
  "type": "snapshot",
  "revision": 1,
  "stream": null,
  "frame": null,
  "service": {
    "preview_skipped": 0,
    "preview_errors": 0,
    "preview_cache_bytes": 0,
    "preview_cache_limit_bytes": 33554432,
    "subscribers": 1,
    "latest_result_key": null
  }
}
```

revision 是当前服务进程内的展示版本，不是持久化全局事件号。重连必须建立新连接代次，不能把前一进程的 revision 当作永久下界。空闲时 stream/frame 可为空；heartbeat 没有帧载荷。service.latest_result_key 指向最新推理结果身份，frame 可以是较早但已完整编码的展示帧；两者不必相等，不能据此把最新框拼到旧图。

## 3. Stream

stream 包含 session_id、source_id、source_label、mode（finite/continuous）、status、model（id/version/name/device）、engine_label、classes、class_catalog_version、class_counts、processed/total/succeeded/failed、timings 与 error。

约束：session_id 为当前运行会话；continuous 的 total=null；类表 id/name/label/color 来自当前模型。model.version 与 class_catalog_version 当前均采用模型文件哈希，缺失可为空。timings 未测量为null，合法0保留。continuous 的 P50/P95 采用最近最多1000成功样本，mean累计；有限运行使用完整本轮样本。error 是安全诊断 code/message，不把内部异常路径暴露给展示。管理端仍保留诊断详情，展示投影没有 model.path。

## 4. Frame 与检测

frame 包含 frame_key、stream_session_id、id（字符串）、name、status、width/height、coordinate_space、detections、timing_ms、created_at、capture_time/capture_clock_domain、published_at、preview/preview_status、error。

|字段|约束|
|---|---|
|frame_key|{source_id,session_id,frame_id}；inbox采用生产者capture_key，有限来源采用source/run/index|
|stream_session_id|关联当前运行会话，不能仅凭capture_key推断当前Run|
|width/height、coordinate_space|原图尺寸；source_pixels，x右y下，原点左上|
|status|ok+空detections才是未检出；error不表示没有目标|
|preview_status|pending/ready/error/none；等待预览不能把框绘到别的图|
|capture_time|真实采集时刻未提供时null；模拟脚本不伪造曝光时间|
|published_at|文件发布时刻，与摄入、推理完成及页面到达不同|

每个 detection 包含 id、class_id、class_name、confidence、geometry_type、polygon_px、center_px、angle_deg、angle_convention、orientation_valid、track_id。

polygon_px 为4个顺序原图像素点，有限数值，可超出视口；不逐点裁切后冒充原几何。confidence范围0..1。center_px 为四点均值。角度约定为 long_axis_clockwise_from_positive_x_mod_180，即长轴相对+x顺时针、[0,180)。HBB与数值上正方形方向无效；当前仅排除数值退化，近方形的业务可靠阈值尚未标定，不能把有效几何角当作可靠抓取姿态。track_id=null，id仅帧内标识。

## 5. Preview 与前端提交

preview 包含 id/url/mime/width/height/sx/sy/ox/oy。变换是预览点=(原图点×scale)+offset；本版为整图缩小，无裁剪和补边，ox=oy=0。因像素尺寸四舍五入，sx/sy分别按实际宽高计算。

编码侧为一个执行中任务和一个最新待处理任务；已有完整展示帧会保留到下一张编码完成。浏览器同样保留一个执行中请求与一个最新待准备帧，换会话时使旧异步结果失效。

URL内容不可变；缓存过期只影响预览，不删除历史原图。浏览器验证协议与会话、获取图片、解码成功后原子提交图与框；旧连接/旧帧异步完成不能覆盖新画面。画布接收已准备的数据，不自行fetch。历史源由独立适配器转换，不要求数据库Frame改成展示契约。

## 6. 管理与历史 HTTP

- GET /api/health：检查数据库连通；不代表模型或设备健康。
- GET /api/capabilities：引擎可用性、受信任来源、限制、默认参数。
- POST /api/uploads：单图；仅JPG/JPEG/PNG/BMP，最大20MiB，最大4000万像素。
- POST /api/runs：source_id、engine、confidence、iou、image_size、max_det、replay_fps；来源不能是任意路径。
- GET /api/status：旧管理快照{run,frame}，内存读取。
- POST /api/runs/{id}/control：pause/resume/stop，受理意图与帧边界完成区分。
- GET /api/runs、/api/runs/{id}、/api/runs/{id}/frames、/api/runs/{id}/frames/{frame_id}：历史分页和详情。
- GET /api/runs/{id}/frames/{frame_id}/image、/annotated：历史原图和绘框PNG。
- GET /api/runs/{id}/export?format=json|csv：终态导出；不重新推理。

Run状态为loading/running/pausing/paused/stopping/completed/stopped/failed/interrupted。有限任务total整数，持续任务null。数据库服务启动依赖、历史查询依赖和先保存后发布行为仍保留。错误统一detail.code/message，前端还需处理非JSON和网络错误。

## 7. Inbox 文件契约

生产者先写 image.part，关闭后改为最终图片名；再写 ready.part，关闭后发布 *.ready.json。消费者只扫描最终清单，支持周期补扫。清单schema_version=1.0，包含source_id/session_id/frame_id、image（同目录文件名）、size、sha256、capture_time（可null）、带时区published_at。

身份字段限制为字母数字下划线短横线，frame_id为数字字符串；源图片不得符号链接/跨目录，清单最多16KiB，图片最大20MiB。未消费清单最多10000，超限停任务而不丢弃。消费者保存私有SQLite回执，不删除相机文件；成功业务提交后才ack。数据库和回执不是一个原子事务，崩溃窗口须按实现边界解释，不能宣称跨介质恰好一次。
