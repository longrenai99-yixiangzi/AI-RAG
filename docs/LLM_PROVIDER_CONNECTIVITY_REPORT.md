# LLM Provider Connectivity Report

> 任务：TASK-015.1 LLM Provider Connectivity Validation  
> 验证目录：D:\AI智能体\AI设计管理RAG-V1  
> 验证时间：2026-08-23  
> 边界：未修改正式 Retriever、8000 服务、正式 Qdrant 或 Answer Policy

## 1. 配置检查

| 项目 | 当前结果 |
|---|---|
| API Base URL | http://10.11.139.124:3000/v1 |
| Model Name | deepseek_v4_pro_public |
| API Key | 已读取，未输出明文 |
| API Key 来源 | app/config.py 先读当前进程环境，再读 Windows User 环境；本次 Windows User 环境变量存在 |
| API 配置完整性 | api_ready=True |
| HTTP 请求超时 | 总超时 60 秒，连接超时 15 秒 |
| 重试 | 失败最多重试 3 次，重试等待 1 秒、2 秒 |
| 显式 Proxy 配置 | 未发现 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY 当前进程配置 |
| Provider | OpenAI-compatible Shadow Provider，复用现有 LLMClient |

代码当前没有单独的 Proxy 参数；HTTP 客户端使用系统/环境代理默认行为。若内网访问必须经过代理，需要显式配置代理环境或后续在 Provider 中增加代理配置项。

## 2. 网络检查

执行 TCP 连接检查：

    目标：10.11.139.124:3000
    结果：失败

这说明当前运行环境无法建立到 API 服务地址和端口的 TCP 连接。

### 复测结果

随后再次复测时：

- TCP 连接：成功；
- 网卡：WLAN；
- GET /v1/models：HTTP 401；
- 服务返回：Invalid token。

因此网络路径目前已经恢复，当前失败点不是 TCP 不可达。

## 3. 单请求验证

### 输入

使用 100 题 Gold Dataset 中的真实设计管理问题，并附带一条 Shadow Qdrant Evidence：

    设计管理指南如何定义项目设计管理的主要职责？

### 结果

| 验证项 | 结果 |
|---|---|
| 请求是否成功 | 否 |
| Provider 返回内容 | 无 |
| JSON/结构解析 | 未执行，因为请求失败 |
| Claim Validator | 未执行，因为没有模型响应 |
| 错误类型 | LLMError |
| 错误摘要 | 生成模型请求失败；请检查内网连接、模型权限和服务状态 |

## 4. 失败原因判断

### 已确认事实

1. API Base URL、Model Name 和 API Key 均已配置；
2. api_ready=True；
3. 当前进程没有发现显式 HTTP/HTTPS Proxy；
4. TCP 到 10.11.139.124:3000 失败；
5. 单请求返回 LLMError。

### 最可能原因

复测已经确认网络和服务端口可达。当前最可能是 API Key 无效、过期、绑定了错误的服务/项目，或该 Key 没有访问当前 Model Name 的权限。

### 尚不能确认的原因

HTTP 401 已确认令牌认证失败，但仅凭当前响应还不能区分：

- API Key 已过期；
- API Key 复制错误；
- API Key 属于其他服务或项目；
- API Key 没有访问 deepseek_v4_pro_public 的权限。

服务端在认证通过后的 /v1/chat/completions 返回格式仍未验证。

## 5. 配置问题清单

当前需要外部环境确认：

1. 重新提供或刷新 API Key；
2. API Key 是否属于 10.11.139.124:3000 服务；
3. API Key 是否有访问 deepseek_v4_pro_public 的权限；
4. 服务端 /v1/chat/completions 在认证通过后是否正常；
5. deepseek_v4_pro_public 是否仍是有效模型名。

本次没有修改这些配置，避免在没有服务端证据时盲目替换地址或密钥。

## 6. 替代 Provider 方案

### 方案 A：恢复现有内网 Provider

优先恢复当前配置对应的服务：

    http://10.11.139.124:3000/v1/chat/completions

恢复后先验证：

1. TCP 3000 端口可达；
2. 使用同一 API Key 请求单个真实问题；
3. 返回 JSON 中存在 choices/message/content；
4. Claim Validator 通过后再运行 100 题。

### 方案 B：替换为其他 OpenAI-compatible Provider

只需通过环境变量替换：

    RAG_API_BASE_URL
    RAG_CHAT_MODEL
    RAG_API_KEY

Provider 需要兼容：

    POST /v1/chat/completions
    Authorization: Bearer <key>
    messages
    temperature
    max_tokens
    choices[0].message.content

可选服务类型包括企业内部网关、vLLM、Ollama OpenAI-compatible 接口或其他已批准的兼容服务。当前未安装、未切换和未验证这些替代服务。

### 方案 C：配置代理

如果服务只能通过代理访问，可在运行 Shadow 进程前配置：

    HTTP_PROXY
    HTTPS_PROXY
    NO_PROXY

代理地址、认证信息和允许访问范围必须由网络管理员提供，不能在项目代码中硬编码。

## 7. 当前结论

TASK-015.1 的配置读取检查和单请求验证已完成。网络已经恢复，但当前 LLM Provider 因 HTTP 401 Invalid token 不可用，真实答案生成尚未恢复。

在 Provider 恢复前：

- 不运行 100 题真实 LLM 生成；
- 不修改正式 Answer Engine；
- 继续保留 evidence-only 和 LLM_UNAVAILABLE 回退；
- 不把 Shadow 证据摘要当作模型生成结论。

**TASK-015.1：LLM Provider Connectivity Validation 完成；当前阻塞条件为 API Key 认证失败。**
