# PicGate API 接口文档

本文档描述 PicGate 对客户端开放的主要 HTTP 接口。默认服务地址示例为：

```text
http://127.0.0.1:5643
```

如果在管理后台配置了“公共基础 URL”，图片结果中的 URL 会使用该配置值。

## 认证

除图片访问接口外，`/v1/*` 网关接口使用 OpenAI 风格的 Bearer Token：

```http
Authorization: Bearer <gateway_api_key>
```

如果管理后台未配置网关 API 密钥，则网关接口允许无认证访问。生产环境建议始终配置密钥。

## 状态码

| 状态码 | 说明 |
| --- | --- |
| `200` | 请求成功 |
| `202` | 异步任务已创建 |
| `400` | 请求参数错误 |
| `401` | 认证失败 |
| `404` | 资源不存在 |
| `502` | 上游 API 调用失败 |
| `503` | 上游配置缺失或服务不可用 |

错误响应格式：

```json
{
  "error": {
    "message": "错误说明",
    "type": "error_type"
  }
}
```

## 获取模型列表

```http
GET /v1/models
```

返回管理后台配置的网关模型名。

响应示例：

```json
{
  "object": "list",
  "data": [
    {
      "id": "picgate",
      "object": "model",
      "created": 1779158252,
      "owned_by": "picgate"
    }
  ]
}
```

## 文生图（同步）

```http
POST /v1/images/generations
```

同步模式会保持客户端连接，直到上游绘图完成并返回图片 URL。

请求体示例：

```json
{
  "model": "picgate",
  "prompt": "画银河中穿梭的橘子，电影感，高清。",
  "size": "1024x1024",
  "n": 1
}
```

常用字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `prompt` | string | 是 | 图片生成提示词 |
| `model` | string | 否 | 客户端传入的模型名 |
| `n` | integer | 否 | 图片数量，默认 `1` |
| `size` | string | 否 | 图片尺寸，默认 `1024x1024` |
| `quality` | string | 否 | 透传给支持该字段的上游模型 |
| `style` | string | 否 | 仅对支持该字段的上游模型透传 |

响应示例：

```json
{
  "created": 1779158335,
  "data": [
    {
      "url": "http://127.0.0.1:5643/images/0e27d94a-3f91-4f71-8f11-5ad54d84e2b7",
      "revised_prompt": null
    }
  ]
}
```

## 文生图（异步）

```http
POST /v1/images/generations?async=true
```

异步模式会立即返回任务号，PicGate 在后台继续请求上游并保存图片。客户端无需保持提交请求连接，后续通过任务接口轮询结果。

请求体与同步文生图相同。

提交响应示例：

```json
{
  "id": "task_9ac9cb14452745948f81b8880b8f1d4c",
  "object": "picgate.task",
  "type": "images.generations",
  "status": "queued",
  "created": 1779158252,
  "started_at": null,
  "finished_at": null,
  "result": null,
  "error": null,
  "poll_url": "http://127.0.0.1:5643/v1/tasks/task_9ac9cb14452745948f81b8880b8f1d4c"
}
```

PowerShell 示例：

```powershell
$headers = @{
  Authorization = "Bearer <gateway_api_key>"
  "Content-Type" = "application/json"
}

$body = @{
  model  = "picgate"
  prompt = "画银河中穿梭的橘子，电影感，高清。"
  size   = "1024x1024"
  n      = 1
} | ConvertTo-Json -Compress

$task = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5643/v1/images/generations?async=true" `
  -Method Post `
  -Headers $headers `
  -Body $body

$task.id
```

## 轮询异步任务

```http
GET /v1/tasks/{task_id}
```

任务状态：

| 状态 | 说明 |
| --- | --- |
| `queued` | 任务已创建，等待后台执行 |
| `running` | 正在调用上游或处理结果 |
| `succeeded` | 任务成功，`result` 中包含最终结果 |
| `failed` | 任务失败，`error` 中包含错误信息 |

处理中响应示例：

```json
{
  "id": "task_9ac9cb14452745948f81b8880b8f1d4c",
  "object": "picgate.task",
  "type": "images.generations",
  "status": "running",
  "created": 1779158252,
  "started_at": 1779158252,
  "finished_at": null,
  "result": null,
  "error": null
}
```

成功响应示例：

```json
{
  "id": "task_9ac9cb14452745948f81b8880b8f1d4c",
  "object": "picgate.task",
  "type": "images.generations",
  "status": "succeeded",
  "created": 1779158252,
  "started_at": 1779158252,
  "finished_at": 1779158336,
  "result": {
    "created": 1779158335,
    "data": [
      {
        "url": "http://127.0.0.1:5643/images/0e27d94a-3f91-4f71-8f11-5ad54d84e2b7",
        "revised_prompt": null
      }
    ]
  },
  "error": null
}
```

失败响应示例：

```json
{
  "id": "task_9ac9cb14452745948f81b8880b8f1d4c",
  "object": "picgate.task",
  "type": "images.generations",
  "status": "failed",
  "created": 1779158252,
  "started_at": 1779158252,
  "finished_at": 1779158260,
  "result": null,
  "error": {
    "message": "Failed to connect to upstream API",
    "type": "connection_error",
    "status_code": 502
  }
}
```

PowerShell 轮询示例：

```powershell
do {
  Start-Sleep -Seconds 3

  $status = Invoke-RestMethod `
    -Uri "http://127.0.0.1:5643/v1/tasks/$($task.id)" `
    -Method Get `
    -Headers $headers

  Write-Host "Status: $($status.status)"
} while ($status.status -eq "queued" -or $status.status -eq "running")

if ($status.status -eq "succeeded") {
  $status.result.data[0].url
} else {
  $status.error | ConvertTo-Json -Depth 10
}
```

## 图片编辑

```http
POST /v1/images/edits
```

用于对已有图片进行编辑或图生图。默认同步执行；如果需要异步任务，使用 `?async=true`。

请求体示例：

```json
{
  "image": "http://127.0.0.1:5643/images/0e27d94a-3f91-4f71-8f11-5ad54d84e2b7",
  "prompt": "把橘子改成发光的水晶橘子",
  "size": "1024x1024",
  "n": 1
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `image` | string | 是 | 图片 URL、data URL 或 base64 |
| `prompt` | string | 是 | 编辑提示词 |
| `mask` | string | 否 | 遮罩图片 URL、data URL 或 base64 |
| `n` | integer | 否 | 图片数量，默认 `1` |
| `size` | string | 否 | 图片尺寸，默认 `1024x1024` |

响应格式与文生图同步接口一致。

## 图片编辑（异步）

```http
POST /v1/images/edits?async=true
```

请求体与同步图片编辑相同。提交后立即返回任务号，后续通过 `/v1/tasks/{task_id}` 轮询结果。

PowerShell 示例：

```powershell
$body = @{
  model  = "picgate"
  image  = $imageUrl
  prompt = "把这张图中的水母换成西瓜，保持主体不变，电影感，高清。"
  size   = "1024x768"
  n      = 1
} | ConvertTo-Json -Depth 10 -Compress

$task = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5643/v1/images/edits?async=true" `
  -Method Post `
  -Headers $headers `
  -Body $body

$taskId = $task.id

do {
  Start-Sleep -Seconds 3

  $status = Invoke-RestMethod `
    -Uri "http://127.0.0.1:5643/v1/tasks/$taskId" `
    -Method Get `
    -Headers $headers

  Write-Host "Status: $($status.status)"
} while ($status.status -eq "queued" -or $status.status -eq "running")

if ($status.status -eq "succeeded") {
  $status.result.data[0].url
} else {
  $status.error | ConvertTo-Json -Depth 10
}
```

## 对话补全

```http
POST /v1/chat/completions
```

用于 OpenAI 兼容的多轮对话，支持图片 URL 转 base64 后转发给上游。支持普通非流式和 `stream=true` 流式请求。

请求体示例：

```json
{
  "model": "picgate",
  "messages": [
    {
      "role": "user",
      "content": "请画一只赛博朋克风格的猫"
    }
  ],
  "stream": false
}
```

带图片的请求示例：

```json
{
  "model": "picgate",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "基于这张图做二次创作"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "http://127.0.0.1:5643/images/0e27d94a-3f91-4f71-8f11-5ad54d84e2b7"
          }
        }
      ]
    }
  ],
  "stream": false
}
```

## 访问图片

```http
GET /images/{image_id}
```

返回已保存图片的二进制内容。该接口不要求 Bearer Token，方便 OpenWebUI 或浏览器直接加载图片。

示例：

```text
http://127.0.0.1:5643/images/0e27d94a-3f91-4f71-8f11-5ad54d84e2b7
```

## 访问缩略图

```http
GET /images/{image_id}/thumbnail
```

返回图片缩略图。如果缩略图不存在但本地原图存在，会尝试即时生成。若无法生成，则返回占位图。

## 注意事项

- `/v1/images/generations?async=true` 和 `/v1/images/edits?async=true` 支持异步任务，`/v1/chat/completions` 仍保持同步或流式行为。
- 异步任务状态保存在 SQLite 的 `async_tasks` 表中。
- 后台任务使用当前 PicGate 进程执行。服务重启会中断未完成任务，启动时会把这些任务标记为 `failed`。
- 多实例部署时，建议后续接入 Redis、Celery、RQ 或其他任务队列，避免任务只存在于单个进程中。
