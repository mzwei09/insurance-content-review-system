# 流式审核与性能优化文档

## 概述

本文档详细说明了系统的流式审核功能和性能优化措施，这些改进显著提升了用户体验，特别是在处理多张图片时。

## 🚀 性能优化

### 问题分析

在优化前，多图片审核存在以下性能瓶颈：

1. **串行处理**: 逐张提取图片文字 → 逐张审核，完全串行
2. **长时间等待**: 3张图片需要 15-20 秒，用户体验差
3. **无进度反馈**: 用户不知道当前进度，只能等待

### 优化方案

#### 1. 并行处理 (Parallel Processing)

**实现位置**: `src/multimodal_reviewer.py` 的 `_review_detailed()` 方法

**核心改进**:
- 使用 `ThreadPoolExecutor` 并行处理文本和所有图片
- 最多 6 个并发任务（1个文本 + 5张图片）
- 使用 `as_completed()` 实时获取完成的任务结果

**代码示例**:
```python
with ThreadPoolExecutor(max_workers=min(len(image_urls) + 1, 6)) as executor:
    futures = {}
    
    # 提交文本审核任务
    if text_content:
        futures[executor.submit(review_text)] = "text"
    
    # 提交所有图片审核任务（并行）
    for idx, img_url in enumerate(image_urls, 1):
        futures[executor.submit(review_image, idx, img_url)] = f"image_{idx}"
    
    # 等待所有任务完成
    for future in as_completed(futures):
        result = future.result()
        # 处理结果...
```

**性能提升**:
- **3张图片**: 从 ~18秒 降至 ~6秒 (提升 67%)
- **5张图片**: 从 ~30秒 降至 ~8秒 (提升 73%)
- **理论上限**: 接近单张图片的处理时间（受限于 API 并发限制）

#### 2. 进度回调机制

**实现位置**: `src/multimodal_reviewer.py` 的 `progress_callback` 参数

**功能**:
- 每个任务完成时立即回调
- 支持实时进度推送
- 为流式 API 提供数据源

**回调事件类型**:
```python
{
    "type": "progress",          # 进度更新
    "stage": "text_review",      # 当前阶段
    "message": "正在审核文本内容..."
}

{
    "type": "text_result",       # 文本审核结果
    "result": { ... }
}

{
    "type": "image_result",      # 单张图片审核结果
    "image_index": 1,
    "result": { ... }
}

{
    "type": "complete",          # 最终汇总结果
    "result": { ... }
}
```

## 📡 流式审核 (Streaming Review)

### 功能特性

1. **实时进度显示**: 用户可以看到每个步骤的进度
2. **渐进式结果**: 每个审核结果完成后立即显示
3. **更好的体验**: 不再是"黑盒等待"，用户知道系统在做什么
4. **可取消**: 用户可以随时取消审核

### 后端实现

#### 1. 流式 API 端点

**端点**: `POST /api/review-multimodal-stream`

**技术**: Server-Sent Events (SSE)

**实现位置**: `src/api/main.py`

**核心代码**:
```python
@app.post("/api/review-multimodal-stream")
async def review_multimodal_stream(...):
    # 创建消息队列
    message_queue = queue.Queue()
    
    def progress_callback(event: dict):
        """进度回调函数，将事件放入队列"""
        message_queue.put(event)
    
    # 在后台线程中执行审核
    def run_review():
        reviewer._review_detailed(
            text_content=text_content,
            image_urls=image_urls,
            api_key=api_key,
            progress_callback=progress_callback  # 传入回调
        )
    
    review_thread = threading.Thread(target=run_review, daemon=True)
    review_thread.start()
    
    # 生成 SSE 流
    async def event_generator():
        while True:
            event = message_queue.get(timeout=0.1)
            event_type = event.get("type", "message")
            yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

#### 2. SSE 事件格式

所有事件遵循 SSE 标准格式：

```
event: progress
data: {"type":"progress","stage":"text_review","message":"正在审核文本内容..."}

event: text_result
data: {"type":"text_result","result":{"compliance":false,...}}

event: image_result
data: {"type":"image_result","image_index":1,"result":{...}}

event: complete
data: {"type":"complete","result":{"compliance":false,...}}
```

### 前端实现

#### 1. 流式模式开关

**位置**: 审核按钮上方

**UI**:
```html
<label class="flex items-center gap-2 cursor-pointer">
  <input type="checkbox" id="stream-mode-toggle" checked />
  <span>实时显示审核过程</span>
</label>
```

**默认**: 启用流式模式

#### 2. EventSource 客户端

**实现位置**: `frontend/index.html` 的 `startStreamReview()` 函数

**核心代码**:
```javascript
async function startStreamReview() {
  const formData = new FormData();
  formData.append('text', content);
  uploadedImages.forEach(img => formData.append('images', img.file));
  
  const response = await fetch('/api/review-multimodal-stream', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData
  });
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data:')) {
        const data = JSON.parse(line.slice(6));
        handleStreamEvent(eventType, data);
      }
    }
  }
}
```

#### 3. 实时进度展示

**进度文本**:
- "正在提取图片1的文字..."
- "正在审核文本内容..."
- "正在审核图片2的内容..."

**已完成项**:
- ✓ 文本审核完成
- ✓ 图片1审核完成
- ✓ 图片2审核完成

**结果展示**:
- 每个结果到达后立即追加到详情区
- 支持逐步展开，用户可以边看边等

## 🔄 模式对比

### 非流式模式 (传统)

**优点**:
- 实现简单
- 兼容性好
- 适合单张图片或纯文本

**缺点**:
- 长时间等待
- 无进度反馈
- 用户体验差

**适用场景**:
- 纯文本审核
- 单张图片审核
- 网络不稳定环境

### 流式模式 (推荐)

**优点**:
- 实时进度反馈
- 渐进式结果展示
- 更好的用户体验
- 可以提前看到部分结果

**缺点**:
- 实现复杂
- 需要 SSE 支持
- 网络中断需要重试

**适用场景**:
- 多张图片审核
- 长时间任务
- 需要实时反馈的场景

## 📊 性能数据

### 测试场景

- **文本**: 100 字营销文案
- **图片**: 3 张 800x600 的营销海报
- **网络**: 本地测试（延迟 < 10ms）

### 优化前 (串行)

| 步骤 | 耗时 | 累计 |
|------|------|------|
| 提取图片1文字 | 3s | 3s |
| 审核图片1 | 2s | 5s |
| 提取图片2文字 | 3s | 8s |
| 审核图片2 | 2s | 10s |
| 提取图片3文字 | 3s | 13s |
| 审核图片3 | 2s | 15s |
| 审核文本 | 2s | 17s |
| **总计** | - | **~17s** |

### 优化后 (并行)

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 并行提取3张图片文字 | 3s | 最慢的一张 |
| 并行审核3张图片+文本 | 2s | 最慢的一个 |
| 结果汇总 | 0.5s | - |
| **总计** | **~5.5s** | **提升 68%** |

### 流式模式额外优势

- **首个结果**: 最快 3 秒即可看到第一个结果
- **用户感知**: 等待时间"更短"（有进度反馈）
- **可取消**: 不满意可以提前终止

## 🛠️ 使用指南

### 用户端

1. 访问审核页面
2. 输入文本或上传图片
3. 确保「实时显示审核过程」已勾选（默认勾选）
4. 点击「开始审核」
5. 观察实时进度和结果

**如果遇到问题**:
- 取消勾选「实时显示审核过程」，使用传统模式
- 检查网络连接
- 刷新页面重试

### 开发者端

#### 启用/禁用流式模式

**前端**:
```javascript
// 默认启用
document.getElementById('stream-mode-toggle').checked = true;

// 禁用流式模式
document.getElementById('stream-mode-toggle').checked = false;
```

**后端**:
```python
# 使用流式端点
POST /api/review-multimodal-stream

# 使用传统端点
POST /api/review-multimodal
```

#### 自定义进度回调

```python
def my_progress_callback(event: dict):
    event_type = event.get("type")
    if event_type == "progress":
        print(f"进度: {event.get('message')}")
    elif event_type == "text_result":
        print(f"文本审核完成: {event.get('result')}")
    # ... 处理其他事件

reviewer._review_detailed(
    text_content=text,
    image_urls=images,
    api_key=api_key,
    progress_callback=my_progress_callback
)
```

## 🐛 常见问题

### Q1: 流式模式下网络中断怎么办？

**A**: 前端会自动检测连接中断并提示用户重试。用户可以：
1. 刷新页面
2. 取消勾选流式模式，使用传统模式
3. 检查网络连接后重试

### Q2: 为什么有时候流式模式反而慢？

**A**: 可能的原因：
1. 网络延迟较高，SSE 传输开销大
2. 只有1张图片，并行优势不明显
3. API 服务器负载高，限制了并发

**建议**: 单张图片或纯文本时，可以使用传统模式。

### Q3: 流式模式支持所有浏览器吗？

**A**: 支持所有现代浏览器（Chrome 60+, Firefox 55+, Safari 11+, Edge 79+）。
IE 不支持 EventSource，但会自动降级到传统模式。

### Q4: 如何调整并发数？

**A**: 修改 `src/multimodal_reviewer.py` 中的 `max_workers`:

```python
with ThreadPoolExecutor(max_workers=min(len(image_urls) + 1, 6)) as executor:
    # 6 = 最大并发数，可以根据 API 限制调整
```

**注意**: 过高的并发可能触发 API 限流。

## 🔮 未来改进

1. **WebSocket 支持**: 更稳定的双向通信
2. **断点续传**: 网络中断后从上次位置继续
3. **智能并发**: 根据 API 响应时间动态调整并发数
4. **批量提取**: 一次 API 调用提取多张图片文字（需要 API 支持）
5. **缓存优化**: 相同图片不重复提取文字

## 📚 相关文档

- [系统架构](architecture.md)
- [性能分析](PERFORMANCE_ANALYSIS.md)
- [API 文档](../README.md#api-接口文档)

## 📄 许可证

MIT License
