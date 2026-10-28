# 持续落盘来源与模拟拍照

生产路线已确定：相机保存本机磁盘，程序读取完成发布的图片。当前实现没有真实相机SDK，只提供发布协议、持续读取和模拟脚本。

## 1. 用小数据集模拟拍照

```powershell
Set-Location 'C:\Users\13480\Desktop\codex_\factory_demo'
$py = 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe'
& $py -B scripts\simulate_camera.py --input-dir '..\yolov5_obb-master\dataset\dataset4911_obb_smoke_50\test\images' --output-dir 'runtime\camera_inbox' --source-id camera_inbox --count 50 --fps 5
```

脚本循环选用输入图片，保持原有编码、尺寸和内容，生成新session与帧号；不覆盖原数据。输出图片后发布ready清单。随后在后台选择已配置的相机inbox来源启动；也可先启动持续来源等待新清单。结束模拟器不自动结束持续任务，应在后台停止。

约束：count为1..10000，fps为目标发布频率；本机文件I/O达不到目标时记录late_frames，不补造真实曝光时间。capture_time=null，published_at是真实发布时刻。work_rate_fps是本次文件发布工作速率，不是相机或推理能力。

## 2. 队列与回执

只接收已发布 *.ready.json；.part和只有图片没有ready的文件不摄入。周期扫描补足文件通知遗漏，已消费清单通过runtime私有SQLite回执识别；清单被修改或重复身份会明确报错，不把它当新照片。

约束：原图和清单都不自动删除。未消费条目超过10000会停止任务，不跳过旧图。暂停推理期间模拟器/相机仍可能继续落盘。回执、业务数据库和原图不是一个分布式事务；崩溃后的重试不等于设备动作恰好一次。

## 3. 当前容量边界

4096×2168 Mono8/Bayer8像素数据约8.88MB/帧，42fps约373MB/s；BGR8约26.64MB/帧，未压缩彩色BMP超出当前20MiB单文件限制。实际编码文件大小需实测，不能把原始像素大小当JPEG大小。

当前原图快照仍会额外保存一份。是否取消复制需要先确认相机文件不可覆盖、保留期限和清理责任。磁盘空间1GiB阈值不是容量预留，也不证明可以持续42fps。生产队列超龄/减速/停机/跳帧策略仍待现场确认，本版不默认丢待检图片。
