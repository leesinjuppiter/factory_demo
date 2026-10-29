"""Rebuild this frozen report from summary.json and pipeline-frames.csv, offline."""
import csv
import html
import io
import json
from pathlib import Path
import re

import markdown
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

OUT=Path(__file__).resolve().parent
S=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
A=json.loads((OUT/'additional-analysis.json').read_text(encoding='utf-8'))
P=S['pipeline']; B=S['baseline']; T=P['stages_ms']; E=S['environment']
FONT=FontProperties(fname=r'C:\Windows\Fonts\msyh.ttc') if Path(r'C:\Windows\Fonts\msyh.ttc').exists() else FontProperties(family='DejaVu Sans')
plt.rcParams.update({'font.size':15,'svg.fonttype':'path','axes.unicode_minus':False})
plt.rcParams['svg.hashsalt']='factory-demo-full4911-20261028'


def chart(slug,title,labels,values,subtitle):
    fig,ax=plt.subplots(figsize=(1280/72,720/72),facecolor='#f2f4f3')
    fig.subplots_adjust(left=.24,right=.90,top=.79,bottom=.20)
    ax.set_facecolor('#f2f4f3')
    means=[v['mean'] for v in values]; p95=[v['p95'] for v in values]; focal=means.index(max(means))
    ax.barh(range(len(labels)),means,height=.64,color=['#d6e9df' if i==focal else '#dbe1df' for i in range(len(labels))],edgecolor=['#177b68' if i==focal else '#52676b' for i in range(len(labels))],linewidth=1.2,zorder=3)
    ax.scatter(p95,range(len(labels)),marker='D',s=45,color='#203039',zorder=4)
    ax.set_yticks(range(len(labels)),labels,fontproperties=FONT,fontsize=17)
    ax.invert_yaxis();ax.set_xlim(0,max(p95)*1.25)
    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5));ax.grid(axis='x',color='#203039',alpha=.08,zorder=0)
    for name in ['top','right','left']:ax.spines[name].set_visible(False)
    ax.spines['bottom'].set_color('#9eada5');ax.tick_params(length=0,pad=10,colors='#52676b')
    ax.set_xlabel('每帧耗时 / ms（横轴从 0 开始）',fontproperties=FONT,fontsize=15,labelpad=16)
    for i,(a,b) in enumerate(zip(means,p95)):
        ax.text(b+.35,i,f'{a:.2f} / {b:.2f}',va='center',fontproperties=FONT,fontsize=14,color='#203039')
    fig.text(.045,.92,title,fontproperties=FONT,fontsize=27,color='#203039',weight='bold')
    fig.text(.045,.86,subtitle,fontproperties=FONT,fontsize=16,color='#52676b')
    fig.text(.045,.09,'条形：均值    ◆：P95    数值：均值 / P95    n = 4911',fontproperties=FONT,fontsize=15,color='#52676b')
    fig.text(.045,.045,'来源：本次服务器逐帧记录；同一帧各阶段的 P95 不可相加。2026-10-28',fontproperties=FONT,fontsize=13,color='#52676b')
    stream=io.StringIO();fig.savefig(stream,format='svg');fig.savefig(OUT/(slug+'.png'),dpi=72);plt.close(fig)
    svg=stream.getvalue();svg=svg[svg.index('<svg'):]
    svg=re.sub(r'[ \t]+\n','\n',svg)
    svg=re.sub(r'width="[^"]+" height="[^"]+"','width="1280" height="720"',svg,count=1)
    svg=svg.replace('<svg ','<svg role="img" aria-labelledby="'+slug+'-title '+slug+'-desc" ',1)
    svg=svg.replace('version="1.1">','version="1.1"><title id="'+slug+'-title">'+html.escape(title)+'</title><desc id="'+slug+'-desc">'+html.escape(subtitle)+'；横轴毫秒，条形为均值，菱形为P95。</desc>',1)
    # Prefix Matplotlib-generated clip/glyph IDs to keep both inline charts unique.
    ids=re.findall(r'id="([^"]+)"',svg)
    for ident in sorted(ids,key=len,reverse=True):
        if ident.startswith(slug+'-'):continue
        svg=svg.replace('id="'+ident+'"','id="'+slug+'-'+ident+'"').replace('#'+ident+'"','#'+slug+'-'+ident+'"').replace('#'+ident+')','#'+slug+'-'+ident+')')
    return svg


def table(rows,headers):
    return '|'+ '|'.join(headers)+'|\n|'+'|'.join('---' for _ in headers)+'|\n'+''.join('|'+ '|'.join(str(c) for c in row)+'|\n' for row in rows)


def stage_rows(items):
    return [[label,v['n']]+[f"{v[k]:.3f}" for k in ['mean','p50','p95','p99','maximum']] for label,v in items]


main=list(P['main_groups_ms'].items())
chart1=chart('main-chain','主链路：读图、推理和应用开销均有优化空间',[k for k,_ in main],[v for _,v in main],'从空间检查开始，到当前帧数据库提交并发布完成；七组互不重叠。')
preview_keys=[('快照重新读取','preview_snapshot_read_ms'),('预览重新解码','preview_decode_ms'),('预览缩放','preview_resize_ms'),('JPEG 编码','preview_jpeg_encode_ms'),('队列等待','preview_queue_wait_ms')]
chart2=chart('preview-chain','并行预览：缩放与重复解码占据主要时间',[k for k,_ in preview_keys],[T[k] for _,k in preview_keys],'在独立线程执行，与推理共享 CPU；本图不能加到主链路总耗时。')
groups_table=table(stage_rows(main),['互斥主链路分组','样本数','均值ms','P50ms','P95ms','P99ms','最大ms'])
details=[('文件 stat','stat_ms'),('原图字节读取','file_read_ms'),('SHA-256','integrity_hash_ms'),('原图解码','decode_ms'),('letterbox','letterbox_ms'),('布局/连续内存转换','layout_ms'),('H2D/类型/归一化','h2d_normalize_ms'),('候选筛选/旋转NMS','nms_ms'),('坐标还原/结果组装','coordinate_result_ms'),('几何属性补充','geometry_enrich_ms'),('可用空间检查','space_check_ms'),('运行统计/复制','stats_copy_ms'),('数据库保存/提交','db_commit_ms'),('结果发布','publish_ms'),('单帧活动周期','active_cycle_ms'),('旧界面处理total','processing_ms')]
detail_table=table(stage_rows([(label,T[key]) for label,key in details]),['细分阶段','n','均值ms','P50ms','P95ms','P99ms','最大ms'])
preview_details=[('预览排队','preview_queue_wait_ms'),('预览重新读取','preview_snapshot_read_ms'),('预览重新解码','preview_decode_ms'),('预览缩放','preview_resize_ms'),('JPEG编码','preview_jpeg_encode_ms'),('字节打包/UUID/描述','preview_pack_bytes_ms'),('缓存更新/发布','preview_cache_publish_ms'),('预览工作总区间','preview_preview_work_ms'),('帧处理开始→预览就绪','frame_to_preview_ms'),('DB提交→预览就绪','commit_to_preview_ms'),('WS发送开始→本机接收','ws_send_start_to_local_receive_ms'),('观察器等待下载','observer_wait_ms'),('本机JPEG HTTP接收','observer_http_ms'),('本机JPEG解码','observer_decode_ms'),('帧处理开始→本机解码完成','frame_to_local_decode_ms')]
preview_table=table(stage_rows([(a,T[b]) for a,b in preview_details]),['并行显示指标','n','均值ms','P50ms','P95ms','P99ms','最大ms'])
resource_table=table([[label]+[f"{S['resources'][phase][key]['mean']:.2f} / {S['resources'][phase][key]['maximum']:.2f}" for phase in ['baseline','pipeline']] for label,key in [('进程CPU %','process_cpu_percent'),('进程RSS MiB','process_rss_mib'),('整卡GPU利用率 %','gpu_util_percent'),('GPU显存 MiB','gpu_memory_mib'),('GPU功率 W','gpu_power_w'),('GPU温度 ℃','gpu_temperature_c')]],['资源（均值 / 采样最大）','基线','应用链路'])
split_table=table([[split,v['images'],v['failed'],v['detections'],f"{v['pipeline_worker_seconds']:.3f}",f"{v['pipeline_worker_fps']:.3f}"] for split,v in S['splits'].items()],['划分','图片','失败','框数','worker秒','worker FPS'])
compare_labels={'file_read_ms':'原图字节读取','integrity_hash_ms':'SHA-256','decode_ms':'原图解码','preprocess_ms':'预处理','inference_ms':'模型前向','postprocess_ms':'后处理','geometry_enrich_ms':'几何补充'}
comparison_table=table([[compare_labels[k],f"{v['baseline_mean']:.3f}",f"{v['pipeline_mean']:.3f}",f"{v['difference_ms']:+.3f}"] for k,v in A['comparison_ms'].items()],['共同阶段','基线均值ms','应用均值ms','差值ms'])
slow=list(csv.DictReader((OUT/'pipeline-frames.csv').open(encoding='utf-8')))
assert len(slow)==4911
slow=sorted(slow,key=lambda r:float(r['active_cycle_ms']),reverse=True)[:15]
slow_table=table([[r['split'],r['relative_path'],r['frame_id'],r['detections']]+[f"{float(r[k]):.2f}" for k in ['active_cycle_ms','file_read_ms','decode_ms','inference_ms','space_check_ms','db_commit_ms']] for r in slow],['划分','相对图片路径','帧ID','框数','周期ms','读字节ms','解码ms','前向ms','空间检查ms','DBms'])
db_delta=P['database_after']['bytes']-P['database_before']['bytes']
mean=T['active_cycle_ms']['mean'];forward=T['inference_ms']['mean'];input_mean=main[0][1]['mean']
report=f'''# Factory Demo · 完整 4911 张性能测试与优化依据

测试日期：2026-10-28；离线复核与报告整理：2026-10-29。状态：**两种条件均完成 4911/4911，失败 0；本轮只测量与分析，未实施性能优化。** 服务器目前已断开，以下运行状态均指测试结束时留存的证据。

## 1. 先看实际结果

|口径|处理图片|墙钟耗时|实际吞吐|包含内容|
|---|---|---|---|---|
|基线链路|4911|{B['wall_seconds']:.3f} 秒|{B['fps']:.3f} 张/秒|读图、哈希、解码、预处理、GPU前向、后处理、几何信息及CSV记录|
|完整应用链路|4911|{P['scenario_wall_seconds']:.3f} 秒|{P['scenario_fps']:.3f} 张/秒|真实API创建任务、原图快照、统计、PostgreSQL提交、结果发布；包含三次任务之间的请求/轮询间隔|
|应用worker区间|4911|{P['worker_wall_seconds']:.3f} 秒|{P['worker_fps']:.3f} 张/秒|三个服务端run_start到run_end区间之和，排除任务间API间隔|

应用单帧活动周期均值 **{mean:.3f} ms**，P50 **{T['active_cycle_ms']['p50']:.3f} ms**，P95 **{T['active_cycle_ms']['p95']:.3f} ms**，P99 **{T['active_cycle_ms']['p99']:.3f} ms**。旧界面的total均值为{T['processing_ms']['mean']:.3f} ms，其倒数约{1000/T['processing_ms']['mean']:.2f} FPS；它漏掉数据库等环节，不能当作实际应用吞吐。

两个条件同时改变了预览、ASGI、观察器等工作负载，可能伴随资源与锁竞争；没有关闭预览的配对试验，不能分离各因素的因果贡献，也不能把增加的{P['scenario_wall_seconds']-B['wall_seconds']:.3f}秒全部归于数据库或原图写盘。两组是不同工作负载条件，不是优化前后对照。

## 2. 固定条件与输入边界

- 服务器：Ubuntu22.04.5 / Linux5.4，RTX3080Ti 12GiB，驱动580.76.05，Toolkit12.8.93，GCC11.4。
- 独立Conda：`/root/miniconda3/envs/factory_demo/bin/python`，Python3.10.22，PyTorch2.5.1+cu124、torchvision0.20.1、NumPy1.26.4、OpenCV4.10.0.84。完整包版本在environment.json。
- 容器可见48个逻辑CPU，但cgroup配额相当于12个CPU；内存上限90GiB。不能按48核独占机器解读。
- 数据集：`/root/autodl-tmp/dataset/dataset4911_obb_622`，train2947 / val982 / test982，按划分及文件排序，保留原划分，只测性能。
- 4911张均为**1580×1080**，共1,526,260,344字节（约1.421GiB）；4911个不同SHA-256。不是规划中的4096×2168工业相机负载。
- 权重`factory_now.pt`，175,615,389字节，SHA-256：`62af01dbc971d332ad4813d5f2811243f555877ffbdb0755fe428159687ef037`。
- PyTorch / cuda:0 / FP32 / batch1 / image_size640 / confidence0.25 / IoU0.45 / max_det300；实际自动letterbox张量在trace中核实为`[1,3,448,640]`，不是固定640×640。
- 应用单进程、单任务、单帧串行推理；数据库PostgreSQL14.24在本机，synchronous_commit=on、fsync=on、track_io_timing=off。
- 保留默认replay_fps=10参数，仅在追踪开启且设置`FACTORY_BENCHMARK_UNPACED=1`时跳过回放等待。测试结束时的记录显示正式服务已撤去两个测量变量；代码保留常规10fps上限。本轮不检查服务器当前状态。

**预热与缓存**：正式计时前读取并哈希全部输入；没有清理OS缓存。基线、应用各先用前10张实际图片预热，加载及预热不计入4911张墙钟。此测试偏向已缓存文件读取，不能称为冷磁盘吞吐。每个条件只有一次完整有效测量，P95/P99描述图片混合分布，不是多轮置信区间。

## 3. 主链路：哪些环节占时间

{{{{MAIN_CHART}}}}

{groups_table}

总活动周期起点在空间检查前，终点在该帧提交后结果发布完成；七组均值相加等于{mean:.3f}ms。各阶段P95/P99不能相加。其他开销为活动周期减去六个已测分组的逐帧差值，包含对象构造、调用、计时与部分追踪开销；没有强行归因。

{detail_table}

**阶段约束**：H2D/归一化含CPU→GPU传输、类型转换与归一化；nms_ms含有限性检查、候选筛选/CSL和旋转NMS，并非裸CUDA内核。数据库区间含Python序列化、应用锁、本机协议、SQL及commit，不能称服务器纯SQL耗时。原图快照使用write_bytes返回，没有fsync，0.368ms不代表磁盘持久化延迟。pacing_wait均值{T['pacing_wait_ms']['mean']:.4f}ms是发布后边界开销，本轮没有主动回放sleep。

## 4. 并行展示：图片和识别结果到达的延迟

{{{{PREVIEW_CHART}}}}

{preview_table}

本轮4911张全部产生预览，4911张均被本机观察器HTTP接收并解码，HTTP全部200，没有待处理队列替换。JPEG平均约{A['jpeg_bytes']['mean']/1024:.2f}KiB，P95约{A['jpeg_bytes']['p95']/1024:.2f}KiB。全程观察器计数4922还包括10张预热和启动时的旧快照；统计已按三个正式run_id过滤为4911。

观察器通过本机WS接收帧元数据，用容量1的待取队列取最新JPEG，再由Pillow解码；它是可控本机消费者，不是实际浏览器、公网HTTPS延迟或绘制耗时。WS测量事件{S['display']['ws_send_ms']['n']}次，包含状态变化和多订阅者，不能当图片数。服务端send_json均值{S['display']['ws_send_ms']['mean']:.3f}ms，P95 {S['display']['ws_send_ms']['p95']:.3f}ms，包含序列化与ASGI背压，不等于纯网络耗时；WS快照复制均值{S['display']['ws_queue_copy_ms']['mean']:.3f}ms。

“帧处理开始→本机解码完成”起点在空间检查之后，均值112.505ms、P95 135.870ms；“活动周期”起点在空间检查之前，两者边界不同。显示工作与主链路重叠，不能把42.056ms预览工作再加到51.040ms周期上。当前19.42fps下预览全覆盖，不代表42fps时仍全覆盖；latest-only策略允许显示跳帧，但检测记录必须完整。

## 5. 输入完整性、结果数量和慢帧

{split_table}

两种条件各4911张，失败均0，输出均为139,663个检测框。逐图SHA-256全部对应，逐图框数、逐类框数、舍入输出签名差异均0。应用有{P['empty_successful_frames']}张成功但无检测，触及max_det300的图片{P['max_det_reached_frames']}张。空检测不等于漏检，框数不是跨帧物体去重计数。

权重8类、真值7类且类别顺序不同；本轮未做类别映射、旋转IoU匹配、AP、召回率、执行成功率或模型数值容差验收。签名一致只用于排查测量链路是否改变输出。

以下为活动周期最长的15帧，全部保留在pipeline-frames.csv中。最大值用于定位，不能单凭一帧判定永久瓶颈。

{slow_table}

本轮有**22帧活动周期超过100ms**。在读字节、解码、前向、空间检查、数据库、快照、统计及发布这些已列区间中，19帧最大的区间是DB提交，2帧是读字节，1帧是空间检查。最长帧284.338ms中，读字节占233.100ms；另有259.283ms帧的空间检查占215.775ms。它们是下一轮补充IO/锁/commit追踪的定位线索，尚不能据此判定磁盘设备慢或SQL本身慢。

### 共同阶段为什么在应用中也变慢

{comparison_table}

应用解码比基线增加4.056ms，前向增加1.344ms；这说明完整应用的附加成本不限于新增的DB和快照区间，已有阶段的墙钟分布也发生变化。并行预览、WS序列化与主线程共享CPU/锁，可能参与竞争；但没有“相同服务关闭预览”的配对实验，不能证明全部差值由预览导致，也不能把这些差值再重复加到主链路均值。

有限目录模式每帧从增长的耗时列表计算分位数，连续inbox模式使用上限1000的deque，两种模式边界不同。从本轮各划分首尾20%窗口看，统计/复制并不一致地随帧号增长（train为1.682→1.641ms，val为0.668→1.213ms，test为0.981→0.936ms）。可列为源码层面的候选改进，尚无证据称其为本轮持续恶化的首要瓶颈；窗口数据保存在additional-analysis.json。

## 6. 资源与存储记录

{resource_table}

每2秒采样一次：基线{S['resources']['baseline']['samples']}点、应用{S['resources']['pipeline']['samples']}点。CPU100%表示一个逻辑CPU，177.6%约1.78个核；只监控推理/API进程，不含数据库、网关和独立观察器。GPU指标为整卡采样，最大值不是瞬时峰值；未达到100%不能独立证明GPU利用率可按比例放大。

应用轮次数据库体积增加约{db_delta/1024**2:.2f}MiB，文件系统空闲减少约{P['filesystem_free_delta']/1024**3:.3f}GiB。包含预热、数据库WAL、原图快照和测量日志，不能视为纯业务净增长。各阶段资源原始采样在raw-records.tar.gz，/proc读取中read_bytes增量为0，与已预热页缓存一致，不代表没有读图。

追踪record调用累计：基线396.508ms、应用3524.942ms；该累计横跨线程、含锁等待，线程间可重叠，**不能从墙钟直接扣除**。CUDA计时增加了一处NMS后同步，其扰动没有通过开/关追踪配对试验定量；报告数据属于带测量仪器的基线。

## 7. 后续优化优先级（本轮只分析）

|优先级|证据与建议实验|验收约束|
|---|---|---|
|P0 输入与预览图像处理|主链路解码13.245ms；预览重复解码12.032ms、INTER_AREA缩放23.768ms。优先对比缩放策略/实现；再评估有界预览任务复用已解码图像，减少重复读取与解码。|保持原图/结果绑定、坐标变换、JPEG尺寸与质量可解释；限制队列和内存。变更线程数需整链路复测，不能只测单次resize。|
|P0 应用同步区间|统计/DB/发布11.488ms，其中DB6.554ms；空间检查均值1.526ms、最大215.775ms。拆出JSON编码、锁等待、SQL、commit及文件系统检查慢点，检查是否每帧重复计算可缓存统计。|先保留当前提交后发布语义；数据库故障策略待用户确认，不能直接将数据库改成无保障异步写。不得通过删结果/关fsync伪造提速。|
|P1 GPU前向|前向13.513ms，GPU应用轮次平均24.85%；对比FP16或TensorRT的单帧延迟及整链路吞吐，检查主机等待。|同权重/输入/阈值做OBB结果与精度对照，TensorRT尚未适配，不预估确定倍数。大batch可能增加动作等待，不能只追求离线FPS。|
|P1 有界读取流水线|当前串行读图和GPU执行；在生产落盘约束下试验完成文件发布后有界预读、解码、队列排队时间。|处理部分写入、乱序、重复文件、重启恢复和背压；明确超时帧如何处置，不能静默丢执行帧。实时积压不能靠无限队列解决。|
|P2 展示传输|本机HTTP均值6.760ms、WS本机传播3.350ms，当前图像处理更大。后续在真实公网/局域网测图片体积、带宽、接收/解码/绘制。|HTTP用于不可变JPEG、WS用于元数据是当前实现；不能据此认定HTTP必须全部改WS，也不能用本机结果承诺公网延迟。|
|P2 持续运行与动作时限|测试有效运行仅约4.2分钟；尚无真实相机、编码器和执行反馈。补持续落盘、磁盘空间、WAL增长与长尾关联监测。|冻结相机像素格式、接口、存图格式、曝光完成时间；补拍摄到动作距离、编码器和实际动作延迟，建立逐帧截止时间。|

串行简化估算：如果其他均值完全不变，模型前向耗时理想降为0，周期仍需{mean-forward:.3f}ms，对应约{1000/(mean-forward):.2f}fps；仅将读图/哈希/解码理想降为0，仍约{1000/(mean-input_mean):.2f}fps。**这只是固定其余开销的上限算术，不是可实现的优化预测**；真正并行化会改变资源竞争与阶段时间。

42fps对应每帧23.810ms预算。本轮所有4911帧活动周期都超过这一参考值，离线应用能力19.418fps低于42fps：**只在同类1580×1080工作负载、持续输入42fps且长期处理能力固定19.418fps的假设下**，积压约增加22.582帧/秒，即每分钟约1355帧。19.418fps来自有限目录三次任务的场景吞吐，不是连续工业相机服务率的实测；持续inbox还使用不同统计窗口。这是排队算术示例，不是工业相机实测。生产相机4096×2168与本轮输入不同，不能直接外推具体现场FPS。带速0.45m/s下，51.040ms约对应2.30cm、112.505ms约5.06cm，只是恒速距离换算；没有拍摄到执行距离/编码器/动作延迟，无法给出合格动作截止时间。

## 8. 复现、文件与测量审计

先确认无活动任务、磁盘空间和数据库备份策略。脚本针对本台Linux部署，会核对PID和目录、停止8765主服务、启动带追踪实例；6006只读入口继续运行，最后恢复正常8765。不是通用生产压测工具，不能在有业务时直接运行。

```bash
conda activate factory_demo
cd /root/autodl-tmp/factory_demo
# 必须使用全新目录，避免追踪追加和原始记录混合
python -B scripts/benchmark_full4911.py --dataset /root/autodl-tmp/dataset/dataset4911_obb_622 --output /root/autodl-tmp/tmp/bench4911-NEW
python -B scripts/analyze_benchmark.py --input /root/autodl-tmp/tmp/bench4911-NEW --output /root/autodl-tmp/tmp/bench4911-NEW/analysis
```

`--phase pipeline`仅适用于已准备manifest、warm_images和配置的受控重测；不要把它当首次运行入口。本次复用完整基线CSV，补跑应用链路。

服务器断开后，在含NumPy/Pandas/Matplotlib/Markdown的本机Conda环境中，可不加载模型、不连接数据库地复算补充分析与生成网页：

```text
python -B docs/benchmarks/20261028-full4911/analyze_records.py
python -B docs/benchmarks/20261028-full4911/build_report.py
```

本报告生成在用户指定的yolo_v5_obb环境中，图表使用本机微软雅黑；其他机器重新生成时需提供可用中文字体或修改FONT路径。已经生成的HTML/SVG均已内嵌图形字形，离线阅读不需要Python或安装字体。

第一轮应用4911张均成功入库，但SIGTERM时Uvicorn重新发送信号，atexit没能保证追踪尾部落盘，丢失最后2帧周期。该轮保留在`/root/autodl-tmp/tmp/bench4911-20261028-01`，**没有用它计算最终分位数**。最终应用轮次在`/root/autodl-tmp/tmp/bench4911-20261028-02`；lifespan显式关闭追踪，原始文件有完整footer。观察器也改为独立接收、只取最新帧，避免其自身积压污染显示延迟。

基线与应用各自的实测源码哈希、源码副本分开留存。基础Git版本277d7f5；在其上增加测量点。测量完成后仅加固了复现脚本的异常恢复顺序、统计完整性断言与文档，不改变这次实测样本。测试记录probe-tests.log：服务器63通过、9个subtests，另有2条警告；本机59通过、4项CUDA跳过。逐图性能不是这些测试的耗时。

|交付文件|用途|
|---|---|
|[report.html](report.html)|独立离线网页版，内嵌SVG图，方便阅读|
|[summary.json](summary.json)|全量统计、环境、恢复状态、资源与口径|
|[pipeline-frames.csv](pipeline-frames.csv)|4911行应用逐帧计时、哈希核对与预览对应|
|[baseline-frames.csv](baseline-frames.csv)|4911行基线逐帧计时|
|[stage-statistics.csv](stage-statistics.csv)|所有阶段n、均值、P50/P90/P95/P99/最小/最大/累计|
|[manifest.jsonl](manifest.jsonl)|输入相对路径、尺寸、字节、哈希与划分|
|[raw-records.tar.gz](raw-records.tar.gz)|原始追踪/资源/本机观察器/实测源码快照；不含原图、权重、密码|
|[archive-integrity.json](archive-integrity.json)|压缩归档及权重的SHA-256和白名单|
|[attempt-audit.json](attempt-audit.json)|首次不完整记录与补跑原因|
|[restoration.json](restoration.json)|正常服务恢复证据|
|[additional-analysis.json](additional-analysis.json)|共同阶段对照、长尾定位、分段统计和排队算术假设|
|[offline-verification-20261029.json](offline-verification-20261029.json)|本地归档与源码哈希、4911帧对应及逐阶段统计复算结果|

测试结束时的留存证据显示：正式服务健康检查OK、active_run_id为空；云端配置恢复configs/cloud.json、cuda:0，FACTORY_TRACE_PATH和FACTORY_BENCHMARK_UNPACED均未设置，公开6006预览就绪。**2026-10-29服务器已断开，本次没有重新检查在线状态**。测试记录未执行自动清理；实例存储在断开/释放后的存续取决于平台与用户操作，不能据离线文件保证当前服务器仍保留原图或数据库。
'''
md=report.replace('{{MAIN_CHART}}','![主链路耗时图](main-chain.svg)').replace('{{PREVIEW_CHART}}','![并行预览耗时图](preview-chain.svg)')
(OUT/'REPORT.md').write_text(md,encoding='utf-8')
body=markdown.markdown(report.replace('{{MAIN_CHART}}','<div class="diagram-container">'+chart1+'</div>').replace('{{PREVIEW_CHART}}','<div class="diagram-container">'+chart2+'</div>'),extensions=['tables','fenced_code','toc'])
body=re.sub(r'<table>(.*?)</table>',r'<div class="table-scroll"><table>\1</table></div>',body,flags=re.S)
css="""*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f2f4f3;color:#203039;font:17px/1.9 'Segoe UI','Microsoft YaHei',sans-serif}main{max-width:1440px;margin:auto;padding:40px 48px 80px;min-width:0}h1{font-size:36px;line-height:1.45;border-bottom:3px solid #177b68;padding-bottom:24px}h2{font-size:26px;border-top:1px solid #c4d0cb;padding-top:32px;margin-top:44px}a{color:#126a59;text-underline-offset:3px}p,li{overflow-wrap:anywhere}li{margin:8px 0}pre{padding:20px;background:#edf5f1;overflow:auto;border:1px solid #c4d0cb}code{font-family:Consolas,'Microsoft YaHei',monospace;font-size:.87em}table{border-collapse:collapse;min-width:740px;font-size:14px;width:100%}td,th{border:1px solid #cbd7d1;padding:10px 13px;text-align:left;white-space:normal}th{background:#edf5f1}td{background:#fff}.table-scroll,.diagram-container{width:100%;overflow-x:auto;margin:24px 0;border:1px solid #c4d0cb}.diagram-container svg{display:block;width:100%;min-width:1280px;height:auto}nav{display:flex;gap:18px;flex-wrap:wrap;font-size:14px}footer{font-size:14px;color:#52676b;margin-top:40px}@media(max-width:600px){main{padding:20px 16px}h1{font-size:27px}h2{font-size:22px}body{font-size:16px}}@media print{main{padding:0}.table-scroll,.diagram-container{overflow:visible}table{min-width:0;font-size:10px}.diagram-container svg{min-width:0}h2{break-after:avoid}pre{white-space:pre-wrap}}"""
first_heading=re.search(r'<h2 id="([^"]+)"',body).group(1)
page=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Factory Demo 4911张性能实测报告</title><style>{css}</style></head><body><main><nav><a href="#{first_heading}">测试结果</a><a href="summary.json">结构化统计</a><a href="pipeline-frames.csv">逐帧CSV</a><a href="raw-records.tar.gz">原始证据</a></nav>{body}<footer>离线阅读 · Factory Demo · 2026-10-28实测 / 2026-10-29离线复核</footer></main></body></html>'
# Use the rendered HTML as the source of the SVG exports.
(OUT/'report.html').write_text(page,encoding='utf-8')
svgs=re.findall(r'<svg\b.*?</svg>',page,re.S)
assert len(svgs)==2
for name,svg in zip(['main-chain','preview-chain'],svgs):(OUT/(name+'.svg')).write_text(svg,encoding='utf-8')
print(json.dumps({'images':4911,'charts':2,'report_bytes':len(page.encode()),'output':str(OUT)},ensure_ascii=False))
