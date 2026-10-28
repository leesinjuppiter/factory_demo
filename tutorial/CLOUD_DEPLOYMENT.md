# AutoDL 云端 GPU 部署与复现

日期：2026-10-28。代码在 `/root/autodl-tmp/factory_demo`，图片数据在同级 `dataset/`。云端使用独立 Conda 环境 `factory_demo`；本机继续使用 `yolo_v5_obb`。本页描述新增 CUDA 路径，旧 CPU 验收记录仍保留原环境含义。

## 1. 创建环境与安装依赖

```bash
conda create -n factory_demo python=3.10 pip -y
conda activate factory_demo
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
cd /root/autodl-tmp/factory_demo
python -m pip install -r requirements-cloud-cu124.txt
python -m pip check
```

约束：此清单针对 Linux/RTX 3080 Ti，不替换本机环境。CUDA Toolkit 和驱动属于额外系统依赖。GPU 可用还需实际运算和模型测试；不能把 nvidia-smi 中的 CUDA 13.0 当作 Toolkit 版本。当前服务器驱动580.76.05、Toolkit12.8、GCC11.4、PyTorch CUDA12.4；次版本差异有警告，本次编译和实际运行已验证。

## 2. 数据源与设备选择

服务器 `.env` 在数据库连接之外增加：

```dotenv
FACTORY_CONFIG=/root/autodl-tmp/factory_demo/configs/cloud.json
FACTORY_DEVICE=cuda:0
```

cloud.json 三组图片路径为 `../dataset/dataset4911_obb_smoke_50/{test,val,train}/images`，不再依赖原始 yolov5_obb-master 目录。`runtime/camera_inbox` 为持续落盘来源。

约束：设备只接受 cpu 或 cuda:N。默认CPU，指定CUDA不可用时明确失败，不自动回退。设备是服务启动配置，不允许浏览器任意切换。仍为单进程、单任务、单张FP32；模型参数、阈值、类别表和展示协议保持一致。PyTorch CUDA不代表TensorRT已实现。

## 3. Linux 旋转 NMS 编译

```bash
conda activate factory_demo
cd /root/autodl-tmp/factory_demo/vendor/yolov5_obb/utils/nms_rotated
CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.6 MAX_JOBS=2 python -B setup.py build_ext --inplace
```

约束：8.6对应RTX 3080 Ti，换卡须核对架构。Windows .pyd不能用于Linux；生成的.so和build目录不进Git。换PyTorch、Python或平台后重新编译。`FORCE_CPU=1`显式只构建CPU，该产物不能处理CUDA输入。

构建包含CPU/CUDA旋转OBB NMS。旧poly_nms_cuda.cu作为来源保留但不编译，应用不支持任意多边形NMS。CUDA guard和整除更新为兼容接口；原始索引在输入设备创建，避免过滤小框后CPU/CUDA索引混用。保留原IoU计算与抑制算法。

模型、预热和输入都使用所选设备。CUDA阶段计时在边界同步；预处理包括主机到设备传输，后处理包括返回JSON所需的数据传输。同步有额外成本，这不是异步流水线性能上限，也不包含数据库、预览、网络和动作执行。

## 4. 独立 PostgreSQL

本轮安装PostgreSQL14，创建仅用于本应用的factory_demo数据库及同名普通角色，随机密码只写服务器.env。数据目录为 `/var/lib/postgresql/14/main`。

在另一台全新Ubuntu22.04服务器上，首次初始化可执行以下命令；本轮服务器已完成，不要重复执行创建账户/数据库：

```bash
apt-get update
apt-get install -y postgresql
pg_ctlcluster 14 main start
cd /tmp
runuser -u postgres -- createuser --pwprompt --no-superuser --no-createdb --no-createrole factory_demo
runuser -u postgres -- createdb --owner=factory_demo factory_demo
```

在密码提示中输入独立密码，然后在项目.env设置对应DATABASE_URL，格式参考.env.example；密码含URL保留字符时须编码。保留前述FACTORY_CONFIG及FACTORY_DEVICE。不要把密码写进命令行、Git或公开日志。

```bash
pg_lsclusters
pg_isready -h 127.0.0.1 -p 5432
# 容器重启后若14/main未运行：
pg_ctlcluster 14 main start
```

约束：数据库只接受本机连接，应用账户不是超级用户，不复用本机密码，.env不进Git。冷启动和成功结果提交仍依赖数据库，故障仍结束任务。Conda中的psycopg只是客户端；不要重复初始化或覆盖已有库。释放实例前应按平台规则备份系统盘数据库，上传源码不能恢复历史。

## 5. 启动和访问

```bash
conda activate factory_demo
cd /root/autodl-tmp/factory_demo
python -B start.py
```

API保持服务器127.0.0.1:8765，展示路径/，管理/admin.html。已上传dist时不需要Node.js。需要重建前端时执行npm ci / npm run build。

管理HTTP请求限时30秒，适应SSH链路首包较慢的情况；本轮一次状态请求曾达13.7秒。慢网络仍可能超时，状态提示反映通信，不改变后台推理。展示继续使用只读WS，预览独立HTTP加载。

历史页需要下载原图，加载限时60秒；实时展示的压缩预览仍限时10秒，队列策略不变。超时不是未检出，不允许把未加载的图片与新坐标合并显示。

本机建立SSH隧道后访问 http://127.0.0.1:18765/ ：

```bash
ssh -p <SSH端口> -L 18765:127.0.0.1:8765 root@<SSH主机>
```

约束：保持Host/Origin的本机边界，不直接开放公网管理或数据库端口。浏览器关闭不停止任务。只允许一个应用实例，不增加Uvicorn workers；后台运行时核对PID后发送SIGTERM，前台运行时Ctrl+C停止。

本轮后台服务PID、日志、编译和验证日志位于 `/root/autodl-tmp/tmp/factory-cloud-20261028/`。服务器重启后PID会变化，不能直接沿用旧PID。部署前备份位于其中backup-initial，包含私密.env，不上传仓库。

## 6. 验证与边界

```bash
cd /root/autodl-tmp/factory_demo
python -B -m pytest tests -q
python -B scripts/smoke.py --output runtime/cloud-smoke50.json
```

GPU测试覆盖随机旋转框跨64框分块、过滤索引、空输入、全小框、自定义CUDA stream及真实模型CPU/CUDA FP32对照。真实模型对照容差为角点1像素绝对误差加0.1%相对误差、置信度0.002；不要求跨平台逐位一致。

约束：API测试创建独立schema，不指向其他项目数据库。smoke用50张验证流程，不计算精度或全量指标。模拟落盘、WS、历史和预览另行联调。没有工业相机、编码器、机械臂，不以GPU可用、短样本均值或模拟42fps证明生产42fps和动作时限。

实际结果见 [云端验收证据](evidence/cloud-validation-20261028.json)。更改环境或实现后需要重新验证。

## 7. AutoDL 6006 只读展示入口

用户确认使用AutoDL允许映射的6006端口。实例内继续运行HTTP服务；浏览器访问平台提供的HTTPS地址，两者不是同一段协议。[AutoDL官方端口文档](https://www.autodl.com/docs/port/)提供了HTTP映射与HTTPS公网地址的示例，不应把控制台复制的https前缀手工改成http。

本实例已验证的公网地址：

<https://u1101749-9dad-6f2edc53.westb.seetacloud.com:8443/>

准确主机名含westb。此前截图转写成west导致连接失败；以控制台复制地址为准，不推测其他域名。

```bash
conda activate factory_demo
cd /root/autodl-tmp/factory_demo
FACTORY_DISPLAY_HOST=u1101749-9dad-6f2edc53.westb.seetacloud.com \
python -B -m uvicorn backend.display_gateway:app --host 0.0.0.0 --port 6006 --workers 1
```

该命令仅在入口未运行时执行。当前已在后台运行，PID与日志位于 `/root/autodl-tmp/tmp/factory-display-6006/gateway.pid` 和同目录gateway.log；重启容器后需要先启动8765主服务，再启动6006入口。映射域名或端口变化时核对平台地址并更新FACTORY_DISPLAY_HOST。

数据路径为：浏览器HTTPS/WSS连接AutoDL入口，平台回源HTTP/WS到6006，只读入口再连接服务器127.0.0.1:8765的展示接口。浏览器无需SSH隧道；管理/历史继续通过原SSH隧道访问。入口不加载模型、不连数据库、不创建任务。

边界约束：

- 只开放展示HTML、display/style静态资源、展示快照、不可变JPEG预览与只读WS；/admin.html、/api/status、/api/runs、/api/uploads、/docs、.env和admin脚本均不公开。
- 页面隐藏后台管理链接；HTTP控制路由不可达，WS收到应用数据关闭1008，不向主服务转发。前端同源默认地址支持HTTPS，显式display_origin覆盖仍仅允许本机模拟服务，预览必须同源。
- 主服务和PostgreSQL仍仅监听本机。本入口故障只影响公开展示；8765主服务故障时入口返回通用503或断开WS，不能把旧画面解释为当前检测正常。
- 公开入口用于用户明确允许展示的图片与结果，不提供账号认证、管理权限或原图历史下载；需要访问控制时另行设计，不以隐藏按钮代替路由隔离。
- 上游WS订阅仍受主服务16连接上限约束，单入口HTTP连接池16、WS接收队列1；同一帧的图片与坐标一起显示，缓存过期按410处理。
- 当前页面展示最近一次已停止任务的45框，结果年龄继续增长；后台创建新任务后自动更新，不伪造实时相机输入。

公网HTTPS、JPEG、WSS、只读关闭码、私有路由阻断与浏览器结果见[evidence/public-display-6006-20261028.json](evidence/public-display-6006-20261028.json)，截图见[evidence/public-display-6006-20261028.png](evidence/public-display-6006-20261028.png)。
