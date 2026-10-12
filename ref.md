# “今天吃什么”产品与实现参考

> 本文以当前仓库为实现基线，记录产品边界、现有接口和待补能力。它不是从零搭建项目的目录模板。架构和接口以代码及 FastAPI OpenAPI 为准；未实现的产品目标明确标为“待实现”。

## 2. 产品范围与事实边界

### 2.1 核心流程

产品是移动端的线下美食发现、决策与导航 Web 应用：

```text
用户确认出发位置
→ 设置预算、步行上限、菜系、场景或自然语言偏好
→ 查询附近真实餐饮 POI 与步行路线
→ 筛选并返回 0–3 个餐厅候选
→ 调整条件或确认敏感变更
→ 选择地点、查看路线并打开高德导航
→ 保存选择与历史
```

推荐对象是餐厅/美食地点 POI，不是菜单菜品。首版不包含外卖、下单、支付、评论社区、精确营养管理或医疗/过敏安全判断。默认中文、人民币、`Asia/Shanghai` 展示和步行导航；用户应主动确认位置，不做长期后台位置跟踪。

### 2.2 数据来源

- 高德 JavaScript API：浏览器地图、选点、Marker 和路线可视化。
- 高德 Web 服务 API：逆地理编码、输入提示、餐饮 POI、地点详情和步行路线。
- OpenAI-compatible LLM：受限偏好解析、合法候选重排与推荐理由。
- PostgreSQL：业务记录、Task 状态和有效期内的高德响应缓存。

高德是唯一真实地图和餐饮 POI 来源，不引入其他餐饮平台 Adapter。不得虚构餐厅、坐标、评分、人均、营业状态、菜单、库存、排队人数、座位、评价原文或路线。字段缺失时保留未知状态并向用户提示。推荐理由中的事实必须能从高德字段或确定性计算结果验证。地图、POI 和路线的生产路径使用真实服务；单元测试可以使用 fake 来隔离纯逻辑，真实联调仍需有效 Key 和独立 PostgreSQL。

### 2.3 实施优先级

| 优先级 | 内容 | 当前状态 |
|---|---|---|
| 核心 | 高德双端配置、真实 POI/步行路线、受控工作流、Task Worker、SSE、调整、选择与历史 | 代码路径已存在；真实服务联调结果需单独验证 |
| 上线前 | 多用户身份与资源隔离、并发容量与部署策略、后端回归测试、独立数据库恢复测试 | 待实现或待验证 |
| 增强 | PWA、评测摘要、Tracing、生产 Docker、自动生成前端 OpenAPI 类型 | 待实现 |
| 可选 | 收藏/去过/不想再去、多人偏好合并、骑行/驾车、跨设备同步 | 待实现 |

## 3. 当前技术栈与目录

前端：React 19、TypeScript、Vite、React Router、TanStack Query、Zustand、React Hook Form、Zod、Tailwind CSS、Radix UI、Lucide、高德 JS API。测试工具配置包含 Vitest、Testing Library、Playwright。

后端：Python 3.12、FastAPI、Pydantic v2、SQLAlchemy Async、asyncpg、PostgreSQL、HTTPX、LangGraph、LangChain 和 OpenAI-compatible LLM。工具配置包含 Ruff、mypy、pytest。版本以 `src/frontend/pnpm-lock.yaml` 和 `src/backend/uv.lock` 为准。

```text
src/
├── frontend/
│   ├── src/
│   │   ├── components/       # 地图、地点卡、偏好表单与 UI
│   │   ├── lib/              # API、SSE、Zod Schema、高德和状态
│   │   ├── pages/            # home、location、discover、history
│   │   └── main.tsx          # 路由与 QueryClient
│   └── e2e/
└── backend/
    └── app/
        ├── api/             # 公共路由汇总、Schema、错误、健康检查与中间件（扁平结构）
        ├── modules/         # auth、choice、decision、history、location、places、preferences、task
        │   └── decision/workflow/  # LangGraph State、节点、Graph、事件与 Prompt
        ├── infrastructure/  # amap、llm、auth、共享 database 设施
        ├── core/            # 配置、时钟、错误、ID、业务模型基类
        ├── container.py     # 进程级共享服务引用
        ├── bootstrap.py     # 进程生命周期与具体依赖组装
        └── main.py          # FastAPI 应用入口
```

代码按业务模块组织，模块内部保留路由、业务类型与规则、服务、仓储和 ORM 的职责区分；业务类型与纯规则不导入 HTTP、ORM 或 LangGraph。业务路由通过模块的 `dependencies.py` 注入 service。数据库连接与 ORM 基类共用，`infrastructure/database/registry.py` 显式注册全部模块的表。`bootstrap.py` 是具体实现的组装入口；它创建一个进程级 Container、共享 HTTP Client 和数据库 Session Factory，并在 lifespan 中启动/停止 Worker。Container 是服务引用的集合，不是每位用户共享的可变业务会话。

每次数据库操作使用独立 `AsyncSession`，并行路线请求不共享 Session。创建、调整、确认恢复、选择地点通过各自的事务上下文保证跨表原子性。Task 领取、心跳、状态和事件使用短事务；高德与 LLM 调用期间不持有数据库事务。当前 Worker 与 API 运行在同一进程生命周期，后续扩大容量时需评估拆分 Worker 与 API 进程、连接池和上游配额。

## 4. 当前 `/api/v2` 契约

JSON 使用 camelCase，通常包装为 `{ "success": true, "data": ..., "meta": {} }`；错误包装为 `error` 与 `meta`。服务端生成或透传 `X-Request-ID`，写操作按接口使用 `Idempotency-Key`。具体字段和状态码以 `/openapi.json` 与各模块的 router/schema 实现为准；公共 HTTP 支持位于 `app/api`，决策 SSE 帧编码位于 `modules/decision/sse.py`。

| 方法与路径（均以 `/api/v2` 为前缀） | 用途 |
|---|---|
| `GET /health/live`、`GET /health/ready` | 进程存活、数据库与应用就绪检查 |
| `GET /resolved-locations?latitude=&longitude=` | 高德逆地理编码 |
| `GET /location-suggestions?query=` | 地址输入提示 |
| `GET /places?latitude=&longitude=&radiusMeters=&limit=&keywords=` | 周边地点搜索 |
| `GET /places/{place_key}` | 地点详情 |
| `POST /decision-runs` | 创建 Session、Run 与 queued Task，返回 `201` 和 `Location` |
| `GET /decision-runs/{run_id}` | 查询 Run 状态、候选与过滤摘要 |
| `GET /decision-runs/{run_id}/events` | SSE 读取持久化 TaskEvent 与终态 |
| `POST /decision-runs/{run_id}/refinements` | 创建子 Run 和调整 Task |
| `PATCH /decision-runs/{run_id}` | 对需要确认的变更提交 `acceptChanges` 并恢复 |
| `POST /place-choices` | 选择已保存的 Candidate 与记录反馈 |
| `GET /discovery-sessions` | cursor 分页读取历史 |
| `GET /discovery-sessions/{session_id}/decision-runs` | 读取 Session 下的 Run |
| `GET /preferences`、`PUT /preferences` | 读取、替换当前偏好 |

没有同步完成版 `POST /decisions`，也没有 POST SSE、单独 `/evaluations/summary` 或 `GET /discovery-sessions/{id}`。创建 Run 时返回值可能仍为 `pending`，客户端随后订阅事件或查询资源。Run 状态为 `pending`、`running`、`awaitingConfirmation`、`completed`、`failed`。`PATCH` 恢复接口接受确认后立即返回 `202`，客户端继续订阅 SSE；事件包括 `runStarted`、`nodeStarted`、`nodeCompleted`、`confirmationRequired`、`result`、`runFailed`、`heartbeat`。事件由 TaskEvent 保存，断流后重新 GET 可重放；终态也可从 Run 查询恢复。

请求示例（这里只示范输入，不手写虚构的餐厅响应）：

```json
{
  "origin": {"latitude": 31.298, "longitude": 121.514, "address": "上海市杨浦区五角场"},
  "budgetPerPerson": {"min": "20.00", "max": "60.00"},
  "maxWalkingMinutes": 15,
  "radiusMeters": 2000,
  "preferredCuisines": ["面馆", "中餐"],
  "excludedCuisines": ["烧烤"],
  "desiredTags": ["适合一人食"],
  "mealPeriod": "lunch",
  "partySize": 1,
  "openNowPreferred": true,
  "requestText": "想吃热乎的，别走太远"
}
```

`DecisionRunResponse` 包含 `decisionRunId`、`discoverySessionId`、`status`、`request`、`places`、`confirmation`、`filterSummary`、`suggestions`、`errorCode`、`chosenCandidateIds`。候选为 0–3 个；无结果是完成状态加空 `places`，而非伪造地点。`POST /place-choices` 只接收 `candidateId` 和 `feedback`，客户端不能覆盖地点快照。Refine 的动作是 `closer`、`cheaper`、`higherRated`、`differentCuisine`、`refresh`、`excludePlace`、`increaseWalkingLimit`、`changeBudget`；后两种由请求提供明确的新值。

当前没有认证。历史、偏好、Run 与选择都缺少用户归属维度，`Idempotency-Key` 也没有按用户命名空间隔离。多用户上线前必须先设计身份、授权查询条件、数据迁移与幂等键作用域；仅增加多个 API/Worker 进程无法解决数据串读。

## 5. 工作流、持久化与决策规则

### 5.1 受控工作流

当前目录是 `modules/decision/workflow`：节点和高德调用顺序由代码控制，不是自由规划 ReAct Agent。节点名为：

```text
[parse_intent →] confirm_intent
→ search_places → filter_places
→ [无候选: 结束]
→ enrich_routes → [无候选: 结束]
→ score_places → rerank_places → select_diverse
→ generate_explanations → 结束
```

自然语言为空时跳过解析；解析出的步行时间或预算变更可能进入确认状态。确认通过新 Task 继续；不使用 LangGraph Checkpointer 或 `Command(resume=...)`。持久化的工作流版本目前为 `4`；旧的未完成 Task 在迁移时标记为 `WORKFLOW_UPGRADED`，迁移节点名或 State 格式时需考虑已有 Task 的恢复。

`DecisionState` 当前字段：`schema_version`、`task_id`、`decision_run_id`、`request`、`places`、`excluded`、`recent`、`old_cuisines`、`action`、`intent`、`changes`、`awaiting_confirmation`、`confirmation_answer`、`next_node`、`filter_summary`，以及执行期的 `lease_token`、`already_completed`。State 仅保存可 JSON 序列化的恢复数据，不应包含数据库 Session、Client、Key、完整 Prompt 或完整高德 Raw Payload。历史展示从业务表读取。

Task 表保存 queued/running/waiting_confirmation/succeeded/failed 等状态、lease 与 State；TaskStep 保存节点状态摘要；TaskEvent 保存有序业务事件。数据库租约控制并发领取和故障后重领。外部调用需受超时与并发上限约束，失败按明确错误终止 Run，不凭空生成备用结果。

### 5.2 领域模型与规则

`modules/location` 定义 `Point`、`Origin`；`modules/preferences` 定义 `Budget`、`Preferences`；`modules/decision` 定义 `DecisionRequest`、`Intent`、Refinement 和评分/过滤规则；`modules/places` 定义 `Place`、`Route` 及 Provider Protocol。业务类型使用 Pydantic 模型；Pydantic 类型在所属模块的 `schemas.py` 中定义，ORM 表在 `models.py` 中定义，类型转换由模块内的 mapper 处理。`Place` 里照片为 URL 列表，评分、价格、营业状态与路线可为空或未知；候选身份和排序由 `candidateId`、`rank` 表示。

当前菜系枚举为：中餐、面馆、火锅、烧烤、快餐、轻食、日韩料理、东南亚料理、西餐、咖啡甜品、小吃、其他餐饮。请求中的菜系必须在这个集合内，例如 `面馆`，不是旧示例中的 `面食`。

确定性代码负责排除已排除地点、超出搜索半径、明确排除的菜系、明确关闭且偏好营业中的地点、已知人均超过预算上限和步行路线超时的地点。人均、评分或营业状态未知时保留未知与警告，不宣称满足条件。路线必须来自高德步行规划，不能把直线距离换算成精确步行时间。当前没有“严格预算”“严格营业状态”的请求开关；若产品需要，应另行设计契约。

评分由 `modules/decision/rules/policies.py` 的七项权重计算：偏好 0.28、步行 0.22、预算 0.18、评分 0.14、营业可信度 0.06、新颖性 0.05、数据完整度 0.07。调整动作改变对应权重或排除集；多样性逻辑尽量避免同品牌、同菜系占满三个位置。LLM 只解析受限偏好、在已有候选中重排并生成可核实理由，不修改 POI 事实或硬约束。`FoodDecisionLlm` 由 `decision/service/llm.py` 中的 `DecisionLlmService` 实现，负责 Prompt 输入组织和业务结果处理；`decision/rules/llm.py` 集中校验菜系、候选排列与理由证据。服务通过 `StructuredLlm` 协议调用 `infrastructure/llm` 的通用结构化适配器。`GeoPlaceProvider` 仍由 `infrastructure/amap` 实现。

### 5.3 数据库边界

当前表包括 `preferences`、`discovery_sessions`、`decision_runs`、`decision_confirmations`、`place_candidates`、`place_choices`、`place_cache`、`route_cache`、`idempotency_records`、`tasks`、`task_steps`、`task_events`。Session 记录 `radius_meters` 等输入；Run 记录 `filter_summary`、工作流版本与终态；Candidate 保存地点及路线快照；Choice 使用 `created_at` 记录创建时间。当前表都没有 `user_id`。创建 Session、Run、Task 和幂等记录在一个事务中；Task 状态使用短事务。Alembic 迁移负责工作流状态升级，后续增加用户归属时仍需要新的迁移方案。

## 6. 前端当前流程与体验目标

实际路由为 `/`、`/map`、`/discover`、`/decision-runs/:runId`、`/history`、`/profile`。首页包含条件输入，地图页负责选点，Discover 页展示地图、候选与进度，历史页和详情页展示已保存的选择。Profile 组件目前位于 `pages/home.tsx`。不存在 `/evaluation` 页面。

前端使用 `lib/api.ts` 统一请求，`lib/stream.ts` 先 POST 创建 Run，再 GET `/decision-runs/{id}/events` 消费 SSE，Zod 校验完整 Run 响应和事件。断流或终态恢复应通过 GET Run；前端不存在旧文档所述 `useDecisionStream` Hook。地图使用浏览器高德 JS Key，服务端高德 Web Service Key 只在后端。地图失败、空结果、缺失字段和上游错误都应有明确 UI；候选卡显示来源可证的评分、人均、步行信息与风险提示。移动端以地图和结果卡为核心，触控、可读性、减少动画等仍是体验目标，不代表每项已经验收。

## 7. 环境配置与验证

后端配置以 `src/backend/.env.example` 为准：

```env
DATABASE_URL=postgresql+asyncpg://food_nav:food_nav@localhost:5432/food_nav
AMAP_WEB_SERVICE_KEY=replace-with-amap-web-service-key
LLM_API_KEY=replace-with-llm-key
LLM_BASE_URL=replace-with-openai-compatible-base-url
LLM_MODEL=replace-with-model-id
CORS_ORIGINS=http://localhost:5173
AMAP_TIMEOUT_SECONDS=4
AMAP_ROUTE_CONCURRENCY=3
AMAP_CACHE_TTL_SECONDS=600
AMAP_ROUTE_CACHE_TTL_SECONDS=300
LLM_TIMEOUT_SECONDS=10
LLM_MAX_RETRIES=1
LLM_TEMPERATURE=0
LLM_REASONING_EFFORT=low
DECISION_TIMEOUT_SECONDS=20
TASK_LEASE_SECONDS=60
TASK_POLL_SECONDS=1
```

前端配置以 `src/frontend/.env.example` 为准：

```env
VITE_API_BASE_URL=http://localhost:8000/api/v2
VITE_AMAP_JS_KEY=replace-with-amap-js-key
VITE_AMAP_SECURITY_CODE=replace-with-amap-security-code
```

LLM 服务需要支持 Responses API 的 `text.format=json_schema`。`LLM_REASONING_EFFORT` 支持 `none / low / high / max`，默认 `low`；设为 `none` 关闭思考。DeepSeek 在思考模式下忽略 `LLM_TEMPERATURE`。结构化响应仍通过 Pydantic 和业务规则校验；LLM 与高德的异步客户端均由 lifespan 管理和关闭。

浏览器 JS API 与后端 Web 服务 API 需要分别配置对应 Key；前端安全码也必须配置。配置缺失或仍为占位符时，后端校验失败，前端显示配置提示。旧文档中的 `API_V1_PREFIX`、`DATABASE_POOL_SIZE`、`LANGSMITH_*`、`VITE_ENABLE_EVALUATION_PAGE` 目前都不是应用配置项。

当前可用的验证命令在 README 中。后端 `tests/` 覆盖规则、SSE、Worker、模块导入及 ORM 注册，并通过隔离 PostgreSQL 验证事务、幂等、确认恢复、租约、鉴权和路由协作。数据库测试必须显式设置 `TEST_DATABASE_URL`，未配置时跳过；高德和 LLM 使用测试替身，测试通过不代表真实上游联调通过。

## 8. 待决设计与后续工作

1. **多用户**：确定认证方式与用户/租户 ID；为 Session、Run、Choice、Preference、Idempotency 等表增加归属，所有读取和写入按归属限定，并迁移现有无归属数据。进程级 Container 可共享无状态服务，用户状态只放请求上下文与数据库。
2. **并发部署**：先测 API、Worker、PostgreSQL 连接池、高德路线配额和 LLM 并发；按容量拆分 API 与 Worker、限制每类上游调用，继续使用数据库租约和幂等约束。单进程 Worker 是当前实现，不是多实例容量结论。
3. **质量门禁**：恢复后端测试，覆盖事务原子性、Task 领取/失租/恢复、确认分支、幂等冲突、失败终态、SSE 重连和 OpenAPI 兼容。独立 PostgreSQL 集成测试与真实服务联调分别记录结果。
4. **展示增强**：PWA、评测摘要、Tracing、部署工件和 OpenAPI 类型生成按实际需求排期；有产物时再写成当前能力。

## 9. 参考入口

- 后端入口与组装：`src/backend/app/main.py`、`src/backend/app/bootstrap.py`
- API：`src/backend/app/api/router.py`、`src/backend/app/modules/*/router.py`
- 用例：`src/backend/app/modules/decision/service/`
- 工作流：`src/backend/app/modules/decision/workflow/`
- 业务规则：`src/backend/app/modules/decision/rules/policies.py`
- 前端路由与请求：`src/frontend/src/main.tsx`、`src/frontend/src/lib/api.ts`、`src/frontend/src/lib/stream.ts`
- 运行说明：`README.md`
