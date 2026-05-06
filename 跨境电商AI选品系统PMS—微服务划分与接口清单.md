# 跨境电商AI选品系统PMS—微服务划分与接口清单

> **版本**：v1.0
> **创建日期**：2026-04-23
> **项目代号**：Project Aegis
> **文档状态**：正式版

------

## 目录

1. **微服务划分总览**
2. **选品域 (Selection Domain)**
3. **Agent域 (Agent Domain)**
4. **知识域 (Knowledge Domain)**
5. **AI域 (AI Domain)**
6. **数据域 (Data Domain)**
7. **集成域 (Integration Domain)**
8. **报告域 (Report Domain)**
9. **用户域 (User Domain)**
10. **通知域 (Notification Domain)**
11. **接口统计汇总**

------

## 1. 微服务划分总览

### 1.1 领域划分原则





| 原则             | 说明                                                   |
| :--------------- | :----------------------------------------------------- |
| **业务边界清晰** | 按业务领域划分，每个领域有明确的职责边界               |
| **粒度适中**     | 避免过细（一个功能一个服务）或过粗（所有功能一个服务） |
| **数据自治**     | 每个服务拥有自己的数据库，通过API或事件通信            |
| **独立部署**     | 每个服务可独立开发、测试、部署、扩缩容                 |

### 1.2 微服务清单





| 序号 | 服务名称                   | 所属领域 | 职责                               | 端口 | 数据库              |
| :--- | :------------------------- | :------- | :--------------------------------- | :--- | :------------------ |
| 1    | **selection-service**      | 选品域   | 选品任务管理、推荐管理、采纳执行   | 8001 | PostgreSQL          |
| 2    | **agent-service**          | Agent域  | Agent编排、执行管理、人工干预      | 8002 | PostgreSQL          |
| 3    | **knowledge-service**      | 知识域   | 知识库管理、文档管理、知识版本     | 8003 | PostgreSQL          |
| 4    | **rag-service**            | 知识域   | RAG检索、混合检索、图谱检索        | 8004 | Qdrant + ES + Neo4j |
| 5    | **llm-service**            | AI域     | LLM路由、模型调用、成本控制        | 8005 | PostgreSQL          |
| 6    | **embedding-service**      | AI域     | 文本向量化、多模态向量化           | 8006 | Qdrant              |
| 7    | **data-ingestion-service** | 数据域   | 数据采集、CDC消费、数据分发        | 8007 | Kafka               |
| 8    | **feature-service**        | 数据域   | 特征查询、特征管理                 | 8008 | Feast + Redis       |
| 9    | **integration-service**    | 集成域   | ERP集成、外部API集成               | 8009 | PostgreSQL          |
| 10   | **crawler-service**        | 集成域   | 爬虫调度、数据采集                 | 8010 | PostgreSQL          |
| 11   | **report-service**         | 报告域   | 报告生成、报告导出、模板管理       | 8011 | PostgreSQL + MinIO  |
| 12   | **user-service**           | 用户域   | 用户管理、角色权限、租户管理、认证 | 8012 | PostgreSQL          |
| 13   | **notification-service**   | 通知域   | 消息通知、消息模板、通道管理       | 8013 | PostgreSQL          |
| 14   | **gateway-service**        | 网关     | API网关、认证、限流、路由          | 8000 | PostgreSQL (配置)   |

------

## 2. 选品域 (Selection Domain)

### 2.1 selection-service

**职责**：选品任务管理、推荐结果管理、采纳执行

**数据库**：PostgreSQL

**依赖服务**：agent-service, integration-service, user-service

### 2.2 接口清单





| 方法             | 路径                                                         | 说明               | 请求体                 | 响应                                        |
| :--------------- | :----------------------------------------------------------- | :----------------- | :--------------------- | :------------------------------------------ |
| **选品任务管理** |                                                              |                    |                        |                                             |
| POST             | `/api/v1/selections`                                         | 创建选品任务       | CreateSelectionRequest | SelectionTaskResponse                       |
| GET              | `/api/v1/selections`                                         | 查询任务列表       | QueryParams            | PaginatedResponse<SelectionTaskResponse>    |
| GET              | `/api/v1/selections/{taskId}`                                | 获取任务详情       | -                      | SelectionTaskDetailResponse                 |
| PUT              | `/api/v1/selections/{taskId}`                                | 更新任务           | UpdateSelectionRequest | SelectionTaskResponse                       |
| DELETE           | `/api/v1/selections/{taskId}`                                | 取消任务           | -                      | SuccessResponse                             |
| POST             | `/api/v1/selections/{taskId}/start`                          | 启动任务           | -                      | ExecutionResponse                           |
| POST             | `/api/v1/selections/{taskId}/pause`                          | 暂停任务           | -                      | SuccessResponse                             |
| POST             | `/api/v1/selections/{taskId}/resume`                         | 恢复任务           | -                      | SuccessResponse                             |
| GET              | `/api/v1/selections/{taskId}/status`                         | 获取任务状态       | -                      | TaskStatusResponse                          |
| GET              | `/api/v1/selections/{taskId}/progress`                       | 获取执行进度       | -                      | ProgressResponse                            |
| **推荐管理**     |                                                              |                    |                        |                                             |
| GET              | `/api/v1/selections/{taskId}/recommendations`                | 获取推荐列表       | QueryParams            | PaginatedResponse<RecommendationResponse>   |
| GET              | `/api/v1/selections/{taskId}/recommendations/{recId}`        | 获取推荐详情       | -                      | RecommendationDetailResponse                |
| POST             | `/api/v1/selections/{taskId}/recommendations/{recId}/adopt`  | 采纳推荐           | AdoptRequest           | AdoptResponse                               |
| POST             | `/api/v1/selections/{taskId}/recommendations/{recId}/reject` | 驳回推荐           | RejectRequest          | SuccessResponse                             |
| PUT              | `/api/v1/selections/{taskId}/recommendations/{recId}/adjust` | 调整推荐参数       | AdjustRequest          | RecommendationResponse                      |
| GET              | `/api/v1/selections/{taskId}/recommendations/compare`        | 对比推荐           | CompareRequest         | CompareResponse                             |
| **分析结果**     |                                                              |                    |                        |                                             |
| GET              | `/api/v1/selections/{taskId}/market-analysis`                | 获取市场分析结果   | -                      | MarketAnalysisResponse                      |
| GET              | `/api/v1/selections/{taskId}/product-plan`                   | 获取产品规划结果   | -                      | ProductPlanResponse                         |
| GET              | `/api/v1/selections/{taskId}/commercial-analysis`            | 获取商业化分析结果 | -                      | CommercialAnalysisResponse                  |
| GET              | `/api/v1/selections/{taskId}/risk-assessment`                | 获取风险评估结果   | -                      | RiskAssessmentResponse                      |
| **历史与统计**   |                                                              |                    |                        |                                             |
| GET              | `/api/v1/selections/history`                                 | 获取历史任务       | QueryParams            | PaginatedResponse<SelectionHistoryResponse> |
| GET              | `/api/v1/selections/statistics`                              | 获取选品统计       | QueryParams            | StatisticsResponse                          |
| GET              | `/api/v1/selections/{taskId}/timeline`                       | 获取任务时间线     | -                      | TimelineResponse                            |

------

## 3. Agent域 (Agent Domain)

### 3.1 agent-service

**职责**：Agent编排、执行管理、状态管理、人工干预

**数据库**：PostgreSQL

**依赖服务**：llm-service, rag-service, feature-service, knowledge-service

### 3.2 接口清单





| 方法              | 路径                                                         | 说明           | 请求体              | 响应                                 |
| :---------------- | :----------------------------------------------------------- | :------------- | :------------------ | :----------------------------------- |
| **Agent执行管理** |                                                              |                |                     |                                      |
| POST              | `/api/v1/agents/execute`                                     | 触发Agent执行  | ExecuteAgentRequest | ExecutionResponse                    |
| GET               | `/api/v1/agents/executions/{executionId}`                    | 获取执行详情   | -                   | ExecutionDetailResponse              |
| GET               | `/api/v1/agents/executions`                                  | 查询执行列表   | QueryParams         | PaginatedResponse<ExecutionResponse> |
| POST              | `/api/v1/agents/executions/{executionId}/pause`              | 暂停执行       | -                   | SuccessResponse                      |
| POST              | `/api/v1/agents/executions/{executionId}/resume`             | 恢复执行       | -                   | SuccessResponse                      |
| POST              | `/api/v1/agents/executions/{executionId}/cancel`             | 取消执行       | -                   | SuccessResponse                      |
| POST              | `/api/v1/agents/executions/{executionId}/retry`              | 重试执行       | -                   | ExecutionResponse                    |
| **Agent状态管理** |                                                              |                |                     |                                      |
| GET               | `/api/v1/agents/executions/{executionId}/state`              | 获取当前状态   | -                   | StateResponse                        |
| PUT               | `/api/v1/agents/executions/{executionId}/state`              | 更新状态       | UpdateStateRequest  | SuccessResponse                      |
| GET               | `/api/v1/agents/executions/{executionId}/checkpoints`        | 获取检查点列表 | -                   | List<CheckpointResponse>             |
| POST              | `/api/v1/agents/executions/{executionId}/checkpoints/{checkpointId}/restore` | 恢复到检查点   | -                   | SuccessResponse                      |
| **人工干预**      |                                                              |                |                     |                                      |
| POST              | `/api/v1/agents/executions/{executionId}/intervene`          | 人工干预       | InterveneRequest    | SuccessResponse                      |
| GET               | `/api/v1/agents/executions/{executionId}/interventions`      | 获取干预记录   | -                   | List<InterventionResponse>           |
| POST              | `/api/v1/agents/executions/{executionId}/approve`            | 审批通过       | ApproveRequest      | SuccessResponse                      |
| POST              | `/api/v1/agents/executions/{executionId}/reject`             | 审批驳回       | RejectRequest       | SuccessResponse                      |
| **Agent日志**     |                                                              |                |                     |                                      |
| GET               | `/api/v1/agents/executions/{executionId}/logs`               | 获取执行日志   | QueryParams         | PaginatedResponse<LogResponse>       |
| GET               | `/api/v1/agents/executions/{executionId}/logs/stream`        | 实时日志流     | -                   | WebSocket                            |
| **Agent监控**     |                                                              |                |                     |                                      |
| GET               | `/api/v1/agents/executions/{executionId}/metrics`            | 获取执行指标   | -                   | MetricsResponse                      |
| GET               | `/api/v1/agents/executions/{executionId}/cost`               | 获取成本统计   | -                   | CostResponse                         |
| GET               | `/api/v1/agents/statistics`                                  | 获取Agent统计  | QueryParams         | AgentStatisticsResponse              |
| **Agent管理**     |                                                              |                |                     |                                      |
| GET               | `/api/v1/agents`                                             | 获取Agent列表  | -                   | List<AgentInfoResponse>              |
| GET               | `/api/v1/agents/{agentName}`                                 | 获取Agent信息  | -                   | AgentInfoResponse                    |
| PUT               | `/api/v1/agents/{agentName}/config`                          | 更新Agent配置  | AgentConfigRequest  | SuccessResponse                      |
| POST              | `/api/v1/agents/{agentName}/test`                            | 测试Agent      | TestRequest         | TestResponse                         |

------

## 4. 知识域 (Knowledge Domain)

### 4.1 knowledge-service

**职责**：知识库管理、文档管理、知识版本管理

**数据库**：PostgreSQL

**依赖服务**：embedding-service, rag-service

### 4.2 接口清单





| 方法             | 路径                                                         | 说明                    | 请求体                | 响应                                       |
| :--------------- | :----------------------------------------------------------- | :---------------------- | :-------------------- | :----------------------------------------- |
| **文档管理**     |                                                              |                         |                       |                                            |
| POST             | `/api/v1/knowledge/documents`                                | 上传文档                | Multipart File        | DocumentResponse                           |
| GET              | `/api/v1/knowledge/documents`                                | 查询文档列表            | QueryParams           | PaginatedResponse<DocumentResponse>        |
| GET              | `/api/v1/knowledge/documents/{docId}`                        | 获取文档详情            | -                     | DocumentDetailResponse                     |
| PUT              | `/api/v1/knowledge/documents/{docId}`                        | 更新文档元数据          | UpdateDocumentRequest | DocumentResponse                           |
| DELETE           | `/api/v1/knowledge/documents/{docId}`                        | 删除文档                | -                     | SuccessResponse                            |
| POST             | `/api/v1/knowledge/documents/{docId}/process`                | 处理文档（分块/向量化） | -                     | ProcessResponse                            |
| GET              | `/api/v1/knowledge/documents/{docId}/chunks`                 | 获取文档分块            | -                     | List<ChunkResponse>                        |
| GET              | `/api/v1/knowledge/documents/{docId}/download`               | 下载文档                | -                     | FileStream                                 |
| **知识版本管理** |                                                              |                         |                       |                                            |
| GET              | `/api/v1/knowledge/documents/{docId}/versions`               | 获取版本列表            | -                     | List<VersionResponse>                      |
| POST             | `/api/v1/knowledge/documents/{docId}/versions/{versionId}/rollback` | 回滚到指定版本          | -                     | SuccessResponse                            |
| POST             | `/api/v1/knowledge/documents/{docId}/publish`                | 发布文档                | -                     | SuccessResponse                            |
| POST             | `/api/v1/knowledge/documents/{docId}/archive`                | 归档文档                | -                     | SuccessResponse                            |
| **知识分类管理** |                                                              |                         |                       |                                            |
| GET              | `/api/v1/knowledge/categories`                               | 获取分类列表            | -                     | List<CategoryResponse>                     |
| POST             | `/api/v1/knowledge/categories`                               | 创建分类                | CreateCategoryRequest | CategoryResponse                           |
| PUT              | `/api/v1/knowledge/categories/{categoryId}`                  | 更新分类                | UpdateCategoryRequest | CategoryResponse                           |
| DELETE           | `/api/v1/knowledge/categories/{categoryId}`                  | 删除分类                | -                     | SuccessResponse                            |
| **知识标签管理** |                                                              |                         |                       |                                            |
| GET              | `/api/v1/knowledge/tags`                                     | 获取标签列表            | -                     | List<TagResponse>                          |
| POST             | `/api/v1/knowledge/tags`                                     | 创建标签                | CreateTagRequest      | TagResponse                                |
| DELETE           | `/api/v1/knowledge/tags/{tagId}`                             | 删除标签                | -                     | SuccessResponse                            |
| **知识评测**     |                                                              |                         |                       |                                            |
| POST             | `/api/v1/knowledge/evaluate`                                 | 评测知识库质量          | EvaluateRequest       | EvaluateResponse                           |
| GET              | `/api/v1/knowledge/evaluate/history`                         | 获取评测历史            | QueryParams           | PaginatedResponse<EvaluateHistoryResponse> |
| **知识统计**     |                                                              |                         |                       |                                            |
| GET              | `/api/v1/knowledge/statistics`                               | 获取知识库统计          | -                     | KnowledgeStatisticsResponse                |

### 4.3 rag-service

**职责**：RAG检索、混合检索、图谱检索、精排

**数据库**：Qdrant + Elasticsearch + Neo4j

**依赖服务**：embedding-service

### 4.4 接口清单





| 方法           | 路径                                   | 说明                 | 请求体                 | 响应                     |
| :------------- | :------------------------------------- | :------------------- | :--------------------- | :----------------------- |
| **RAG检索**    |                                        |                      |                        |                          |
| POST           | `/api/v1/rag/retrieve`                 | 混合检索             | RetrieveRequest        | RetrieveResponse         |
| POST           | `/api/v1/rag/retrieve/vector`          | 纯向量检索           | VectorRetrieveRequest  | RetrieveResponse         |
| POST           | `/api/v1/rag/retrieve/keyword`         | 纯关键词检索         | KeywordRetrieveRequest | RetrieveResponse         |
| POST           | `/api/v1/rag/retrieve/hybrid`          | 混合检索（详细参数） | HybridRetrieveRequest  | RetrieveResponse         |
| POST           | `/api/v1/rag/query`                    | RAG问答              | QueryRequest           | QueryResponse            |
| POST           | `/api/v1/rag/query/stream`             | 流式RAG问答          | QueryRequest           | SSE Stream               |
| **图谱检索**   |                                        |                      |                        |                          |
| POST           | `/api/v1/rag/graph/query`              | 图谱查询             | GraphQueryRequest      | GraphQueryResponse       |
| POST           | `/api/v1/rag/graph/path`               | 路径查询             | PathQueryRequest       | PathResponse             |
| POST           | `/api/v1/rag/graph/neighbors`          | 邻居查询             | NeighborsRequest       | NeighborsResponse        |
| GET            | `/api/v1/rag/graph/entity/{entityId}`  | 获取实体详情         | -                      | EntityResponse           |
| **多模态检索** |                                        |                      |                        |                          |
| POST           | `/api/v1/rag/multimodal/image`         | 以图搜图             | ImageSearchRequest     | List<ImageResponse>      |
| POST           | `/api/v1/rag/multimodal/text-to-image` | 文本搜图             | TextToImageRequest     | List<ImageResponse>      |
| POST           | `/api/v1/rag/multimodal/video`         | 视频检索             | VideoSearchRequest     | List<VideoResponse>      |
| **缓存管理**   |                                        |                      |                        |                          |
| POST           | `/api/v1/rag/cache/clear`              | 清除检索缓存         | ClearCacheRequest      | SuccessResponse          |
| GET            | `/api/v1/rag/cache/stats`              | 获取缓存统计         | -                      | CacheStatsResponse       |
| **检索评测**   |                                        |                      |                        |                          |
| POST           | `/api/v1/rag/evaluate/accuracy`        | 评测检索准确率       | EvaluateRequest        | AccuracyResponse         |
| POST           | `/api/v1/rag/evaluate/recall`          | 评测召回率           | EvaluateRequest        | RecallResponse           |
| GET            | `/api/v1/rag/metrics`                  | 获取检索指标         | -                      | RetrievalMetricsResponse |

------

## 5. AI域 (AI Domain)

### 5.1 llm-service

**职责**：LLM路由、模型调用、成本控制、降级管理

**数据库**：PostgreSQL

**依赖服务**：vLLM, Triton, Ollama, OpenAI API

### 5.2 接口清单





| 方法         | 路径                                    | 说明           | 请求体               | 响应                       |
| :----------- | :-------------------------------------- | :------------- | :------------------- | :------------------------- |
| **LLM调用**  |                                         |                |                      |                            |
| POST         | `/api/v1/llm/generate`                  | 生成文本       | GenerateRequest      | GenerateResponse           |
| POST         | `/api/v1/llm/generate/stream`           | 流式生成       | GenerateRequest      | SSE Stream                 |
| POST         | `/api/v1/llm/chat`                      | 对话生成       | ChatRequest          | ChatResponse               |
| POST         | `/api/v1/llm/chat/stream`               | 流式对话       | ChatRequest          | SSE Stream                 |
| POST         | `/api/v1/llm/batch`                     | 批量生成       | BatchGenerateRequest | BatchGenerateResponse      |
| **模型管理** |                                         |                |                      |                            |
| GET          | `/api/v1/llm/models`                    | 获取模型列表   | -                    | List<ModelResponse>        |
| GET          | `/api/v1/llm/models/{modelName}`        | 获取模型详情   | -                    | ModelDetailResponse        |
| PUT          | `/api/v1/llm/models/{modelName}/config` | 更新模型配置   | ModelConfigRequest   | SuccessResponse            |
| POST         | `/api/v1/llm/models/{modelName}/test`   | 测试模型       | TestModelRequest     | TestModelResponse          |
| **路由管理** |                                         |                |                      |                            |
| GET          | `/api/v1/llm/routes`                    | 获取路由规则   | -                    | List<RouteRuleResponse>    |
| POST         | `/api/v1/llm/routes`                    | 创建路由规则   | CreateRouteRequest   | RouteRuleResponse          |
| PUT          | `/api/v1/llm/routes/{ruleId}`           | 更新路由规则   | UpdateRouteRequest   | RouteRuleResponse          |
| DELETE       | `/api/v1/llm/routes/{ruleId}`           | 删除路由规则   | -                    | SuccessResponse            |
| **成本管理** |                                         |                |                      |                            |
| GET          | `/api/v1/llm/cost/usage`                | 获取用量统计   | QueryParams          | UsageResponse              |
| GET          | `/api/v1/llm/cost/quota`                | 获取配额信息   | -                    | QuotaResponse              |
| PUT          | `/api/v1/llm/cost/quota`                | 设置配额       | SetQuotaRequest      | SuccessResponse            |
| GET          | `/api/v1/llm/cost/billing`              | 获取账单       | QueryParams          | BillingResponse            |
| **降级管理** |                                         |                |                      |                            |
| GET          | `/api/v1/llm/circuit-breaker`           | 获取熔断器状态 | -                    | CircuitBreakerResponse     |
| POST         | `/api/v1/llm/circuit-breaker/reset`     | 重置熔断器     | ResetRequest         | SuccessResponse            |
| PUT          | `/api/v1/llm/circuit-breaker/config`    | 更新熔断配置   | CircuitBreakerConfig | SuccessResponse            |
| **安全护栏** |                                         |                |                      |                            |
| POST         | `/api/v1/llm/security/check`            | 检查Prompt安全 | SecurityCheckRequest | SecurityCheckResponse      |
| POST         | `/api/v1/llm/security/filter`           | 过滤输出内容   | FilterRequest        | FilterResponse             |
| GET          | `/api/v1/llm/security/rules`            | 获取安全规则   | -                    | List<SecurityRuleResponse> |

### 5.3 embedding-service

**职责**：文本向量化、多模态向量化、批量处理

**数据库**：Qdrant

**依赖服务**：BGE, CLIP

### 5.4 接口清单





| 方法             | 路径                                          | 说明             | 请求体                  | 响应                     |
| :--------------- | :-------------------------------------------- | :--------------- | :---------------------- | :----------------------- |
| **文本向量化**   |                                               |                  |                         |                          |
| POST             | `/api/v1/embedding/text`                      | 文本向量化       | TextEmbedRequest        | EmbedResponse            |
| POST             | `/api/v1/embedding/text/batch`                | 批量文本向量化   | BatchTextEmbedRequest   | BatchEmbedResponse       |
| POST             | `/api/v1/embedding/text/similarity`           | 计算文本相似度   | SimilarityRequest       | SimilarityResponse       |
| **多模态向量化** |                                               |                  |                         |                          |
| POST             | `/api/v1/embedding/image`                     | 图片向量化       | ImageEmbedRequest       | EmbedResponse            |
| POST             | `/api/v1/embedding/image/batch`               | 批量图片向量化   | BatchImageEmbedRequest  | BatchEmbedResponse       |
| POST             | `/api/v1/embedding/image/similarity`          | 计算图片相似度   | ImageSimilarityRequest  | SimilarityResponse       |
| POST             | `/api/v1/embedding/video`                     | 视频向量化       | VideoEmbedRequest       | EmbedResponse            |
| POST             | `/api/v1/embedding/audio`                     | 音频向量化       | AudioEmbedRequest       | EmbedResponse            |
| **向量管理**     |                                               |                  |                         |                          |
| POST             | `/api/v1/embedding/vectors`                   | 存储向量         | StoreVectorRequest      | StoreVectorResponse      |
| POST             | `/api/v1/embedding/vectors/batch`             | 批量存储向量     | BatchStoreVectorRequest | BatchStoreResponse       |
| DELETE           | `/api/v1/embedding/vectors/{vectorId}`        | 删除向量         | -                       | SuccessResponse          |
| GET              | `/api/v1/embedding/vectors/{vectorId}`        | 获取向量         | -                       | VectorResponse           |
| **模型管理**     |                                               |                  |                         |                          |
| GET              | `/api/v1/embedding/models`                    | 获取向量模型列表 | -                       | List<EmbedModelResponse> |
| PUT              | `/api/v1/embedding/models/{modelName}/config` | 更新模型配置     | ModelConfigRequest      | SuccessResponse          |
| **性能指标**     |                                               |                  |                         |                          |
| GET              | `/api/v1/embedding/metrics`                   | 获取向量化指标   | -                       | EmbedMetricsResponse     |

------

## 6. 数据域 (Data Domain)

### 6.1 data-ingestion-service

**职责**：数据采集、CDC消费、数据分发

**数据库**：Kafka

**依赖服务**：外部API, CDC

### 6.2 接口清单





| 方法             | 路径                                                    | 说明              | 请求体                 | 响应                                        |
| :--------------- | :------------------------------------------------------ | :---------------- | :--------------------- | :------------------------------------------ |
| **数据源管理**   |                                                         |                   |                        |                                             |
| GET              | `/api/v1/ingestion/sources`                             | 获取数据源列表    | -                      | List<DataSourceResponse>                    |
| POST             | `/api/v1/ingestion/sources`                             | 创建数据源        | CreateSourceRequest    | DataSourceResponse                          |
| PUT              | `/api/v1/ingestion/sources/{sourceId}`                  | 更新数据源        | UpdateSourceRequest    | DataSourceResponse                          |
| DELETE           | `/api/v1/ingestion/sources/{sourceId}`                  | 删除数据源        | -                      | SuccessResponse                             |
| POST             | `/api/v1/ingestion/sources/{sourceId}/test`             | 测试数据源连接    | -                      | TestConnectionResponse                      |
| **采集任务管理** |                                                         |                   |                        |                                             |
| GET              | `/api/v1/ingestion/tasks`                               | 获取采集任务列表  | QueryParams            | PaginatedResponse<IngestionTaskResponse>    |
| POST             | `/api/v1/ingestion/tasks`                               | 创建采集任务      | CreateTaskRequest      | IngestionTaskResponse                       |
| PUT              | `/api/v1/ingestion/tasks/{taskId}`                      | 更新采集任务      | UpdateTaskRequest      | IngestionTaskResponse                       |
| DELETE           | `/api/v1/ingestion/tasks/{taskId}`                      | 删除采集任务      | -                      | SuccessResponse                             |
| POST             | `/api/v1/ingestion/tasks/{taskId}/run`                  | 手动触发采集      | -                      | RunTaskResponse                             |
| POST             | `/api/v1/ingestion/tasks/{taskId}/stop`                 | 停止采集任务      | -                      | SuccessResponse                             |
| GET              | `/api/v1/ingestion/tasks/{taskId}/status`               | 获取任务状态      | -                      | TaskStatusResponse                          |
| GET              | `/api/v1/ingestion/tasks/{taskId}/history`              | 获取执行历史      | QueryParams            | PaginatedResponse<ExecutionHistoryResponse> |
| **CDC管理**      |                                                         |                   |                        |                                             |
| GET              | `/api/v1/ingestion/cdc/connectors`                      | 获取CDC连接器列表 | -                      | List<ConnectorResponse>                     |
| POST             | `/api/v1/ingestion/cdc/connectors`                      | 创建CDC连接器     | CreateConnectorRequest | ConnectorResponse                           |
| DELETE           | `/api/v1/ingestion/cdc/connectors/{connectorId}`        | 删除CDC连接器     | -                      | SuccessResponse                             |
| POST             | `/api/v1/ingestion/cdc/connectors/{connectorId}/pause`  | 暂停CDC           | -                      | SuccessResponse                             |
| POST             | `/api/v1/ingestion/cdc/connectors/{connectorId}/resume` | 恢复CDC           | -                      | SuccessResponse                             |
| GET              | `/api/v1/ingestion/cdc/connectors/{connectorId}/status` | 获取CDC状态       | -                      | ConnectorStatusResponse                     |
| **数据质量**     |                                                         |                   |                        |                                             |
| POST             | `/api/v1/ingestion/quality/check`                       | 执行质量检查      | QualityCheckRequest    | QualityCheckResponse                        |
| GET              | `/api/v1/ingestion/quality/rules`                       | 获取质量规则      | -                      | List<QualityRuleResponse>                   |
| POST             | `/api/v1/ingestion/quality/rules`                       | 创建质量规则      | CreateRuleRequest      | QualityRuleResponse                         |
| GET              | `/api/v1/ingestion/quality/reports`                     | 获取质量报告      | QueryParams            | PaginatedResponse<QualityReportResponse>    |
| **数据统计**     |                                                         |                   |                        |                                             |
| GET              | `/api/v1/ingestion/statistics`                          | 获取采集统计      | QueryParams            | IngestionStatisticsResponse                 |
| GET              | `/api/v1/ingestion/metrics`                             | 获取采集指标      | -                      | IngestionMetricsResponse                    |

### 6.3 feature-service

**职责**：特征查询、特征管理

**数据库**：Feast + Redis

**依赖服务**：data-ingestion-service

### 6.4 接口清单





| 方法             | 路径                                              | 说明             | 请求体                   | 响应                               |
| :--------------- | :------------------------------------------------ | :--------------- | :----------------------- | :--------------------------------- |
| **特征查询**     |                                                   |                  |                          |                                    |
| POST             | `/api/v1/features/query`                          | 批量查询特征     | FeatureQueryRequest      | FeatureQueryResponse               |
| GET              | `/api/v1/features/entity/{entityType}/{entityId}` | 查询实体特征     | -                        | EntityFeaturesResponse             |
| POST             | `/api/v1/features/online`                         | 获取在线特征     | OnlineFeatureRequest     | OnlineFeatureResponse              |
| POST             | `/api/v1/features/offline`                        | 获取离线特征     | OfflineFeatureRequest    | OfflineFeatureResponse             |
| **特征管理**     |                                                   |                  |                          |                                    |
| GET              | `/api/v1/features`                                | 获取特征列表     | QueryParams              | PaginatedResponse<FeatureResponse> |
| GET              | `/api/v1/features/{featureName}`                  | 获取特征详情     | -                        | FeatureDetailResponse              |
| POST             | `/api/v1/features`                                | 注册特征         | RegisterFeatureRequest   | FeatureResponse                    |
| PUT              | `/api/v1/features/{featureName}`                  | 更新特征         | UpdateFeatureRequest     | FeatureResponse                    |
| DELETE           | `/api/v1/features/{featureName}`                  | 删除特征         | -                        | SuccessResponse                    |
| **特征视图管理** |                                                   |                  |                          |                                    |
| GET              | `/api/v1/features/views`                          | 获取特征视图列表 | -                        | List<FeatureViewResponse>          |
| POST             | `/api/v1/features/views`                          | 创建特征视图     | CreateFeatureViewRequest | FeatureViewResponse                |
| PUT              | `/api/v1/features/views/{viewName}`               | 更新特征视图     | UpdateFeatureViewRequest | FeatureViewResponse                |
| **特征统计**     |                                                   |                  |                          |                                    |
| GET              | `/api/v1/features/{featureName}/statistics`       | 获取特征统计     | -                        | FeatureStatisticsResponse          |
| GET              | `/api/v1/features/{featureName}/distribution`     | 获取特征分布     | -                        | DistributionResponse               |
| **特征血缘**     |                                                   |                  |                          |                                    |
| GET              | `/api/v1/features/{featureName}/lineage`          | 获取特征血缘     | -                        | LineageResponse                    |
| GET              | `/api/v1/features/entity/{entityId}/lineage`      | 获取实体特征血缘 | -                        | EntityLineageResponse              |

------

## 7. 集成域 (Integration Domain)

### 7.1 integration-service

**职责**：ERP集成、外部API集成

**数据库**：PostgreSQL

**依赖服务**：OMS, WMS, SCM, CRM, FMS, BI

### 7.2 接口清单





| 方法             | 路径                                                       | 说明               | 请求体                 | 响应                                |
| :--------------- | :--------------------------------------------------------- | :----------------- | :--------------------- | :---------------------------------- |
| **ERP集成**      |                                                            |                    |                        |                                     |
| POST             | `/api/v1/integration/erp/oms/orders`                       | 同步OMS订单        | SyncOrdersRequest      | SyncResponse                        |
| GET              | `/api/v1/integration/erp/oms/orders/{orderId}`             | 获取订单详情       | -                      | OrderResponse                       |
| POST             | `/api/v1/integration/erp/oms/listings`                     | 创建Listing草稿    | CreateListingRequest   | ListingResponse                     |
| GET              | `/api/v1/integration/erp/wms/inventory/{asin}`             | 获取库存信息       | -                      | InventoryResponse                   |
| POST             | `/api/v1/integration/erp/wms/capacity/reserve`             | 预留库容           | ReserveCapacityRequest | CapacityResponse                    |
| GET              | `/api/v1/integration/erp/scm/suppliers`                    | 获取供应商列表     | QueryParams            | PaginatedResponse<SupplierResponse> |
| GET              | `/api/v1/integration/erp/scm/suppliers/{supplierId}`       | 获取供应商详情     | -                      | SupplierDetailResponse              |
| POST             | `/api/v1/integration/erp/scm/purchase-orders`              | 创建采购单         | CreatePORequest        | PurchaseOrderResponse               |
| GET              | `/api/v1/integration/erp/crm/reviews/{asin}`               | 获取评价列表       | QueryParams            | PaginatedResponse<ReviewResponse>   |
| GET              | `/api/v1/integration/erp/fms/costs/{asin}`                 | 获取成本数据       | -                      | CostResponse                        |
| GET              | `/api/v1/integration/erp/fms/profit/{asin}`                | 获取利润数据       | QueryParams            | ProfitResponse                      |
| GET              | `/api/v1/integration/erp/bi/kpi/{metric}`                  | 获取KPI数据        | QueryParams            | KPIResponse                         |
| **外部API集成**  |                                                            |                    |                        |                                     |
| POST             | `/api/v1/integration/external/amazon/search`               | 搜索Amazon商品     | AmazonSearchRequest    | AmazonSearchResponse                |
| GET              | `/api/v1/integration/external/amazon/products/{asin}`      | 获取Amazon商品详情 | -                      | AmazonProductResponse               |
| GET              | `/api/v1/integration/external/amazon/reviews/{asin}`       | 获取Amazon评价     | QueryParams            | AmazonReviewsResponse               |
| POST             | `/api/v1/integration/external/tiktok/search`               | 搜索TikTok视频     | TikTokSearchRequest    | TikTokSearchResponse                |
| GET              | `/api/v1/integration/external/tiktok/trends`               | 获取TikTok趋势     | QueryParams            | TikTokTrendsResponse                |
| POST             | `/api/v1/integration/external/google/trends`               | 获取Google Trends  | TrendsRequest          | TrendsResponse                      |
| POST             | `/api/v1/integration/external/1688/search`                 | 搜索1688商品       | Ali1688SearchRequest   | Ali1688SearchResponse               |
| GET              | `/api/v1/integration/external/1688/suppliers/{supplierId}` | 获取1688供应商     | -                      | Ali1688SupplierResponse             |
| GET              | `/api/v1/integration/external/gdelt/events`                | 获取GDELT事件      | QueryParams            | GDELTEventsResponse                 |
| **集成配置管理** |                                                            |                    |                        |                                     |
| GET              | `/api/v1/integration/configs`                              | 获取集成配置列表   | -                      | List<IntegrationConfigResponse>     |
| POST             | `/api/v1/integration/configs`                              | 创建集成配置       | CreateConfigRequest    | IntegrationConfigResponse           |
| PUT              | `/api/v1/integration/configs/{configId}`                   | 更新集成配置       | UpdateConfigRequest    | IntegrationConfigResponse           |
| DELETE           | `/api/v1/integration/configs/{configId}`                   | 删除集成配置       | -                      | SuccessResponse                     |
| POST             | `/api/v1/integration/configs/{configId}/test`              | 测试集成连接       | -                      | TestConnectionResponse              |
| **同步管理**     |                                                            |                    |                        |                                     |
| GET              | `/api/v1/integration/sync/tasks`                           | 获取同步任务列表   | QueryParams            | PaginatedResponse<SyncTaskResponse> |
| POST             | `/api/v1/integration/sync/tasks`                           | 创建同步任务       | CreateSyncTaskRequest  | SyncTaskResponse                    |
| POST             | `/api/v1/integration/sync/tasks/{taskId}/run`              | 执行同步任务       | -                      | RunSyncResponse                     |
| GET              | `/api/v1/integration/sync/tasks/{taskId}/status`           | 获取同步状态       | -                      | SyncStatusResponse                  |

### 7.3 crawler-service

**职责**：爬虫调度、数据采集

**数据库**：PostgreSQL

**依赖服务**：Scrapy, Playwright, 代理池

### 7.4 接口清单





| 方法             | 路径                                             | 说明             | 请求体                | 响应                                   |
| :--------------- | :----------------------------------------------- | :--------------- | :-------------------- | :------------------------------------- |
| **爬虫管理**     |                                                  |                  |                       |                                        |
| GET              | `/api/v1/crawler/spiders`                        | 获取爬虫列表     | -                     | List<SpiderResponse>                   |
| GET              | `/api/v1/crawler/spiders/{spiderName}`           | 获取爬虫详情     | -                     | SpiderDetailResponse                   |
| PUT              | `/api/v1/crawler/spiders/{spiderName}/config`    | 更新爬虫配置     | SpiderConfigRequest   | SuccessResponse                        |
| **爬取任务管理** |                                                  |                  |                       |                                        |
| GET              | `/api/v1/crawler/jobs`                           | 获取爬取任务列表 | QueryParams           | PaginatedResponse<CrawlJobResponse>    |
| POST             | `/api/v1/crawler/jobs`                           | 创建爬取任务     | CreateCrawlJobRequest | CrawlJobResponse                       |
| GET              | `/api/v1/crawler/jobs/{jobId}`                   | 获取任务详情     | -                     | CrawlJobDetailResponse                 |
| DELETE           | `/api/v1/crawler/jobs/{jobId}`                   | 取消爬取任务     | -                     | SuccessResponse                        |
| POST             | `/api/v1/crawler/jobs/{jobId}/run`               | 手动触发爬取     | -                     | RunJobResponse                         |
| POST             | `/api/v1/crawler/jobs/{jobId}/stop`              | 停止爬取         | -                     | SuccessResponse                        |
| GET              | `/api/v1/crawler/jobs/{jobId}/results`           | 获取爬取结果     | QueryParams           | PaginatedResponse<CrawlResultResponse> |
| **调度管理**     |                                                  |                  |                       |                                        |
| GET              | `/api/v1/crawler/schedules`                      | 获取调度列表     | -                     | List<ScheduleResponse>                 |
| POST             | `/api/v1/crawler/schedules`                      | 创建调度         | CreateScheduleRequest | ScheduleResponse                       |
| PUT              | `/api/v1/crawler/schedules/{scheduleId}`         | 更新调度         | UpdateScheduleRequest | ScheduleResponse                       |
| DELETE           | `/api/v1/crawler/schedules/{scheduleId}`         | 删除调度         | -                     | SuccessResponse                        |
| POST             | `/api/v1/crawler/schedules/{scheduleId}/enable`  | 启用调度         | -                     | SuccessResponse                        |
| POST             | `/api/v1/crawler/schedules/{scheduleId}/disable` | 禁用调度         | -                     | SuccessResponse                        |
| **代理池管理**   |                                                  |                  |                       |                                        |
| GET              | `/api/v1/crawler/proxy/pool`                     | 获取代理池状态   | -                     | ProxyPoolResponse                      |
| POST             | `/api/v1/crawler/proxy/add`                      | 添加代理         | AddProxyRequest       | SuccessResponse                        |
| DELETE           | `/api/v1/crawler/proxy/{proxyId}`                | 移除代理         | -                     | SuccessResponse                        |
| POST             | `/api/v1/crawler/proxy/refresh`                  | 刷新代理池       | -                     | SuccessResponse                        |
| **爬虫监控**     |                                                  |                  |                       |                                        |
| GET              | `/api/v1/crawler/metrics`                        | 获取爬虫指标     | -                     | CrawlerMetricsResponse                 |
| GET              | `/api/v1/crawler/statistics`                     | 获取爬取统计     | QueryParams           | CrawlerStatisticsResponse              |

------

## 8. 报告域 (Report Domain)

### 8.1 report-service

**职责**：报告生成、报告导出、模板管理

**数据库**：PostgreSQL + MinIO

**依赖服务**：selection-service, agent-service

### 8.2 接口清单





| 方法         | 路径                                             | 说明             | 请求体                | 响应                              |
| :----------- | :----------------------------------------------- | :--------------- | :-------------------- | :-------------------------------- |
| **报告生成** |                                                  |                  |                       |                                   |
| POST         | `/api/v1/reports/generate`                       | 生成报告         | GenerateReportRequest | ReportResponse                    |
| GET          | `/api/v1/reports/{reportId}`                     | 获取报告详情     | -                     | ReportDetailResponse              |
| GET          | `/api/v1/reports/{reportId}/status`              | 获取生成状态     | -                     | ReportStatusResponse              |
| DELETE       | `/api/v1/reports/{reportId}`                     | 删除报告         | -                     | SuccessResponse                   |
| GET          | `/api/v1/reports`                                | 查询报告列表     | QueryParams           | PaginatedResponse<ReportResponse> |
| **报告导出** |                                                  |                  |                       |                                   |
| GET          | `/api/v1/reports/{reportId}/download`            | 下载报告         | QueryParams(format)   | FileStream                        |
| POST         | `/api/v1/reports/{reportId}/export/pdf`          | 导出PDF          | ExportRequest         | ExportResponse                    |
| POST         | `/api/v1/reports/{reportId}/export/excel`        | 导出Excel        | ExportRequest         | ExportResponse                    |
| POST         | `/api/v1/reports/{reportId}/export/ppt`          | 导出PPT          | ExportRequest         | ExportResponse                    |
| **报告分享** |                                                  |                  |                       |                                   |
| POST         | `/api/v1/reports/{reportId}/share`               | 分享报告         | ShareRequest          | ShareResponse                     |
| GET          | `/api/v1/reports/shared/{shareToken}`            | 访问分享报告     | -                     | SharedReportResponse              |
| DELETE       | `/api/v1/reports/{reportId}/share/{shareId}`     | 取消分享         | -                     | SuccessResponse                   |
| **报告对比** |                                                  |                  |                       |                                   |
| POST         | `/api/v1/reports/compare`                        | 对比报告         | CompareReportsRequest | CompareResponse                   |
| GET          | `/api/v1/reports/{reportId}/diff/{compareId}`    | 获取差异详情     | -                     | DiffResponse                      |
| **模板管理** |                                                  |                  |                       |                                   |
| GET          | `/api/v1/reports/templates`                      | 获取模板列表     | -                     | List<TemplateResponse>            |
| POST         | `/api/v1/reports/templates`                      | 创建模板         | CreateTemplateRequest | TemplateResponse                  |
| GET          | `/api/v1/reports/templates/{templateId}`         | 获取模板详情     | -                     | TemplateDetailResponse            |
| PUT          | `/api/v1/reports/templates/{templateId}`         | 更新模板         | UpdateTemplateRequest | TemplateResponse                  |
| DELETE       | `/api/v1/reports/templates/{templateId}`         | 删除模板         | -                     | SuccessResponse                   |
| POST         | `/api/v1/reports/templates/{templateId}/preview` | 预览模板         | PreviewRequest        | PreviewResponse                   |
| **定时报告** |                                                  |                  |                       |                                   |
| GET          | `/api/v1/reports/schedules`                      | 获取定时报告列表 | -                     | List<ReportScheduleResponse>      |
| POST         | `/api/v1/reports/schedules`                      | 创建定时报告     | CreateScheduleRequest | ReportScheduleResponse            |
| PUT          | `/api/v1/reports/schedules/{scheduleId}`         | 更新定时报告     | UpdateScheduleRequest | ReportScheduleResponse            |
| DELETE       | `/api/v1/reports/schedules/{scheduleId}`         | 删除定时报告     | -                     | SuccessResponse                   |
| **报告统计** |                                                  |                  |                       |                                   |
| GET          | `/api/v1/reports/statistics`                     | 获取报告统计     | QueryParams           | ReportStatisticsResponse          |

------

## 9. 用户域 (User Domain)

### 9.1 user-service

**职责**：用户管理、角色权限、租户管理、认证授权

**数据库**：PostgreSQL

**依赖服务**：无

### 9.2 接口清单





| 方法           | 路径                                                | 说明          | 请求体                  | 响应                                |
| :------------- | :-------------------------------------------------- | :------------ | :---------------------- | :---------------------------------- |
| **认证**       |                                                     |               |                         |                                     |
| POST           | `/api/v1/auth/login`                                | 用户登录      | LoginRequest            | LoginResponse                       |
| POST           | `/api/v1/auth/logout`                               | 用户登出      | -                       | SuccessResponse                     |
| POST           | `/api/v1/auth/refresh`                              | 刷新Token     | RefreshRequest          | TokenResponse                       |
| POST           | `/api/v1/auth/register`                             | 用户注册      | RegisterRequest         | RegisterResponse                    |
| POST           | `/api/v1/auth/verify`                               | 验证Token     | VerifyRequest           | VerifyResponse                      |
| POST           | `/api/v1/auth/password/reset`                       | 重置密码请求  | ResetPasswordRequest    | SuccessResponse                     |
| POST           | `/api/v1/auth/password/confirm`                     | 确认重置密码  | ConfirmResetRequest     | SuccessResponse                     |
| **OAuth2/SSO** |                                                     |               |                         |                                     |
| GET            | `/api/v1/auth/oauth/{provider}`                     | OAuth登录跳转 | -                       | Redirect                            |
| GET            | `/api/v1/auth/oauth/{provider}/callback`            | OAuth回调     | QueryParams             | LoginResponse                       |
| POST           | `/api/v1/auth/sso/login`                            | SSO登录       | SSOLoginRequest         | LoginResponse                       |
| **用户管理**   |                                                     |               |                         |                                     |
| GET            | `/api/v1/users`                                     | 获取用户列表  | QueryParams             | PaginatedResponse<UserResponse>     |
| POST           | `/api/v1/users`                                     | 创建用户      | CreateUserRequest       | UserResponse                        |
| GET            | `/api/v1/users/{userId}`                            | 获取用户详情  | -                       | UserDetailResponse                  |
| PUT            | `/api/v1/users/{userId}`                            | 更新用户      | UpdateUserRequest       | UserResponse                        |
| DELETE         | `/api/v1/users/{userId}`                            | 删除用户      | -                       | SuccessResponse                     |
| POST           | `/api/v1/users/{userId}/enable`                     | 启用用户      | -                       | SuccessResponse                     |
| POST           | `/api/v1/users/{userId}/disable`                    | 禁用用户      | -                       | SuccessResponse                     |
| PUT            | `/api/v1/users/{userId}/password`                   | 修改密码      | ChangePasswordRequest   | SuccessResponse                     |
| GET            | `/api/v1/users/me`                                  | 获取当前用户  | -                       | UserDetailResponse                  |
| PUT            | `/api/v1/users/me`                                  | 更新当前用户  | UpdateProfileRequest    | UserResponse                        |
| **角色管理**   |                                                     |               |                         |                                     |
| GET            | `/api/v1/roles`                                     | 获取角色列表  | -                       | List<RoleResponse>                  |
| POST           | `/api/v1/roles`                                     | 创建角色      | CreateRoleRequest       | RoleResponse                        |
| GET            | `/api/v1/roles/{roleId}`                            | 获取角色详情  | -                       | RoleDetailResponse                  |
| PUT            | `/api/v1/roles/{roleId}`                            | 更新角色      | UpdateRoleRequest       | RoleResponse                        |
| DELETE         | `/api/v1/roles/{roleId}`                            | 删除角色      | -                       | SuccessResponse                     |
| POST           | `/api/v1/users/{userId}/roles/{roleId}`             | 分配角色      | -                       | SuccessResponse                     |
| DELETE         | `/api/v1/users/{userId}/roles/{roleId}`             | 移除角色      | -                       | SuccessResponse                     |
| **权限管理**   |                                                     |               |                         |                                     |
| GET            | `/api/v1/permissions`                               | 获取权限列表  | -                       | List<PermissionResponse>            |
| POST           | `/api/v1/permissions`                               | 创建权限      | CreatePermissionRequest | PermissionResponse                  |
| DELETE         | `/api/v1/permissions/{permissionId}`                | 删除权限      | -                       | SuccessResponse                     |
| POST           | `/api/v1/roles/{roleId}/permissions/{permissionId}` | 授予权限      | -                       | SuccessResponse                     |
| DELETE         | `/api/v1/roles/{roleId}/permissions/{permissionId}` | 撤销权限      | -                       | SuccessResponse                     |
| **租户管理**   |                                                     |               |                         |                                     |
| GET            | `/api/v1/tenants`                                   | 获取租户列表  | QueryParams             | PaginatedResponse<TenantResponse>   |
| POST           | `/api/v1/tenants`                                   | 创建租户      | CreateTenantRequest     | TenantResponse                      |
| GET            | `/api/v1/tenants/{tenantId}`                        | 获取租户详情  | -                       | TenantDetailResponse                |
| PUT            | `/api/v1/tenants/{tenantId}`                        | 更新租户      | UpdateTenantRequest     | TenantResponse                      |
| DELETE         | `/api/v1/tenants/{tenantId}`                        | 删除租户      | -                       | SuccessResponse                     |
| POST           | `/api/v1/tenants/{tenantId}/enable`                 | 启用租户      | -                       | SuccessResponse                     |
| POST           | `/api/v1/tenants/{tenantId}/disable`                | 禁用租户      | -                       | SuccessResponse                     |
| GET            | `/api/v1/tenants/{tenantId}/quota`                  | 获取租户配额  | -                       | QuotaResponse                       |
| PUT            | `/api/v1/tenants/{tenantId}/quota`                  | 设置租户配额  | SetQuotaRequest         | SuccessResponse                     |
| **审计日志**   |                                                     |               |                         |                                     |
| GET            | `/api/v1/audit/logs`                                | 获取审计日志  | QueryParams             | PaginatedResponse<AuditLogResponse> |
| GET            | `/api/v1/audit/logs/{logId}`                        | 获取日志详情  | -                       | AuditLogDetailResponse              |
| POST           | `/api/v1/audit/logs/export`                         | 导出审计日志  | ExportRequest           | ExportResponse                      |

------

## 10. 通知域 (Notification Domain)

### 10.1 notification-service

**职责**：消息通知、消息模板、通道管理

**数据库**：PostgreSQL

**依赖服务**：钉钉, 企业微信, 邮件, 短信

### 10.2 接口清单





| 方法         | 路径                                                         | 说明         | 请求体                    | 响应                                    |
| :----------- | :----------------------------------------------------------- | :----------- | :------------------------ | :-------------------------------------- |
| **消息发送** |                                                              |              |                           |                                         |
| POST         | `/api/v1/notifications/send`                                 | 发送通知     | SendNotificationRequest   | SendResponse                            |
| POST         | `/api/v1/notifications/batch`                                | 批量发送通知 | BatchSendRequest          | BatchSendResponse                       |
| GET          | `/api/v1/notifications/{notificationId}`                     | 获取通知详情 | -                         | NotificationResponse                    |
| GET          | `/api/v1/notifications/{notificationId}/status`              | 获取发送状态 | -                         | SendStatusResponse                      |
| **消息模板** |                                                              |              |                           |                                         |
| GET          | `/api/v1/notifications/templates`                            | 获取模板列表 | QueryParams               | PaginatedResponse<TemplateResponse>     |
| POST         | `/api/v1/notifications/templates`                            | 创建模板     | CreateTemplateRequest     | TemplateResponse                        |
| GET          | `/api/v1/notifications/templates/{templateId}`               | 获取模板详情 | -                         | TemplateDetailResponse                  |
| PUT          | `/api/v1/notifications/templates/{templateId}`               | 更新模板     | UpdateTemplateRequest     | TemplateResponse                        |
| DELETE       | `/api/v1/notifications/templates/{templateId}`               | 删除模板     | -                         | SuccessResponse                         |
| POST         | `/api/v1/notifications/templates/{templateId}/preview`       | 预览模板     | PreviewRequest            | PreviewResponse                         |
| **通道管理** |                                                              |              |                           |                                         |
| GET          | `/api/v1/notifications/channels`                             | 获取通道列表 | -                         | List<ChannelResponse>                   |
| POST         | `/api/v1/notifications/channels`                             | 创建通道     | CreateChannelRequest      | ChannelResponse                         |
| GET          | `/api/v1/notifications/channels/{channelId}`                 | 获取通道详情 | -                         | ChannelDetailResponse                   |
| PUT          | `/api/v1/notifications/channels/{channelId}`                 | 更新通道     | UpdateChannelRequest      | ChannelResponse                         |
| DELETE       | `/api/v1/notifications/channels/{channelId}`                 | 删除通道     | -                         | SuccessResponse                         |
| POST         | `/api/v1/notifications/channels/{channelId}/test`            | 测试通道     | TestChannelRequest        | TestResponse                            |
| POST         | `/api/v1/notifications/channels/{channelId}/enable`          | 启用通道     | -                         | SuccessResponse                         |
| POST         | `/api/v1/notifications/channels/{channelId}/disable`         | 禁用通道     | -                         | SuccessResponse                         |
| **订阅管理** |                                                              |              |                           |                                         |
| GET          | `/api/v1/notifications/subscriptions`                        | 获取订阅列表 | QueryParams               | PaginatedResponse<SubscriptionResponse> |
| POST         | `/api/v1/notifications/subscriptions`                        | 创建订阅     | CreateSubscriptionRequest | SubscriptionResponse                    |
| DELETE       | `/api/v1/notifications/subscriptions/{subscriptionId}`       | 取消订阅     | -                         | SuccessResponse                         |
| PUT          | `/api/v1/notifications/subscriptions/{subscriptionId}/enable` | 启用订阅     | -                         | SuccessResponse                         |
| PUT          | `/api/v1/notifications/subscriptions/{subscriptionId}/disable` | 禁用订阅     | -                         | SuccessResponse                         |
| **消息历史** |                                                              |              |                           |                                         |
| GET          | `/api/v1/notifications/history`                              | 获取发送历史 | QueryParams               | PaginatedResponse<HistoryResponse>      |
| GET          | `/api/v1/notifications/history/{messageId}`                  | 获取消息详情 | -                         | MessageDetailResponse                   |
| POST         | `/api/v1/notifications/history/{messageId}/resend`           | 重新发送     | -                         | SendResponse                            |
| **通知统计** |                                                              |              |                           |                                         |
| GET          | `/api/v1/notifications/statistics`                           | 获取通知统计 | QueryParams               | NotificationStatisticsResponse          |
| GET          | `/api/v1/notifications/metrics`                              | 获取通知指标 | -                         | NotificationMetricsResponse             |

------

## 11. 接口统计汇总

### 11.1 按服务统计





| 服务名称               | 接口数量 | 所属领域 |
| :--------------------- | :------- | :------- |
| selection-service      | 23       | 选品域   |
| agent-service          | 26       | Agent域  |
| knowledge-service      | 22       | 知识域   |
| rag-service            | 19       | 知识域   |
| llm-service            | 22       | AI域     |
| embedding-service      | 19       | AI域     |
| data-ingestion-service | 28       | 数据域   |
| feature-service        | 18       | 数据域   |
| integration-service    | 32       | 集成域   |
| crawler-service        | 24       | 集成域   |
| report-service         | 26       | 报告域   |
| user-service           | 42       | 用户域   |
| notification-service   | 26       | 通知域   |
| **总计**               | **327**  | -        |

### 11.2 按HTTP方法统计





| 方法     | 数量    | 占比     |
| :------- | :------ | :------- |
| GET      | 140     | 42.8%    |
| POST     | 135     | 41.3%    |
| PUT      | 30      | 9.2%     |
| DELETE   | 22      | 6.7%     |
| **总计** | **327** | **100%** |

### 11.3 按领域统计





| 领域     | 服务数 | 接口数  | 占比     |
| :------- | :----- | :------ | :------- |
| 选品域   | 1      | 23      | 7.0%     |
| Agent域  | 1      | 26      | 8.0%     |
| 知识域   | 2      | 41      | 12.5%    |
| AI域     | 2      | 41      | 12.5%    |
| 数据域   | 2      | 46      | 14.1%    |
| 集成域   | 2      | 56      | 17.1%    |
| 报告域   | 1      | 26      | 8.0%     |
| 用户域   | 1      | 42      | 12.8%    |
| 通知域   | 1      | 26      | 8.0%     |
| **总计** | **13** | **327** | **100%** |

------

**文档版本**: v1.0
**创建日期**: 2026-04-23
**项目代号**: Project Aegis
**文档状态**: 正式版