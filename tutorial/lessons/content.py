"""教学正文。每节包含实现顺序、验收、故障定位、练习与自测。"""
LESSONS=[]
def add(n,title,goal,body,files,question,options,answer,explain):
    offset=n%len(options)
    options=options[offset:]+options[:offset]
    answer=(answer-offset)%len(options)
    LESSONS.append(dict(id=n,title=title,goal=goal,body=body,files=files,quiz=dict(question=question,options=options,answer=answer,explain=explain)))

add(0,'先理解要完成什么','用输入、处理、存储、显示四个职责描述整个应用。',r'''
## 这一节先不写代码
最终你要实现的是一个本机检测应用：选一张图片或一个目录，后台逐张推理，把结果和原图快照保存下来，浏览器显示四点框，用户可以暂停、继续、停止、查看历史和导出。

课程不要求你从零重写 YOLO 的神经网络层、训练器或旋转 NMS C++ 扩展。我们实现应用和适配器，复用已经验证的 YOLOv5-OBB 基础代码及可信权重。OpenVINO/TensorRT 在本版是扩展接口，不会被描述成已经可运行。

## 先分四条线
1. **控制线**：浏览器发送 source_id 和参数，API 校验后交给 Runner。
2. **计算线**：图片字节 → BGR 数组 → RGB 张量 → 模型候选 → 原图四点框。
3. **保存线**：原图字节写磁盘；Frame 和 Run 汇总一起提交 PostgreSQL。
4. **显示线**：浏览器读取 JSON，再按帧 ID 读取原图，绑定在同一 SVG 坐标系中。

{{diagram:01-architecture}}

## 学习方式
每节先阅读“动手顺序”，在 `practice/factory_demo` 手写文件，再展开该节的完整参考代码进行对照。可选的 `course.py apply N` 只是放置截至第 N 节的参考文件，不会证明你已经学会；它保留不同的现有文件，不覆盖你的修改。

## 验收与练习
不用看图，说明为什么浏览器关闭后任务仍可继续，为什么原图不放进数据库 JSON。画出上述四条线，每条箭头写具体数据名字。如果你把每次 GET /status 画成触发一次推理，先返回本节重新区分控制与查询。
''',[], '浏览器轮询 /api/status 的职责是什么？',['读取当前结果','触发一次新的模型推理','重新计算数据库统计'],0,'推理由后台工作线程推进；轮询只读取快照。')

add(1,'建立独立目录与环境检查','在不碰原项目的前提下准备练习区。',r'''
## 动手顺序
1. 打开 PowerShell，把下面三行作为本课程每次新开终端的起点。
2. 执行环境探测，它只读取解释器和包版本，不连接数据库、不安装依赖。
3. 建立练习区的依赖清单。若选择手写，创建同名目录并保存本节文件；若想使用参考文件，运行 apply 1。

```powershell
$course = 'C:\Users\13480\Desktop\codex_\tmp\deliverables\factory_demo_tutorial'
$py = 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe'
Set-Location $course
& $py -B tools\env_probe.py
& $py -B tools\course.py apply 1
```

## 代码为什么这样组织
`reference` 是教学参考答案，不直接用来跑正式练习；`practice/factory_demo` 是你逐步实现的应用；`examples` 是拆开概念的小实验。Python 文件用 `-B` 避免到处生成 __pycache__。本教程默认不操作现有 8765 工作台。

`requirements-api.txt` 只覆盖 API 所需依赖，不是完整 YOLO 环境。看到 MISSING 时先确认当前解释器，不要直接重装 Torch。只有确实缺少课程所需 API 包时才执行下面的安装命令；本课程生成阶段没有替你执行安装。

```powershell
& $py -m pip install -r reference\requirements-api.txt
```

## 验收与故障定位
解释器应来自 yolo_v5_obb。若显示其他 Python，检查 `$py`，不要只凭提示符环境名判断。包版本输出是环境证据，不代表数据库或模型已经跑通。

练习：解释为什么不能把原项目 `.env` 直接复制过来。答案涉及独立数据库、角色凭据以及避免把练习数据写入原历史。
''',['tools/env_probe.py','reference/requirements-api.txt'],'下面哪个行为属于环境检查？',['读取包版本','自动删除旧数据库','自动重装 Torch'],0,'环境检查先读取状态，缺什么再针对性处理。')

add(2,'先写数据协议','把检测结果从模型内部格式变成前后端共同理解的结构。',r'''
## 动手顺序
1. 新建 `examples/protocol.py`，先写 FRAME 示例，只保留宽高、帧标识和一个检测框。
2. 给检测框写四个点，按矩形边连续排列；单位是原图像素。
3. 写 `validate`：宽高大于零、confidence 在 0..1、四个点、每点两维、数值有限。
4. 运行，再把其中一个数改成 NaN，观察为什么必须拒绝。

```powershell
& $py -B examples\protocol.py
```

## 逐句理解
`frame['detections']` 是列表，因此没有目标时自然表示成 `[]`。`len(polygon)==4` 检查点数，不能证明坐标数值合法，所以还需要 `math.isfinite`。本实验用 assert 方便学习；产品 API 使用显式校验和结构化错误，不依赖可能被优化开关禁用的 assert。

Run 是整个任务；Frame 是某一张图片。Frame.id 只在同一 run_id 下唯一；检测 id 又只在同一帧内唯一。不能拿这两个序号计算跨帧实物去重数量。

## 验收与练习
有效示例能打印 JSON，NaN 示例失败，空 detections 仍合法。再写一个目标点超出图片边界的样例：有限的越界点可以是合法旋转框，不应逐点裁切改变几何。

最常见错误是把像素坐标除以图像尺寸后仍当像素交给 SVG，导致框缩成左上角的一小点。
''',['examples/protocol.py'],'detections=[] 在一张正常处理的图片中代表什么？',['没有保留目标，是正常结果','图像必定读取失败','模型一定没有加载'],0,'错误应通过 status/error 表达，不能与空检测混用。')

add(3,'从一个最小画布开始','理解 viewBox 如何让原图与四点框一起缩放。',r'''
## 动手顺序
1. 建立 `examples/canvas.html`，先写一个 viewBox 为 `0 0 640 360` 的 SVG。
2. 用灰色矩形代表示意输入，明确标注教学图，避免被误认为真实检测。
3. 把四点数组转换成 polygon 的 points：每个点用逗号连接，四个点用空格连接。
4. 增加显示宽度滑块和显示框复选框。
5. 在浏览器双击打开该文件；这一步没有后端。

[打开可操作的画布实验](../examples/canvas.html)

## 关键代码的含义
`polygon.map(p=>p.join(',')).join(' ')` 将 `[[x,y],...]` 转为 `x,y x,y ...`。`viewBox` 定义内部坐标范围，CSS width 定义屏幕显示宽度。两者分开，所以缩放页面时不需要重算每个点。

`vector-effect="non-scaling-stroke"` 让框线宽度不随缩放成倍变粗。这改变绘制效果，不改变检测坐标。真实组件随后会用 `<image>` 显示原图；当前实验只证明几何关系。

## 验收与练习
拖动宽度从 100% 到 50%，框与背景同步缩小，下面 JSON 坐标不变。隐藏框后背景仍存在。试着删掉 viewBox，记录结果，再恢复。

这一节的完成标准是理解“坐标系绑定”，不是页面看起来像最终工作台。
''',['examples/canvas.html'],'缩小 SVG 显示宽度时，原图坐标应该怎样处理？',['保持不变，由 viewBox 统一缩放','每次把四点乘 0.5 后保存回数据库','改为类别编号'],0,'原图坐标是持久化协议；显示变换不应修改数据。')

add(4,'建立 Vue 工程骨架','认识入口、依赖锁文件和开发代理。',r'''
## 动手顺序
1. 创建 `frontend/package.json`，理解 dependencies 与 devDependencies 的区别。
2. 保留课程附带的 package-lock.json，让安装版本可重复。
3. 创建 index.html 与 vite.config.js。开发端口为 5176，/api 代理到练习 API 的 8876。
4. 先阅读配置，不急着编写完整页面。第 14 节补齐 src 后再构建；此时缺少 src 入口并不是后端问题。

```powershell
& $py -B tools\course.py apply 4
```

## 代码为什么这样写
Vite 帮你处理 Vue 单文件组件和模块依赖。`plugins:[vue()]` 负责 `.vue`；`proxy` 只作用于开发服务器。最终生产页面由 FastAPI 托管，使用同源 `/api`。

`strictPort:true` 表示占用时直接报错，避免自动换端口后你仍访问旧地址。不要把练习代理仍指向 8765，否则按钮可能控制原项目。

## 验收与练习
检查配置中只出现教学端口 5176/8876。说清浏览器请求 `/api/status` 时，在开发模式和生产模式分别由谁接收。

依赖安装命令在第 14 节执行。课程不把联网 npm 安装包装成离线网页的前置条件；读课程本身不需要 Node 或网络。
''',['reference/frontend/package.json','reference/frontend/vite.config.js','reference/frontend/index.html'],'Vite 的 /api 代理应指向哪个地址？',['http://127.0.0.1:8876','原项目的 8765','任意公网地址'],0,'练习前后端必须成对使用独立端口。')

add(5,'写第一个 FastAPI 接口','用最少代码验证请求、响应和参数校验。',r'''
## 动手顺序
1. 新建 `examples/api_minimal.py`，先创建 FastAPI 对象。
2. 写 GET /api/health 返回 teaching-only，明确这是教学 API。
3. 写 Pydantic 请求模型：source_id 非空，confidence 在合法区间。
4. 写 POST /api/runs 返回请求内容；它没有数据库和后台线程，不能当最终任务实现。
5. 在一个单独终端运行下面命令，浏览器打开 `http://127.0.0.1:8877/docs`。

```powershell
& $py -B examples\api_minimal.py
```

## 逐句理解
`@app.post` 把 URL 和函数绑定；函数参数的类型告诉 FastAPI 如何解析 JSON。`Field(ge=...,le=...)` 在进入函数前拒绝非法参数。`model_dump()` 将请求模型转回普通字典，方便保存和返回。

HTTP 201 表示本示例接受了创建请求，但示例固定 ID 没有持久化含义。生产版会生成 UUID 并提交 Run，不能继续沿用固定值。

## 验收与练习
健康检查 200；合法 confidence=.25 返回 201；confidence=2 返回 422。停止示例用 Ctrl+C。不要用“网页能打开”代替检查 POST 校验。

练习：给示例增加 `image_size` 字段，并解释为什么范围合法还不够，最终版还需要 stride 整除检查。
''',['examples/api_minimal.py'],'confidence=2 应在哪里被拒绝？',['请求校验阶段','等模型算完之后','只在前端按钮里'],0,'后端必须独立校验，前端表单限制不能替代接口约束。')

add(6,'实现配置与图片输入','把逻辑源 ID 安全地转换为可重复的图片清单。',r'''
## 动手顺序
1. 写 Settings：从配置读取 runtime、weights、sources 和 defaults，路径相对练习项目根目录解析。
2. 写 inventory：扫描目录第一层，筛选允许后缀、拒绝不合规输入，排序并记录 size/mtime。
3. 写 decode：先限制字节数和像素数，再校验格式并让 OpenCV 解码。
4. 写磁盘空间检查。它是运行保护，不代表为任务预留磁盘容量。
5. 对照本节完整文件后放入练习区。

```powershell
& $py -B tools\course.py apply 6
```

## 从数据流解释设计
HTTP 只传 `source_id`，因为路径属于服务端配置。清单冻结意味着任务开始后新加的图片不会混进本次结果。每帧读取时再比对 size/mtime，避免“创建任务时是 A 文件，真正读取时已经变成 B 内容”。

`np.frombuffer` 把已有字节暴露为 uint8 数组，`cv2.imdecode` 才返回 H×W×3 图像。不要把前者误认为图像像素。Pillow 校验与 OpenCV 解码的职责也不等价于两次完整 JPEG 解码。

## 验收与练习
本版限制：20 MiB/图、4000 万像素、10000 张/任务、runtime 剩余空间保护阈值 1 GiB。准备一张正确 PNG 和一个仅后缀为 .png 的文本文件，观察后者为何应失败。第 8 节的实验会自动验证这一点。

教学配置中的数据集路径针对本机填写。搬到另一台机器后要修改 sources；不需要更改网页代码。
''',['reference/backend/settings.py','reference/backend/images.py','reference/configs/local.json'],'为什么任务启动时要冻结输入清单？',['保证本次遍历范围可解释','把所有图片永久放进内存','省略后续文件变化检查'],0,'冻结范围与逐帧变化检查互相补充。')

add(7,'实现 PostgreSQL 持久化','让一帧结果与运行汇总在同一事务中保存。',r'''
## 动手顺序
1. 写 Store 初始化：连接教学库，检查库名，获取单实例 advisory lock。
2. 建立 factory_runs 和 factory_frames。前者存任务，后者用 `(run_id,frame_id)` 作为主键。
3. 先实现 save_run，再实现 save_frame；后者在事务里插入 Frame 并更新 Run。
4. 实现 get_run、latest_run、runs、frames、frame 与 close。
5. 学习者准备好本机 PostgreSQL 管理员连接后，主动执行教学初始化脚本。

```powershell
& $py -B tools\course.py apply 7
& $py -B practice\factory_demo\scripts\setup_db.py
```

第二条命令会实际创建 `factory_demo_test_tutorial` 数据库和 `factory_demo_tutorial` 普通角色；管理员 URL 隐藏输入，不写入参考代码。本课程制作时没有执行它。已有同名库或角色会拒绝覆盖，需要你人工确认配置。

## 核心代码解释
`with self.lock, self.conn.transaction()` 有两个职责：进程内串行访问连接，以及数据库提交/回滚。它不能让文件系统写入自动加入 PostgreSQL 事务。快照文件已写但提交失败时，任务必须报错。

JSONB 保存复杂的 detections，关键定位字段另列出来用于主键和分页。图片字节放文件系统，image_path 放数据库。不要为每个框新增一条 SQL，当前结构已经按帧提交。

## 验收与练习
练习库 `.env` 存在且连接的是教学库；Store 明确拒绝原 factory_demo 库。初始化不等于完整 API 已可启动，后面的模块尚未完成。练习：解释如果 Frame INSERT 成功而 Run 更新失败，为何需要整个事务回滚。
''',['reference/backend/store.py','reference/scripts/setup_db.py','reference/.env.example'],'Frame 插入与 Run 汇总更新应该如何提交？',['同一事务','分别提交且忽略第二次失败','任务结束前都不保存'],0,'同一事务避免数据库帧数与累计数脱节。')

add(8,'实现 Runner 并用替身验证','把任务生命周期和模型计算解耦。',r'''
## 动手顺序
1. 先写 Runner 的成员：condition、current、thread、adapter、model。
2. 写 source 和 start：校验单活动任务、冻结清单、生成 UUID、保存 loading Run、启动后台线程。
3. 写 _frame：读取检查 → 快照与哈希 → adapter.predict → 组装 Frame。
4. 写 _work：模型加载复用、逐帧处理、事务保存、更新内存、限速和终态。
5. 最后写控制方法与关闭方法，先读第 10 节解释再核对。

```powershell
& $py -B tools\course.py apply 8
& $py -B examples\runner_lab.py
```

{{diagram:02-frame-pipeline}}

## 为什么先用教学替身
`TeachingAdapter` 输出固定示例，`MemoryStore` 只保留内存记录。实验运行的 Runner 是参考实现，但这不验证真实模型或数据库事务。这样出现错误时，你能先判断是任务逻辑问题，而不是 Torch、权重或 PostgreSQL 安装问题。

实验创建三张输入：黑图→合法空检测、非黑图→一个教学框、损坏 PNG→错误帧。预期 processed=3、succeeded=2、failed=1、detection_count=1。修改第二张源图后，已经保存的快照仍可解码。

## 重点代码解释
`updated=deepcopy(run)` 是候选新状态；`store.save_frame(updated,...)` 成功后才 `run.update(updated)`。如果先更新内存再提交，浏览器可能看见数据库里根本没有的最新帧。

## 验收与练习
实验终态是 completed，同时 failed=1，这不是矛盾：completed 表示遍历结束。尝试让教学适配器抛出 RuntimeError，观察与坏图的任务语义有何不同。不要把实验的零毫秒示例耗时当性能结果。
''',['reference/backend/runner.py','examples/fake_adapter.py','examples/runner_lab.py'],'为什么提交后再更新内存最新帧？',['避免发布未持久化结果','为了让模型重新加载','因为 JSON 不能复制'],0,'提交失败时，不能对外宣布已经保存成功。')

add(9,'把完整 HTTP API 连接起来','接入输入、Runner、存储与统一错误响应。',r'''
## 动手顺序
1. 在 app.py 先写 RunRequest/ControlRequest 和统一 fail 函数。
2. 写 create_app 与 lifespan：启动时建立 Settings、Store、Runner，退出时先结束工作线程再关连接。
3. 接入 health/capabilities、上传、创建任务与 status。
4. 接入运行控制、历史、原图和导出路由；细节在第 15 节继续拆解。
5. 使用教学替身启动完整 API。它需要第 7 节的独立数据库，仍不加载真实权重。

```powershell
& $py -B tools\course.py apply 9
& $py -B tools\serve_demo.py
```

打开 `http://127.0.0.1:8876/docs`。在 `/api/uploads` 上传一张小图，复制响应 source_id，在 `/api/runs` 中提交。查询 status，模型名称应清楚显示 TEACHING-ONLY-FAKE。目录源的 capabilities 可能提示权重未就绪，因此此阶段通过 API 文档验证，不要求工作台开始按钮可用。

## 关键边界
create_app 的 adapter_factory 是测试接缝：默认加载真实适配器，联调时注入替身。不要在生产 predict 里写“失败就返回假框”。统一 `{detail:{code,message}}` 让前端可以区分错误，但前端仍需处理网络断开和非 JSON。

## 验收与故障定位
health=200、合法任务=201、非法参数=422、同时创建第二个活动任务=409。如果 startup 失败先检查数据库名和角色权限，不要把 worker 改成 2 来绕过单实例锁。

练习：比较 HTTP 请求线程与推理工作线程；解释为什么创建任务请求不应该同步等待整个目录处理完才返回。
''',['reference/backend/app.py','tools/serve_demo.py','reference/start.py'],'adapter_factory 的用途是什么？',['注入可辨识的测试替身','真实推理失败时偷偷伪造结果','让浏览器直接加载权重'],0,'替身用于隔离测试，并明确标记其证据边界。')

add(10,'理解暂停、停止和恢复','把按钮动作转换成可验证的状态变化。',r'''
## 动手顺序
1. 对照 Runner.control，把 pause/resume/stop 各自允许的状态写成表。
2. 阅读 _boundary：pausing 转 paused，然后 condition.wait；resume/stop 通过 notify_all 唤醒。
3. 找到 _work 中 _boundary 的调用位置，确认它在每张图片开始前。
4. 阅读 Store 初始化中对遗留非终态任务的处理：变为 interrupted，不自动续跑。
5. 在教学服务中创建一个目录任务，验证暂停、恢复、停止。

## 为什么需要过渡状态
running 收到 pause 后先进入 pausing，因为当前图片可能还在 PyTorch 原生调用里。前端显示“正在暂停”比立刻显示“已暂停”更准确。类似地，stopping 不等于线程已经结束。

condition.wait 会在等待期间释放对应锁，唤醒后重新取得锁；如果用持锁死循环等待，控制请求就没有机会取得锁并改变状态。

## 验收与故障定位
暂停后处理数量稳定；继续后增长；停止后历史保留；终态不能 resume，只能新建 run_id。如果任务很短已经结束，pause 可能得到 409，或最后一帧后直接 completed，不要把它认定为暂停逻辑必错。

练习：画 loading/running/pausing/paused/stopping 与四个终态的关系。再解释为什么浏览器刷新不应该自动 POST 新任务。
''',[], '正在执行原生模型调用时，停止按钮应怎样工作？',['标记 stopping，在安全边界结束','强制杀死任意线程并保证无损','立即删除所有结果'],0,'控制动作与真正停止之间有边界；状态必须如实表达。')

add(11,'实现真实 PyTorch OBB 适配器','把模型专用数据转换成公共四点框协议。',r'''
## 动手顺序
1. 写 load：验证可信 .pt 路径，处理 vendor 导入，加载模型并设为所选设备/FP32/eval。默认CPU，云端用FACTORY_DEVICE=cuda:0显式选择；模型、预热和输入必须放在同一设备，CUDA计时在边界同步，设备不可用明确失败。云端Linux旋转NMS需重新编译，旧多边形THC实现不参与构建。
2. 预热后检查输出最后一维，获取权重类别和 stride，计算权重 SHA-256。
3. 写 predict 参数验证和输入验证。
4. 实现 letterbox、BGR→RGB、HWC→CHW、归一化和 batch 维。
5. 前向、有限值检查、旋转 NMS、rbox2poly、scale_polys，最后组装公共结果。

```powershell
& $py -B tools\course.py apply 11
```

{{diagram:03-inference-transform}}

## 张量逐步解释
OpenCV 解码 `[H,W,3]` BGR；transpose 后 `[3,H',W']`；颜色反转后需要连续内存；float/div_(255) 后值域为 0..1；unsqueeze(0) 得 `[1,3,H',W']`。

本权重 8 类 + 180 个角度分类值，候选最后一维为 5+8+180=193。letterbox auto=True 时短边随 stride 收缩，因此 640 配置不代表每张一定得到 640×640。

旋转框先转四点，再去除网络预处理的缩放/填充，恢复原图像素坐标。不要把普通 HBB NMS 当作等价替代。multi_label=True 是当前语义的一部分。

## 验收与练习
本节只实现适配器，直到下一节导入权重后才运行真实测试。解释 load 为什么不能每帧重复执行；解释 inference_mode 与 eval 分别控制什么。权重 8 类与数据集 7 类顺序不同，当前展示遵循权重类别，不直接计算精度。
''',['reference/backend/inference/pytorch_obb.py'],'为什么适配器必须恢复到原图坐标？',['前端与原图共享像素坐标系','为了把框变成标签真值','为了取消 letterbox'],0,'公共协议应隔离后端专用张量布局和预处理细节。')

add(12,'接入 vendor 与可信模型资产','把可复用模型代码与应用代码的边界固定下来。',r'''
## 动手顺序
1. 放置课程内的 vendor 基础代码、LICENSE、NMS 源码和当前平台扩展。
2. 使用导入工具把已知可信 factory_now.pt 复制到练习项目，先校验哈希再复制。
3. 检查练习配置里的数据集路径，移动电脑后需要修改它。
4. 停止之前的教学替身服务，再运行练习 start.py，避免同端口或同库双实例。

```powershell
& $py -B tools\course.py apply 12
& $py -B tools\import_weights.py --source 'C:\Users\13480\Desktop\codex_\factory_demo\vendor\weights\factory_now.pt'
& $py -B practice\factory_demo\start.py
```

## 需要理解的兼容边界
checkpoint 可能引用顶层 models/utils 名称，因此适配器检查当前进程是否已加载其他同名仓库。`.pyd` 是 Windows x64 / CPython 3.10 / 当前 Torch 环境编译结果，不保证跨平台或跨 Torch 版本使用。

本课程包含基础源码，不包含大权重和数据集副本，也不自动下载它们。导入工具只接受本课程已知哈希；要换模型应单独做适配验证，不删除哈希检查凑合运行。

## 验收与故障定位
真实任务的 model.name、device、sha256、classes 与教学替身明显不同。若缺少 nms_rotated_ext，先检查解释器和二进制兼容，不要仅根据“partially initialized module”认定是 Python 循环导入。

当前还未完成 Vue 页面，先通过 API 文档验证一张图；不要把 8876 根页面未构建理解为模型失败。
''',['tools/import_weights.py','reference/vendor/README.md'],'课程为何不自动加载未知的 .pt？',['checkpoint 必须来自可信来源并核对协议','所有 .pt 都只是无害纯文本','文件名相同就完全一致'],0,'权重可信性、内容哈希和输出协议是不同的检查。')

add(13,'把最小画布升级为真实组件','处理图片下载、异步竞态和图框一致性。',r'''
## 动手顺序
1. 创建 DetectionStage.vue，props 接收 Frame、classes、连接状态、筛选条件。
2. 编写 loadFrame：取消旧请求、设置超时、获取原图 Blob、等待 Image 加载。
3. 只有图像加载成功且 revision 仍有效时，提交 displayUrl 与 loaded Frame。
4. watch 帧键与连接状态；卸载组件时取消请求、释放 Blob URL。
5. 最后加入四点框、类别标签、缩放、全屏与错误占位。坐标标签默认关闭，点击或键盘选择框后显示 P1～P4；指针通过 SVG getScreenCTM().inverse() 映射回原图，留白范围显示空值。
6. 用 `display-change` 将 `{frame, selected, error, loading}` 通知父页。frame 只能取 loaded，不取最新 props.frame。新帧开始加载、失败、切任务时清空；筛选使目标不可见时也清除选择。

```powershell
& $py -B tools\course.py apply 13
```

{{diagram:04-display-sequence}}

## 关键变量分别负责什么
`props.frame` 是最新收到的元数据；`loaded` 是当前画布已成功加载的那一帧。两者不能混用。`revision` 阻止旧异步请求在新任务之后返回并覆盖界面。`AbortController` 控制取消，而版本号仍用于验证最终结果归属。

同一个 Blob URL 同时用于预加载与 SVG image，避免重新发第二次图片请求。URL.revokeObjectURL 是释放浏览器资源，不是删除服务端快照。

## 验收与练习
快速切换历史图片不会出现旧图叠新框；当前帧计数、坐标表与右侧目标详情只能使用画布通知的 Frame。测试 100% 与 125% 的同一原图点读数一致，切帧后不保留旧目标。当前实现开始新帧加载时会清空画布与详情，这可能短暂闪空；“保留上一张直到新图完成”是优化建议，本课程先复现现状。

练习：解释为什么不能直接监听整个 Frame 对象并每次轮询都重新下载图像。
''',['reference/frontend/src/components/DetectionStage.vue'],'画布上的框应使用哪个 Frame？',['已成功加载图片对应的 loaded Frame','任何最新收到的 Frame','累计框最多的 Frame'],0,'图片和检测必须绑定同一个 run_id/frame_id。')

add(14,'实现工业展示页与独立后台','实现只读深蓝大屏，并与浅色任务后台联调。',r'''
## 动手顺序
1. 创建 main.js 挂载 App；创建 api.js 统一超时、JSON 解析与业务错误。
2. AdminApp 中先写 ref/reactive 状态，再写 computed 展示值，最后写各操作函数和模板。
3. poll 用递归 setTimeout，在请求完成后再等 500ms，避免慢机器堆积并发轮询。
4. action 在操作前后增加 mutationVersion，阻止旧轮询响应覆盖刚创建的新任务。
5. 在 DisplayApp.vue 实现只读三栏页：左侧状态与类别，中间大画布，右侧运行指标与选中目标。顶栏使用“工业视觉检测展示系统 / FACTORY DEMO”。
6. 用 display-change 保存已加载帧和 selected，坐标表与当前帧数量只读这份状态；Run 累计数继续采用后端汇总。增加默认收起的坐标明细。
7. 新建 display.css，通过 DisplayApp 引入，每个主题选择器限定 `.display-page`。不要直接改全局 body 背景而污染 AdminApp。
8. 加入响应式布局、真实健康状态和本机时钟；结果查询完成后约 500ms 再查，健康查询完成后约 5 秒再查，两条循环各自不堆叠请求；清理卸载后的轮询与时钟；最后安装并构建。

```powershell
& $py -B tools\course.py apply 14
Push-Location practice\factory_demo\frontend
npm ci
npm run build
Pop-Location
& $py -B practice\factory_demo\start.py
```

如果 8876 服务仍在运行，先 Ctrl+C 正常退出再重启，不能启动第二份。构建完成后访问 `http://127.0.0.1:8876/admin.html` 配置和控制任务；`http://127.0.0.1:8876/` 仅显示结果。开发热更新可另开终端在 frontend 目录 `npm run dev`，访问 5176。

## 展示与后台分离（V1.2）
App.vue 只挂载 DisplayApp。DisplayApp 只 GET 状态、健康和图片，模型信息读取 Run 快照；AdminApp 负责参数、任务控制、历史与导出。admin.js 是第二入口，Vite 同时构建 index.html/admin.html。不要把历史和配置重新放回只读展示页。后台、手册和本教程保持浅色。

## 对照最终页面
![V1.2 选中目标后的四点坐标，来自已有真实结果](../evidence/industrial-display-selected.png)

这张图是正式项目的界面参考，展示已有真实检测记录；没有为截图新跑推理，不代表你的 practice 已经完成。先实现主体布局，再逐项对照类别、计数、坐标和状态，避免只复制颜色而遗漏数据来源。

## 先给每个数字写清含义
当前帧框数来自已加载 Frame，累计框数来自 Run.class_counts，不得在每次轮询时再次累加。置信度不是准确率，成功处理比例不是检测正确率，前向耗时不是端到端响应时间。没有机器人、功耗、温度的接口，就不放虚构仪表。连接失败时显示最后成功查询时间和旧结果提示；顶栏时钟只是本机时间。

## 深色布局的实现顺序
先写可读的 Grid 三栏和中央图像，再加面板细边框、角标与颜色。1920×1080 检查主画面占比，1366×768 检查文字与工具栏，390px 窄屏改成单栏。允许必要纵向滚动和表格局部横滚，不整体缩小字号，也不拉伸图片。

## 代码阅读顺序
先在 AdminApp 找 form 的默认值和 capabilities 的服务器配置覆盖；再找 startRun/control/upload；然后读 poll/action 的版本保护；最后读历史请求的 historyRequestVersion。模板只是把这些状态显示出来，不应自己推导数据库计数。

## 验收与故障定位
在后台上传单图→开始→打开独立展示页→看到真实模型名与框→切到历史→仍能打开同一帧。浏览器刷新不重复创建任务。若 API 可用而页面报错，先看代理端口、构建目录和非 JSON 响应，不要先改模型。再检查展示页没有 POST/PUT/DELETE 请求；后台仍为浅色；框选中后四点详情一致；切任务、加载失败、筛选后旧详情能清除。
''',['reference/frontend/src/DisplayApp.vue','reference/frontend/src/AdminApp.vue','reference/frontend/src/admin.js','reference/frontend/admin.html','reference/frontend/src/main.js','reference/frontend/src/api.js','reference/frontend/src/App.vue','reference/frontend/src/style.css','reference/frontend/src/display.css'],'为什么轮询使用请求完成后的 setTimeout？',['避免请求耗时变长时堆积并发请求','保证每秒一定显示两张图','自动提高模型 FPS'],0,'轮询调度影响请求密度，不决定模型计算速度。')

add(15,'实现历史查询与结果导出','从已保存记录生成可追溯的历史和下载。',r'''
## 动手顺序
1. 阅读 Store.runs/frames 的分页查询，确认 total 与 items 的含义。
2. 连接原图接口：通过 run_id/frame_id 查路径，再限定路径必须位于 runtime。
3. 实现 annotated：读取原图快照，用已保存 polygon 绘制，编码为 PNG。
4. 实现 JSON/CSV 导出：仅终态允许，按帧分页读取，保留错误帧。
5. 前端 download 获取响应 Blob，创建下载链接并在使用后释放 URL。

{{diagram:05-history-export}}

## 与推理流程的关系
历史和导出不调用 adapter.predict。原外部数据源被移动，已保存的快照仍能支持历史；但删除 runtime 会破坏原图访问。数据库不是原图备份，二者需要一起保留。

CSV 文件名、类别和错误字段可能被电子表格解释为公式，所以导出中保留相应转义。CSV 里的 polygon 是 JSON 字符串，不是另一种模型标签格式。

## 验收与练习
导出帧数等于 processed，逐帧框数之和等于累计数；坏图仍有错误记录；合法空检测仍有一帧。核对下载绘框 PNG 与工作台框属于同一帧。

练习：解释为什么后端 StreamingResponse 不保证浏览器导出时零内存占用，提示是前端使用 response.blob()。
''',[], '下载绘框 PNG 是否需要再次推理？',['不需要，读取快照和已保存框','必须重新预测才能画框','需要训练一个模型'],0,'绘图与推理是不同的处理，不能混为一次模型调用。')

add(16,'分层验证整个项目','分清例子测试、数据库测试、模型测试与真实流程。',r'''
## 动手顺序
1. 先运行无数据库、无模型的小例子检查。
2. 再运行真实 Runner + 内存存储实验。
3. 补齐练习测试文件，确认第 7/12/14 节的数据库、权重和前端都已准备。
4. 在练习目录运行 API 与推理测试。API 用教学库内唯一 schema，结束只清理自己的 schema；真实推理测试加载可信权重。

```powershell
& $py -B tools\check_examples.py
& $py -B examples\runner_lab.py
& $py -B tools\course.py apply 16
Push-Location practice\factory_demo
& $py -B -m pytest tests\test_api.py tests\test_inference.py -q --basetemp runtime\pytest-tmp
Pop-Location
```

这些命令属于你的学习验收步骤。本课程制作只运行前两类不连数据库、不加载模型的检查，不能把原项目通过的 20 项测试冒充为练习项目已重新通过。

## 继续做真实 50 张流程
让练习服务运行于 8876，在另一个终端执行：

```powershell
& $py -B practice\factory_demo\scripts\smoke.py --url http://127.0.0.1:8876 --output practice\factory_demo\runtime\evidence\smoke50.json
```

该命令会实际创建三个任务并推理 50 张，前提是权重和数据源路径就绪；完成课程之前不必提前执行。

## 验收与练习
分别记录静态检查、接口替身、真实数据库、真实模型、真实 HTTP、浏览器的证据。截图不能证明事务一致性；构建成功也不能证明模型可加载。练习：为“提交失败不能显示成功帧”写一个故障注入用例构想。
''',['tools/check_examples.py','reference/tests/test_api.py','reference/tests/test_inference.py','reference/scripts/smoke.py'],'教学替身的 API 测试通过，能证明什么？',['相应接口与生命周期逻辑','真实模型准确率已合格','完整数据集性能已测完'],0,'每类测试只证明其覆盖的层次。')

add(17,'学会解释性能指标','先明确计时边界，再谈优化。',r'''
## 动手顺序
1. 找到适配器里的 t0/t1/t2/t3，写下每段包含哪些操作。
2. 找到 Runner 的 read_ms 与 total，确认 total 是四段之和。
3. 找出不在其中的快照、哈希、数据库、回放等待、HTTP 和浏览器显示。
4. 做一个表格，分别写模型延迟、处理均值、任务吞吐与显示延迟的定义。

## 用已有记录理解主要耗时
原 factory_demo 的 50 张历史记录中，模型前向平均约 438.01 ms，占已计时处理耗时约 95.22%。这是原项目的已有证据，**不是你尚未运行的练习项目成绩**。外围全部归零也只能令该口径吞吐提高约 5%，说明优化应先找占比。

固定线程数 4 尚未证明最优。OpenVINO/TensorRT 需要独立适配与验证，不能拿旧 HBB 模型的加速比替当前 OBB 模型。提高置信度阈值可能减少候选，但也改变召回，不能称为无损优化。

## 验收与练习
解释为什么 replay_fps=10 不意味着模型达到 10 FPS。计算若前向从438降至219 ms、其余仍22 ms，总耗时是多少；答案约241 ms，不是原总耗时的一半。

正式指标由你用完整数据集独立测量。先处理权重8类与数据集7类的名称映射和额外类别规则，再计算准确率。
''',[], '1000 / 四阶段平均耗时代表什么？',['该计时口径的处理能力','浏览器端到端显示 FPS','分类准确率'],0,'模型、处理、任务、显示四种指标不能混用。')

add(18,'为新后端保留正确扩展边界','知道未来增加 OpenVINO/TensorRT 时具体改哪里。',r'''
## 动手顺序
1. 把 adapter.load 与 adapter.predict 的输入输出重新写成接口表。
2. 列出 load 必须给出的真实元数据：类别、设备、精度、权重标识。
3. 列出新后端需要替换的内容：模型加载、前向、必要的张量转换；必须对齐的内容：预处理、角度解码、旋转 NMS、原图坐标与类别。
4. 先写后端能力检查和同图对比方案，再计划启用 capabilities.available。

## 不要越过的边界
前端不用知道 .pt、IR 或 engine 的内部布局，但它需要知道后端是否真的可用。仅给下拉框增加一个名称，不代表适配完成。不能在 OpenVINO 执行失败后悄悄跑 PyTorch，却继续显示 OpenVINO。

单图、目录、任务状态、Frame 协议与历史应继续复用，不要为每个引擎复制一整套前端和数据库。与此同时也不要在只有一个真实适配器时提前造复杂插件系统。

## 验收与练习
写一份未来后端验收清单：原始输出对比、最终类别与四点框容差、精度评估、设备依赖、冷启动、稳态和完整处理耗时。这一节提交设计，不实现或测试尚未准备的引擎。
''',[], '何时可以把某个引擎标为 available=true？',['真实适配、能力检查与对齐完成后','把名字加进下拉框后','安装一个同名包后'],0,'可用性应代表实际执行链路，而不是静态配置。')

add(19,'独立复盘与项目交付','不看参考答案也能解释、重建和验证核心链路。',r'''
## V1.3 职责与工业展示检查
展示页只读取数据，坐标显示只改变本地视图；后台页管理配置、控制与历史。深色主题不能污染后台。逐个解释每张卡片的数据来源：当前完整展示帧、stream累计、WS连接状态还是本机时钟。检查同一 frame_key 和运行会话的画面、坐标表和选择详情一致；演示断线提示、空结果、125% 缩放、筛选清除选择和窄屏。先验证这组边界，再继续最终复盘。

## 最终复盘任务
1. 从一张图片出发，口述 source_id、输入清单、BGR、张量、候选、polygon、Frame、Run、image_path 的流向。
2. 指出当前代码中“先提交再发布”的位置，以及无法组成同一原子事务的文件写入。
3. 解释三个状态组合：completed 且 failed>0；status=ok 且 detections=[]；重启后 interrupted。
4. 展示真实模型的一张图、一次目录任务、暂停继续、停止和历史导出，并保存证据。
5. 给项目写 README：环境、启动、数据源、类别映射、限制、测试与未实现功能。

## 你最终应该能交付的内容
练习目录包含前端源码、后端模块、vendor基础代码、你主动导入的可信权重、独立配置、独立数据库连接及运行证据。不要把 `.env`、数据库管理员连接或大量运行缓存放入公开仓库。

课程复选框只保存在当前浏览器，表示你手工标记的学习进度，不是自动验收。更换浏览器、移动文件或清理站点数据可能导致记录不同；可以导出进度 JSON 留存。

## 最后一道独立练习
不用增加任何新框架，画出“运行过程中某张图片损坏”的分支：谁发现、谁记录、哪些计数增加、任务是否结束、历史如何显示。再画“数据库提交失败”分支，比较它们为何不能共用同一错误处理逻辑。

完成这些之后，你掌握的就不只是如何启动项目，还包括为什么要这样划分模块、保存数据和验证结果。
''',[], '学习完成的可靠证据是什么？',['能解释关键边界，并完成实际验收','勾选全部课程复选框','只打开首页看到了按钮'],0,'进度标记是辅助；可复现的实现与验证才是交付依据。')


# V1.3 revises the same 20-step course; practice files are never overwritten.
def revise(n, title, goal, body, files=None, quiz=None):
    lesson=LESSONS[n]
    lesson.update(title=title,goal=goal,body=body)
    if files is not None:lesson['files']=files
    if quiz is not None:lesson['quiz']=quiz

revise(0,'先理解本轮完整数据流','区分采集、推理、存储、展示与管理，而不急着拆多个服务。',r"""
## 先读本轮边界
生产相机先保存到本机磁盘，再由程序读取。当前有有限目录/上传与持续 inbox 模拟来源，真实模型仍是 PyTorch YOLOv5-OBB；OpenVINO/TensorRT 没有完成适配，机械臂没有接入。

控制线：后台HTTP请求→Runner控制意图→帧边界状态。计算线：已完成发布的图片→BGR→推理→原图四点。保存线：原图快照与PostgreSQL结果。显示线：提交后的结果→Presentation→独立JPEG预览→WS元数据+HTTP图片→stream配对解码→纯画布。

{{diagram:01-architecture}}

## 动手与验收
先画四条线，再指出哪条线没有浏览器也必须继续。写出为什么“预览允许跳过旧图”不等于“待检输入允许丢弃”。本课程20节完整源码更新到V1.3，但practice只由你手写或主动apply；参考代码不是你的运行证据。
""",quiz={'question':'浏览器连接展示WS会触发一次推理吗？','options':['不会，生产由后台任务推进','会，每个浏览器各推理一次','会，每个心跳加载模型'],'answer':0,'explain':'展示只订阅已产生结果，生产生命周期不能依赖观看者。'})

revise(2,'固定通用展示契约','先决定字段含义，再接入具体引擎。',r"""
## 动手顺序
1. 先运行小例子 `examples/protocol.py`，理解原图像素、有限数值、空检测和帧内编号。这是最小教学对象，不是完整V1.3网络快照。
2. 阅读 `backend/contracts.py` 的 stream_view / frame_view / detection_view。把旧管理Run/Frame投影成白名单，不输出模型路径和内部异常路径。
3. 分清frame_key（来源帧身份）与stream_session_id（运行会话）；continuous的total为null。
4. 写下preview的实际宽高、sx/sy/ox/oy。原图点(2048,1084)缩小四倍后画在(512,271)，坐标面板仍报原图值。
5. 阅读confidence、center_px、angle_deg、orientation_valid。HBB/数值正方形没有有效方向；图像角度不等于机械姿态。

## 验收与练习
给一份合法空检测、一份NaN、一份不同会话、一份错误类别、一份未知timing。未知用null，合法0必须保留。模拟回放没有真实capture_time时应为空，不能用published_at冒充曝光时刻。协议主版本不兼容应拒绝，未知可选字段可忽略。
""",files=['examples/protocol.py','reference/backend/contracts.py'],quiz={'question':'没有测量过的耗时应如何表示？','options':['null/未知','0且当作已测量','用目标FPS倒数补齐'],'answer':0,'explain':'缺失不能伪装测量为零；合法零值仍保留。'})

revise(6,'实现有限目录与持续落盘来源','让模拟拍照遵守真实文件完成发布边界。',r"""
## 动手顺序
1. 写Settings，只允许服务端配置source_id映射路径；普通目录保留冻结清单。
2. 写InboxSource：只扫描.ready.json，校验同目录图片、size/hash、身份和带时区时间；.part不消费。
3. 给已提交结果写私有回执；不删除相机图片。解释业务DB与SQLite回执并不是一个原子事务。
4. 用simulate_camera.py生成小批文件，观察图片先完成，再发布ready。

```powershell
& $py -B tools\course.py apply 6
& $py -B practice\factory_demo\scripts\simulate_camera.py --input-dir 'C:\Users\13480\Desktop\codex_\yolov5_obb-master\dataset\dataset4911_obb_smoke_50\test\images' --output-dir 'practice\factory_demo\runtime\camera_inbox' --count 10 --fps 5
```

## 边界和验收
此时只验证文件发布，不运行模型。图片保持原尺寸/编码；capture_time=null。持续来源total=null，空目录等待，停止需后台命令；暂停推理不暂停相机。未消费清单超过10000会失败，不静默丢帧。

20MiB仍是图片上限，4096×2168未压缩BGR8约25.41MiB，不能直接当作已支持的输入。目录和回执没有自动清理；长期扫描与42fps实际推理需要另测。
""",files=['reference/backend/settings.py','reference/backend/images.py','reference/backend/acquisition.py','reference/scripts/simulate_camera.py','reference/configs/local.json'],quiz={'question':'何时可以消费相机图片？','options':['完成图片发布且ready清单有效后','文件名刚出现就读取','文件大概稳定就一定完成'],'answer':0,'explain':'发布协议比猜测文件大小稳定可靠；模拟器应验证这个边界。'})

revise(8,'实现Runner与提交后的展示支路','让控制、数据库和展示各自有明确完成语义。',r"""
## 动手顺序
1. 写单活动任务、来源选择、模型缓存和短状态锁。
2. 写有限遍历与inbox持续等待；在帧边界处理pause/stop，持续模式不靠replay_fps限速。
3. _frame校验/解码/保存快照/调用推理；保存Frame与Run事务成功后才发布。
4. 维护内存latest_frame，让status不重复查库；恢复旧记录只在初始化做。
5. 将已提交帧交给Presentation。独立预览线程做JPEG，有界待处理槽可替代旧预览，不能替代待检输入。

```powershell
& $py -B tools\course.py apply 8
& $py -B examples\runner_lab.py
```

{{diagram:02-frame-pipeline}}

## 验收与边界
runner_lab使用真实Runner、内存Store和TeachingAdapter，预期3帧、2成功、1失败、1框；不代表真实模型或DB。数据库失败仍会影响任务，内存状态不代表离线持续生产。控制请求受理与当前原生模型调用结束不同。

练习：画出worker保存结果时用户请求stop的交错，解释为什么旧running副本不能覆盖新的stopping意图。
""",files=['reference/backend/runner.py','reference/backend/presentation.py','examples/fake_adapter.py','examples/runner_lab.py'])

revise(9,'连接管理HTTP与只读展示WS','将生产控制和展示订阅放在不同协议职责。',r"""
## 动手顺序
1. create_app组装Settings、Store、Presentation、Runner，退出时有界结束工作线程。
2. 管理接口保留上传、创建/控制、历史、导出；运行请求不能任意指定本机路径。
3. 新增 /api/display/snapshot、/api/display/ws 和 /api/display/previews/{id}.jpg。
4. WS连接先给快照，变化时推送；无变化发heartbeat；发送控制消息必须拒绝。
5. 使用教学替身服务验证API；需要第7节教学数据库，但不加载大权重。

```powershell
& $py -B tools\course.py apply 9
& $py -B tools\serve_demo.py
```

打开8876/docs，创建小图任务后读取display/snapshot。它是安全展示投影，不应该带C盘模型路径；旧/api/status仍供后台使用。预览URL不可变，但缓存有界，过期返回410；不能承诺永远可取。

## 验收
合法创建201、错误参数422、并发任务409；展示WS不允许生产控制。服务启动仍需数据库，数据库健康接口不是相机或模型健康证明。没有浏览器时任务也继续。
""",files=['reference/backend/app.py','tools/serve_demo.py','reference/start.py'])

revise(13,'将画布变成纯展示组件','把网络与图片生命周期移到stream，保留同帧坐标正确性。',r"""
## 动手顺序
1. 阅读stream/contract.js：validateSnapshot检查协议；toViewInput转换实时；legacyViewInput转换历史。
2. 阅读frameLoader.js：图片URL读取、解码、ObjectURL所有权、旧代失效和预览变换。
3. 通过usePreparedFrame.js接Vue状态，画布只收已解码ViewFrame，不fetch、不认识Run结构。
4. 在DetectionStage中保留框选择、筛选、缩放、全屏、指针逆CTM；已加载类表与图片一起提交。
5. 实时使用1个在途+1个最新等待帧，避免高频事件反复取消慢解码导致永远无画面；历史手选则及时替代旧请求。

{{diagram:04-display-sequence}}

## 验收与练习
旧图片与框完整保留，直到下一合法图解码后原子切换；新会话作废旧请求。用慢图、失败图、快速手选、不同预览尺寸测试，不得新框旧图。125%缩放和全屏时同一点原图坐标不变。有效角度展示、无效方向显示未知，中心不等于抓取点。
""",files=['reference/frontend/src/stream/contract.js','reference/frontend/src/stream/frameLoader.js','reference/frontend/src/stream/usePreparedFrame.js','reference/frontend/src/components/DetectionStage.vue'],quiz={'question':'为什么实时取图不在每个新事件都立即取消旧请求？','options':['慢解码可能永远完不成，需要有界等待和完整提交','这样就不需要帧身份','为了让图片和框分开刷新'],'answer':0,'explain':'实时采用有界调度保证有进展，仍须会话和身份校验。'})

revise(14,'接入WS并保持展示与后台分离','同一前端构建连接真实或模拟协议后端。',r"""
## 动手顺序
1. useDisplayStream连接WS，处理snapshot/heartbeat、连接代次和重连。
2. DisplayApp只读stream/已解码帧，不轮询status/health，不硬编码引擎名称。
3. 保留深蓝三栏、类别、坐标明细、中心与角度；累计值来自后端，不对预览重复累加。
4. AdminApp保留HTTP控制/历史；legacyViewInput经相同frameLoader进入纯画布，下载仍从后台处理。
5. continuous来源空目录允许等待，隐藏有限任务百分比和无意义的回放FPS。
6. 构建双入口，分别打开8876/与8876/admin.html。

```powershell
& $py -B tools\course.py apply 14
Push-Location practice\factory_demo\frontend
npm ci
npm run build
Pop-Location
& $py -B practice\factory_demo\start.py
```

开发端口仍5176，代理到8876并支持WS。服务已运行时先Ctrl+C正常退出，不开启同库第二实例。

## 同一构建验证
完成第16课放置mock脚本后，可运行它直接托管同一份dist：默认8879，不连数据库、不加载Torch。也可用 `?display_origin=http://127.0.0.1:8879` 指定本机展示后端；跨端口图片需要对应服务允许读取，直接同源托管最简单。

## 验收
展示没有POST/PUT/DELETE，不因模型标签变化改Vue源码；mock数据明确标注。图片/类表/坐标原子，未知计时显示—且合法0保留。连接与结果新鲜度分开；页面“距今”是本机时钟差，不是未经同步的曝光到显示时延。历史页仍能选择原图、下载并保留浅色风格。
""",files=['reference/frontend/src/stream/useDisplayStream.js','reference/frontend/src/DisplayApp.vue','reference/frontend/src/AdminApp.vue','reference/frontend/src/admin.js','reference/frontend/admin.html','reference/frontend/src/main.js','reference/frontend/src/api.js','reference/frontend/src/App.vue','reference/frontend/src/style.css','reference/frontend/src/display.css'],quiz={'question':'更换符合契约的推理后端时，展示源码应怎样变化？','options':['不改展示源码，只更换连接/服务实现','增加每种引擎的张量解析','把控制按钮移回展示页'],'answer':0,'explain':'通用性由稳定契约和数据适配层实现。'})

LESSONS[16]['body'] += r"""

## V1.3 协议与独立mock验证
apply16还放置scripts/mock_display.py与frontend/tests。先在前端目录运行 `node --test tests/stream.test.mjs`，再运行 `& $py -B practice\factory_demo\scripts\mock_display.py --port 8879`。打开8879，实际托管的是相同dist，图像为明确标记的模拟数据。不要同时占用其他任务已使用的端口。

新增后端契约/展示/来源测试属于隔离层测试，真实DB/模型测试仍需前述环境。每项通过只证明对应层，不把mock计时当真实推理。
"""
LESSONS[16]['files'] += ['reference/scripts/mock_display.py','reference/frontend/tests/stream.test.mjs']
LESSONS[18]['body'] += '\n\nV1.3 已有 inference/factory.py 的小型显式工厂与能力描述；仅PyTorch可用。新增后端先实现契约和真实数值对照，不能只把available改为true。\n'
LESSONS[18]['files'] += ['reference/backend/inference/factory.py']
LESSONS[19]['body'] += r"""

## V1.3 交付复盘
用同一份dist分别接真实服务与mock，检查不同类别、尺寸、HBB/OBB、无目标、null/0与会话切换。再验证落盘模拟器：.part不读取、ready发布后读取、重复通知不当新帧、持续流total=null、后台停止后退出。测试图像/类别原子提交、历史下载、慢解码不饥饿以及WebSocket只读。

文档中的旧V1.2截图是外观历史证据，不是V1.3性能证明。生产仍先落盘，数据库故障继续生产策略未定，当前仅本机访问。practice中的手写文件不由课程更新覆盖；若与新reference不同，手动理解并迁移，不强制覆盖。
"""

# CLOUD_LESSON_SUPPLEMENT: embed the deploy chapter in lesson 11 for offline reading.
LESSONS[11]['body'] += '\n\n## AutoDL 云端 GPU 部署与复现\n\n日期：2026-10-28。代码在 `/root/autodl-tmp/factory_demo`，图片数据在同级 `dataset/`。云端使用独立 Conda 环境 `factory_demo`；本机继续使用 `yolo_v5_obb`。本页描述新增 CUDA 路径，旧 CPU 验收记录仍保留原环境含义。\n\n## 1. 创建环境与安装依赖\n\n```bash\nconda create -n factory_demo python=3.10 pip -y\nconda activate factory_demo\npython -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124\ncd /root/autodl-tmp/factory_demo\npython -m pip install -r requirements-cloud-cu124.txt\npython -m pip check\n```\n\n约束：此清单针对 Linux/RTX 3080 Ti，不替换本机环境。CUDA Toolkit 和驱动属于额外系统依赖。GPU 可用还需实际运算和模型测试；不能把 nvidia-smi 中的 CUDA 13.0 当作 Toolkit 版本。当前服务器驱动580.76.05、Toolkit12.8、GCC11.4、PyTorch CUDA12.4；次版本差异有警告，本次编译和实际运行已验证。\n\n## 2. 数据源与设备选择\n\n服务器 `.env` 在数据库连接之外增加：\n\n```dotenv\nFACTORY_CONFIG=/root/autodl-tmp/factory_demo/configs/cloud.json\nFACTORY_DEVICE=cuda:0\n```\n\ncloud.json 三组图片路径为 `../dataset/dataset4911_obb_smoke_50/{test,val,train}/images`，不再依赖原始 yolov5_obb-master 目录。`runtime/camera_inbox` 为持续落盘来源。\n\n约束：设备只接受 cpu 或 cuda:N。默认CPU，指定CUDA不可用时明确失败，不自动回退。设备是服务启动配置，不允许浏览器任意切换。仍为单进程、单任务、单张FP32；模型参数、阈值、类别表和展示协议保持一致。PyTorch CUDA不代表TensorRT已实现。\n\n## 3. Linux 旋转 NMS 编译\n\n```bash\nconda activate factory_demo\ncd /root/autodl-tmp/factory_demo/vendor/yolov5_obb/utils/nms_rotated\nCUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.6 MAX_JOBS=2 python -B setup.py build_ext --inplace\n```\n\n约束：8.6对应RTX 3080 Ti，换卡须核对架构。Windows .pyd不能用于Linux；生成的.so和build目录不进Git。换PyTorch、Python或平台后重新编译。`FORCE_CPU=1`显式只构建CPU，该产物不能处理CUDA输入。\n\n构建包含CPU/CUDA旋转OBB NMS。旧poly_nms_cuda.cu作为来源保留但不编译，应用不支持任意多边形NMS。CUDA guard和整除更新为兼容接口；原始索引在输入设备创建，避免过滤小框后CPU/CUDA索引混用。保留原IoU计算与抑制算法。\n\n模型、预热和输入都使用所选设备。CUDA阶段计时在边界同步；预处理包括主机到设备传输，后处理包括返回JSON所需的数据传输。同步有额外成本，这不是异步流水线性能上限，也不包含数据库、预览、网络和动作执行。\n\n## 4. 独立 PostgreSQL\n\n本轮安装PostgreSQL14，创建仅用于本应用的factory_demo数据库及同名普通角色，随机密码只写服务器.env。数据目录为 `/var/lib/postgresql/14/main`。\n\n在另一台全新Ubuntu22.04服务器上，首次初始化可执行以下命令；本轮服务器已完成，不要重复执行创建账户/数据库：\n\n```bash\napt-get update\napt-get install -y postgresql\npg_ctlcluster 14 main start\ncd /tmp\nrunuser -u postgres -- createuser --pwprompt --no-superuser --no-createdb --no-createrole factory_demo\nrunuser -u postgres -- createdb --owner=factory_demo factory_demo\n```\n\n在密码提示中输入独立密码，然后在项目.env设置对应DATABASE_URL，格式参考.env.example；密码含URL保留字符时须编码。保留前述FACTORY_CONFIG及FACTORY_DEVICE。不要把密码写进命令行、Git或公开日志。\n\n```bash\npg_lsclusters\npg_isready -h 127.0.0.1 -p 5432\n# 容器重启后若14/main未运行：\npg_ctlcluster 14 main start\n```\n\n约束：数据库只接受本机连接，应用账户不是超级用户，不复用本机密码，.env不进Git。冷启动和成功结果提交仍依赖数据库，故障仍结束任务。Conda中的psycopg只是客户端；不要重复初始化或覆盖已有库。释放实例前应按平台规则备份系统盘数据库，上传源码不能恢复历史。\n\n## 5. 启动和访问\n\n```bash\nconda activate factory_demo\ncd /root/autodl-tmp/factory_demo\npython -B start.py\n```\n\nAPI保持服务器127.0.0.1:8765，展示路径/，管理/admin.html。已上传dist时不需要Node.js。需要重建前端时执行npm ci / npm run build。\n\n管理HTTP请求限时30秒，适应SSH链路首包较慢的情况；本轮一次状态请求曾达13.7秒。慢网络仍可能超时，状态提示反映通信，不改变后台推理。展示继续使用只读WS，预览独立HTTP加载。\n\n历史页需要下载原图，加载限时60秒；实时展示的压缩预览仍限时10秒，队列策略不变。超时不是未检出，不允许把未加载的图片与新坐标合并显示。\n\n本机建立SSH隧道后访问 http://127.0.0.1:18765/ ：\n\n```bash\nssh -p <SSH端口> -L 18765:127.0.0.1:8765 root@<SSH主机>\n```\n\n约束：保持Host/Origin的本机边界，不直接开放公网管理或数据库端口。浏览器关闭不停止任务。只允许一个应用实例，不增加Uvicorn workers；后台运行时核对PID后发送SIGTERM，前台运行时Ctrl+C停止。\n\n本轮后台服务PID、日志、编译和验证日志位于 `/root/autodl-tmp/tmp/factory-cloud-20261028/`。服务器重启后PID会变化，不能直接沿用旧PID。部署前备份位于其中backup-initial，包含私密.env，不上传仓库。\n\n## 6. 验证与边界\n\n```bash\ncd /root/autodl-tmp/factory_demo\npython -B -m pytest tests -q\npython -B scripts/smoke.py --output runtime/cloud-smoke50.json\n```\n\nGPU测试覆盖随机旋转框跨64框分块、过滤索引、空输入、全小框、自定义CUDA stream及真实模型CPU/CUDA FP32对照。真实模型对照容差为角点1像素绝对误差加0.1%相对误差、置信度0.002；不要求跨平台逐位一致。\n\n约束：API测试创建独立schema，不指向其他项目数据库。smoke用50张验证流程，不计算精度或全量指标。模拟落盘、WS、历史和预览另行联调。没有工业相机、编码器、机械臂，不以GPU可用、短样本均值或模拟42fps证明生产42fps和动作时限。\n\n实际结果见 [云端验收证据](evidence/cloud-validation-20261028.json)。更改环境或实现后需要重新验证。\n'
