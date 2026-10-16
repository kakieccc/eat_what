# “今天吃什么”产品与实现参考

> 本文以当前仓库为实现基线，记录产品边界、现有接口和待补能力。它不是从零搭建项目的目录模板。架构和接口以代码及 FastAPI OpenAPI 为准；未实现的产品目标明确标为“待实现”。

## 2. 产品范围与事实边界

### 2.1 核心流程

产品是移动端的线下美食发现、决策与导航 Web 应用：

```text
用户确认出发位置
→ 设置预算、搜索半径、菜系、场景或自然语言偏好
→ LLM 根据完整表单及原文生成生效条件和检索方向
→ 查询确认位置周围指定半径内的真实餐饮 POI
→ 筛选并返回 0–3 个餐厅候选
→ 调整条件或改选餐厅
→ 选择地点、查看直线距离并在高德查看目标地点
→ 保存选择与历史
```

推荐对象是餐厅/美食地点 POI，不是菜单菜品。首版不包含外卖、下单、支付、评论社区、精确营养管理或医疗/过敏安全判断。默认中文、人民币、`Asia/Shanghai` 展示；用户应主动确认位置，不做长期后台位置跟踪。

### 2.2 数据来源

- 高德 JavaScript API：浏览器地图、选点、Marker 和路线可视化。
- 高德 Web 服务 API：逆地理编码、输入提示、餐饮 POI 和地点详情。
- OpenAI-compatible LLM：受限偏好解析、合法候选重排与推荐理由。
- PostgreSQL：业务记录、Task 状态和有效期内的高德响应缓存。

高德是唯一真实地图和餐饮 POI 来源，不引入其他餐饮平台 Adapter。不得虚构餐厅、坐标、评分、人均、营业状态、菜单、库存、排队人数、座位、评价原文或路线。字段缺失时保留未知状态并向用户提示。推荐理由中的事实必须能从高德字段或确定性计算结果验证。地图、POI 和路线的生产路径使用真实服务；单元测试可以使用 fake 来隔离纯逻辑，真实联调仍需有效 Key 和独立 PostgreSQL。

### 2.3 实施优先级

| 优先级 | 内容 | 当前状态 |
|---|---|---|
| 核心 | 高德双端配置、真实 POI/半径检索、受控工作流、Task Worker、SSE、调整、选择与历史 | 代码路径已存在；真实服务联调结果需单独验证 |
| 上线前 | 并发容量与部署策略、后端回归测试、独立数据库恢复测试 | 待实现或待验证 |
| 增强 | PWA、评测摘要、Tracing、生产 Docker、自动生成前端 OpenAPI 类型 | 待实现 |
| 可选 | 收藏/去过/不想再去、多人偏好合并、骑行/驾车、跨设备同步 | 待实现 |

## 3. 当前技术栈与目录

前端：React 19、TypeScript、Vite、React Router、TanStack Query、Zustand、React Hook Form、Zod、Tailwind CSS、Radix UI、Lucide、高德 JS API。保留 TypeScript、ESLint 静态检查工具。

后端：Python 3.12、FastAPI、Pydantic v2、SQLAlchemy Async、asyncpg、PostgreSQL、HTTPX、LangGraph、LangChain 和 OpenAI-compatible LLM。工具配置包含 Ruff、mypy。版本以 `src/frontend/pnpm-lock.yaml` 和 `src/backend/uv.lock` 为准。

```text
src/
├── frontend/
│   └── src/
│   │   ├── components/       # 地图、地点卡、偏好表单与 UI
│   │   ├── lib/              # API、SSE、Zod Schema、高德和状态
│   │   ├── pages/            # home、location、discover、history
│   │   └── main.tsx          # 路由与 QueryClient
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

代码按业务模块组织，模块内部保留路由、业务类型与规则、服务、仓储和 ORM 的职责区分；业务类型与纯规则不导入 HTTP、ORM 或 LangGraph。业务路由通过模块的 `dependencies.py` 注入 service。数据库连接与 ORM 基类共用，`infrastructure/database/metadata.py` 统一注册全部模型；表结构由 `alembic/versions/` 管理，通过 `uv run alembic upgrade head` 初始化或升级，应用启动不再自动建表。`bootstrap.py` 是具体实现的组装入口；它创建一个进程级 Container、共享 HTTP Client 和数据库 Session Factory，并在 lifespan 中启动/停止 Worker。Container 是服务引用的集合，不是每位用户共享的可变业务会话。

每次数据库操作使用独立 `AsyncSession`，并行地点查询不共享 Session。创建、调整、确认恢复、选择地点通过各自的事务上下文保证跨表原子性。Task 领取、心跳、状态和事件使用短事务；高德与 LLM 调用期间不持有数据库事务。当前 Worker 与 API 运行在同一进程生命周期，后续扩大容量时需评估拆分 Worker 与 API 进程、连接池和上游配额。

## 4. 当前 API 契约

JSON 使用 camelCase，通常包装为 `{ "success": true, "data": ..., "meta": {} }`；错误包装为 `error` 与 `meta`。服务端生成或透传 `X-Request-ID`，写操作按接口使用 `Idempotency-Key`。具体字段和状态码以 `/openapi.json` 与各模块的 router/schema 实现为准；公共 HTTP 支持位于 `app/api`，决策 SSE 帧编码位于 `modules/decision/sse.py`。

| 方法与路径 | 用途 |
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
| `POST /place-choices` | 选择或改选 Candidate，只接收 `candidateId`，返回 `200` |
| `GET /discovery-sessions` | cursor 分页读取历史 |
| `GET /discovery-sessions/{session_id}/decision-runs` | 读取 Session 下的 Run |
| `GET /preferences`、`PUT /preferences` | 读取、替换当前偏好 |

创建接口先解析完整表单与原文，冲突返回 `422 INPUT_CONFLICT` 和统一提示，不返回字段详情，不创建 Run。前端按错误码显示固定冲突文案。通过后创建 Session、Run、Task 和幂等记录并返回 `201`。客户端查询或订阅 SSE；Run 状态为 `pending`、`running`、`completed`、`failed`。事件包括 `runStarted`、`nodeStarted`、`nodeCompleted`、`result`、`runFailed`、`heartbeat`。事件由 TaskEvent 保存，断线后可重放，终态从 Run 查询恢复。没有条件确认资源及暂停恢复接口。

请求示例（这里只示范输入，不手写虚构的餐厅响应）：

```json
{
  "origin": {"latitude": 31.298, "longitude": 121.514, "address": "上海市杨浦区五角场"},
  "preferences": {
    "budgetPerPerson": {"min": "20.00", "max": "60.00"},
    "radiusMeters": 2000,
    "preferredFoods": ["面馆", "中餐"],
    "excludedFoods": ["烧烤"],
    "allowedFoods": [],
    "softPreferences": ["适合一人食"]
  },
  "mealPeriod": "lunch",
  "partySize": 1,
  "requestText": "想吃热乎的，优先附近的餐厅"
}
```

`DecisionRunResponse` 包含 `decisionRunId`、`discoverySessionId`、`status`、生效 `request`、`originalRequest`、`intent`、`places`、`filterSummary`、`suggestions`、`errorCode` 和可空 `choice`。`intent` 包含 `effectiveRequest`、`searchKeywords` 和 `unhandledRequirements`。`choice` 包含 `id/candidateId/decisionRunId/selectedAt`，指向会话的唯一最终选择，可能来自同会话的其他 Run。候选为 0–3 个，空结果正常完成。

Refine 动作为 `closer`、`cheaper`、`higherRated`、`differentCuisine`、`refresh`、`excludePlace`、`changeRadius`、`changeBudget`。后两项接受明确新值，不重新解析旧原文。`excludePlace` 仅排除指定地点；`refresh` 排除本会话所有已展示地点；排序调整可保留已有候选。`differentCuisine` 在硬条件内扩大检索方向并降低上一轮类型的排序优先级。

账号会话认证和用户隔离已实现，幂等键按用户及操作隔离。每个发现会话只有一个最终选择；重复选择同一候选不变，改选更新同一行及选择时间。历史按选择时间降序，条件取最终选择所在 Run 的生效快照。

## 5. 工作流、持久化与决策规则

### 5.1 受控工作流

当前目录是 `modules/decision/workflow`：节点和高德调用顺序由代码控制，不是自由规划 ReAct Agent。节点名为：

```text
提交阶段：完整表单 + 原文 → LLM 意图解析与冲突校验 → 创建 Run/Task
后台：search_places → filter_places（评分、详情、再过滤）
→ [无候选: 结束]
→ rerank_places → select_diverse → generate_explanations → 结束
```

原文为空时仍依据完整表单生成检索方向；原文可补充、收紧条件，放宽预算/半径或取消排除返回统一冲突错误。人数和餐段明确矛盾也返回同一错误。LLM 仅用 `hasConflict` 表示是否冲突，后端仍校验硬条件是否放宽。解析不持有数据库事务，成功后短事务原子写入 Session/Run/Task/幂等结果。原始请求与生效请求分开保存。工作流版本为 `8`、提示词版本为 `6`；表结构变化通过 Alembic 迁移。

State 保存请求、意图、检索关键词、排除集合、最近选择、上一轮类型、动作、候选和过滤摘要，以及执行恢复所需的节点与租约信息；不保存数据库 Session、Client 或密钥。Task 保存 queued/running/succeeded/failed 状态、lease 与 State；TaskStep 保存节点摘要；TaskEvent 保存有序事件。外部调用受超时和请求预算约束，失败明确终止，不生成备用餐厅事实。

### 5.2 领域模型与规则

`modules/location` 定义 `Point`、`Origin`；`modules/preferences` 定义 `Budget`、`Preferences`；`modules/decision` 定义 `DecisionRequest`、`Intent`、Refinement 和评分/过滤规则；`modules/places` 定义 `Place` 及 Provider Protocol。业务类型使用 Pydantic 模型；Pydantic 类型在所属模块的 `schemas.py` 中定义，ORM 表在 `models.py` 中定义，类型转换由模块内的 mapper 处理。`Place` 里照片为 URL 列表，评分和价格可为空；候选身份和排序由 `candidateId`、`rank` 表示。

`Preferences` 只包含预算、半径、偏好食物、排除食物、限定食物和软偏好；位置、原文、人数、餐段属于 `DecisionRequest`。食物可为任意菜系、菜品或类型；限定列表内部为 OR，空列表不限定。仅用户明确限定时生成硬食物条件，“清淡”等用于软偏好和关键词扩展。无法用 POI 核实的要求单独返回，不能声称已满足。

半径仅支持 500、1000、2000、5000 米四档，使用直线距离。代码剔除明确排除的地点和食物标签、超范围、已知低于预算下限或高于上限的地点。缺少人均、评分和匹配信息时保留并提示。应用不记录或检查营业状态，营业时间仅展示来源文本。

关键词最多五个，每页 25 条，轮询各方向并继续分页，每 Run 最多八次搜索请求。合并去重和确定性过滤后才截取前十个候选，补详情后重新过滤。新详情只覆盖非空且不旧于已有字段的信息，快照记录字段采集时间。候选不足时允许原条件下通用餐饮检索，不自动放宽约束。LLM 基于名称、分类、标签等证据判断食物匹配并重排；明确不匹配剔除，未知保留提示。所有返回 ID 和证据必须来自候选。

确定性评分用于详情补全前选取候选，权重包括偏好、距离、预算、评分、新颖性和数据完整度；LLM 再结合完整软偏好和调整动作排序。多样性选择最多三家，推荐理由从已有事实短句中选择。内部综合分不作为面向用户的推荐事实。高德分类和标签按来源保留，不从店名硬编码菜系映射。`DecisionLlmService` 编排结构化调用，`rules/llm.py` 校验冲突、排列与证据，`infrastructure/llm` 处理通用模型接口。

### 5.3 数据库边界

当前包含 13 张应用表和一张 Alembic 版本表，已移除条件确认表。Session 保存完整原始 `request_snapshot`；Run 保存原始请求、意图、生效请求、版本及状态；Candidate 保存地点快照；Choice 对会话有唯一约束并记录 `selected_at`。历史单次关联查询读取当前选择及对应 Run。请求幂等只保存在共享 `idempotency_records` 中，业务唯一约束与行锁另行保障单会话单选择。初始迁移为 `0001`；后续表结构变更生成并审阅 Alembic 迁移，再升级数据库。

## 6. 前端当前流程与体验目标

实际路由为 `/`、`/map`、`/discover`、`/decision-runs/:runId`、`/history`、`/profile`。首页包含条件输入，地图页负责选点，Discover 页展示地图、候选与进度，历史页和详情页展示已保存的选择。Profile 组件目前位于 `pages/home.tsx`。不存在 `/evaluation` 页面。

前端使用 `lib/api.ts` 统一请求，首页提交时 POST 创建 Run，冲突在表单显示固定文案“表单条件与补充说明存在冲突，请调整条件后重试。”，成功后导航结果页；`lib/stream.ts` GET `/decision-runs/{id}/events` 消费 SSE，Zod 校验完整 Run 响应和事件。断流或终态恢复应通过 GET Run；前端不存在旧文档所述 `useDecisionStream` Hook。地图使用浏览器高德 JS Key，服务端高德 Web Service Key 只在后端。地图失败、空结果、缺失字段和上游错误都应有明确 UI；候选卡显示来源可证的评分、人均、直线距离与风险提示。移动端以地图和结果卡为核心，触控、可读性、减少动画等仍是体验目标，不代表每项已经验收。

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
AMAP_CACHE_TTL_SECONDS=600
AMAP_EMPTY_CACHE_TTL_SECONDS=30
LLM_TIMEOUT_SECONDS=10
LLM_MAX_RETRIES=1
LLM_TEMPERATURE=0
DECISION_TIMEOUT_SECONDS=20
TASK_LEASE_SECONDS=60
TASK_POLL_SECONDS=1
```

前端配置以 `src/frontend/.env.example` 为准：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_JS_KEY=replace-with-amap-js-key
VITE_AMAP_SECURITY_CODE=replace-with-amap-security-code
```

LLM 服务需要支持 Responses API 的严格 `text.format=json_schema`。调用固定使用 `reasoning.effort=none` 关闭思考，通过 `responses.parse(text_format=schema)` 生成并校验结构化响应，随后执行业务规则校验；LLM 与高德的异步客户端均由 lifespan 管理和关闭。

浏览器 JS API 与后端 Web 服务 API 需要分别配置对应 Key；前端安全码也必须配置。配置缺失或仍为占位符时，后端校验失败，前端显示配置提示。旧文档中的 `API_V1_PREFIX`、`DATABASE_POOL_SIZE`、`LANGSMITH_*`、`VITE_ENABLE_EVALUATION_PAGE` 目前都不是应用配置项。

静态检查与测试命令在 README 中。后端包含 pytest 单元、独立 PostgreSQL 集成和真实上游验收；前端包含 Vitest 逻辑与组件测试、Playwright 桌面及移动视口验收。真实测试单独触发且不自动重跑，推荐语义由人工复核；用例范围、环境与报告说明见 `docs/testing.md`。

## 8. 待决设计与后续工作

1. **多用户**：确定认证方式与用户/租户 ID；为 Session、Run、Choice、Preference、Idempotency 等表增加归属，所有读取和写入按归属限定，并迁移现有无归属数据。进程级 Container 可共享无状态服务，用户状态只放请求上下文与数据库。
2. **并发部署**：先测 API、Worker、PostgreSQL 连接池、高德路线配额和 LLM 并发；按容量拆分 API 与 Worker、限制每类上游调用，继续使用数据库租约和幂等约束。单进程 Worker 是当前实现，不是多实例容量结论。
3. **质量门禁**：已有测试覆盖事务原子性、Task 领取/失租/恢复、幂等冲突、失败终态、SSE 重连和 OpenAPI 契约；后续修复测试暴露的业务缺陷，并根据真实验收结果确定上线门槛。独立 PostgreSQL 集成测试与真实服务验收分别记录结果。
4. **展示增强**：PWA、评测摘要、Tracing、部署工件和 OpenAPI 类型生成按实际需求排期；有产物时再写成当前能力。

## 9. 参考入口

- 后端入口与组装：`src/backend/app/main.py`、`src/backend/app/bootstrap.py`
- API：`src/backend/app/api/router.py`、`src/backend/app/modules/*/router.py`
- 用例：`src/backend/app/modules/decision/service/`
- 工作流：`src/backend/app/modules/decision/workflow/`
- 业务规则：`src/backend/app/modules/decision/rules/policies.py`
- 前端路由与请求：`src/frontend/src/main.tsx`、`src/frontend/src/lib/api.ts`、`src/frontend/src/lib/stream.ts`
- 运行说明：`README.md`
