
## 优先修复

### 1. [P1 · 已修复] 刷新清空本次条件、位置和当前推荐 ID

- **位置：**[auth.tsx:74](src/frontend/src/lib/auth.tsx#L74)、[store.ts:66](src/frontend/src/lib/store.ts#L66)。
- **原问题：**重新加载时内存中的账号 ID 丢失，恢复同一账号也清空本次草稿、确认位置和 `runId`。
- **处理：**草稿持久化 `ownerId`，同账号刷新保留，退出、401 或换账号时清空；临时网络错误保留并允许重试。草稿版本升至 `5`，旧版无账号归属的草稿重置一次。
- **验证：**新增 12 项回归测试通过；Playwright 桌面/移动视口确认生成中及已完成推荐刷新恢复、条件与位置保留、退出清理，无页面运行时错误。浏览器使用接口和地图测试替身。
- **边界：**数据库推荐记录没有被删除；已选择记录可从历史找回，带 Run ID 的详情 URL 也能重新查询。账户已保存的偏好仍在数据库中。

### 2. [P1 · 复现] 旧半径记录无法读取，页面中的兼容提示到达不了

- **位置：**[preferences/schemas.py:26](src/backend/app/modules/preferences/schemas.py#L26)、[mappers.py:24](src/backend/app/modules/decision/repository/mappers.py#L24)、[schemas.ts:50](src/frontend/src/lib/schemas.ts#L50)。
- **场景与影响：**数据库历史或偏好包含旧半径 `1500` 时，读取即被当前四档半径模型拒绝，服务端产生校验异常；前端 `runSchema` 同样拒绝。用户看不到 `needsRadiusSelection` 对应的“旧记录请重新选择”提示；一条旧记录也可能阻断整页历史。
- **建议：**区分历史读取模型与新请求模型；旧值允许展示，新提交必须选合法档位。需要迁移时明确提示用户，不静默改变搜索范围。

### 3. [P2 · 复现] `GET /places` 显式填写合法半径也返回 422

- **位置：**[places/router.py:22](src/backend/app/modules/places/router.py#L22)。
- **场景与影响：**`?latitude=31&longitude=121&radiusMeters=1000` 返回 422；省略半径反而成功。URL 参数是字符串，整数 `Literal` 不负责将它转换为整数。
- **建议：**先按整数读取 Query，再使用现有 `require_supported_radius()` 验证；保留四档限制。

### 4. [P2 · 复现] 一家餐厅详情不存在，整批推荐一起失败

- **位置：**[filter_places.py:68](src/backend/app/modules/decision/workflow/nodes/filter_places.py#L68)、[provider.py:145](src/backend/app/infrastructure/amap/provider.py#L145)。
- **场景与影响：**搜索返回候选后，某家详情为空，适配器抛出 `PLACE_NOT_FOUND`；筛选节点没有处理，批量等待取消其他候选，整次推荐失败。
- **建议：**将该错误作为单个候选失效处理，剔除并记录提示，继续处理其他候选。

### 5. [P2 · 复现] 填好条件后进入选址页，返回时输入消失

- **位置：**[home.tsx:37](src/frontend/src/pages/home.tsx#L37)、[home.tsx:66](src/frontend/src/pages/home.tsx#L66)。
- **场景与影响：**修改预算或补充说明，再点击地址链接；表单直接卸载，只有点击提交才保存的草稿没有更新。返回首页恢复的是旧条件。
- **建议：**离开首页选址前保存当前输入；草稿允许暂时不合法，提交时再做完整校验。

### 6. [P2 · 复现] 高级条件输入后按 Escape 关闭，内容未保存

- **位置：**[preferences-form.tsx:221](src/frontend/src/components/preferences-form.tsx#L221)。
- **场景与影响：**在“只考虑这些食物”等输入框填写内容，直接按 Escape 关闭面板，然后提交。字段只在 `onBlur` 写入表单，关闭卸载没有可靠触发该回调，提交仍是旧值。
- **建议：**维护输入中的原始文本，并在变更或关闭面板时保存；不要仅靠失焦保存条件。

### 7. [P2 · 复现] 迟到的 GPS 结果覆盖后来手动选的位置

- **位置：**[location.tsx:43](src/frontend/src/pages/location.tsx#L43)、[location.tsx:62](src/frontend/src/pages/location.tsx#L62)。
- **场景与影响：**先点击定位，再手动选点。GPS 完成后才调用 `pick()` 并取得新序号，覆盖用户后来的选择；旧定位失败回调也能覆盖新操作的错误和忙碌状态。
- **建议：**从发起 GPS 时就记录操作序号；手动选点后，忽略旧 GPS 的成功、失败及结束回调。

### 8. [P2 · 静态] 过时推荐的恢复逻辑无法修复当前详情地址

- **位置：**[history.tsx:148](src/frontend/src/pages/history.tsx#L148)、[recommendations.ts:35](src/frontend/src/lib/recommendations.ts#L35)。
- **场景与影响：**新标签页打开已被替换的 Run，409 响应没有提供 `sessionId`，前端又没有缓存，恢复逻辑无法启动。已有缓存时，恢复也只更新草稿，详情 URL 仍指向旧 Run，页面继续报错。
- **建议：**在验证账户归属后提供当前 Run 的恢复信息，成功恢复时替换详情 URL；不要提示用户执行无效的刷新。

## 应该修复

### 9. [P2 · 复现] 读取账户偏好失败，首页静默使用默认条件

- **位置：**[home.tsx:71](src/frontend/src/pages/home.tsx#L71)。
- **场景与影响：**首次打开首页时 `/preferences` 返回 503，页面不显示失败，直接展示默认表单。用户可能以为账户中的排除项、预算已经生效，实际提交的是默认值。
- **建议：**像偏好页一样展示读取失败和重试入口；使用默认值时明确说明。

### 10. [P2 · 复现] 服务端偏好更新后，表单仍显示旧值

- **位置：**[preferences-form.tsx:45](src/frontend/src/components/preferences-form.tsx#L45)、[home.tsx:91](src/frontend/src/pages/home.tsx#L91)。
- **场景与影响：**页面先显示查询缓存，后台重新获取到更新的偏好；`initial` 已改变，但 `useForm.defaultValues` 只初始化一次。用户继续看到并可能重新保存旧条件。
- **建议：**新快照到达时同步未编辑的表单；用户正在编辑时保留输入并提示更新，避免直接覆盖。

### 11. [P2 · 静态] 历史详情的“返回推荐”可能跳到另一餐

- **位置：**[history.tsx:192](src/frontend/src/pages/history.tsx#L192)。
- **场景与影响：**当前草稿是 B 餐，从历史打开 A 餐详情，再点击“返回推荐”；链接只跳到 `/discover`，该页读取全局草稿，因此展示 B 餐。草稿为空时则没有推荐结果。
- **建议：**返回前明确选定该详情对应的 Run，或让推荐页 URL 携带 Run ID。

### 12. [P2 · 静态] 请求挂起时，“恢复查询”提示无法操作

- **位置：**[api.ts:72](src/frontend/src/lib/api.ts#L72)、[stream.ts:73](src/frontend/src/lib/stream.ts#L73)、[discover.tsx:155](src/frontend/src/pages/discover.tsx#L155)、[discover.tsx:257](src/frontend/src/pages/discover.tsx#L257)。
- **场景与影响：**提交请求或 SSE 保持连接但不再返回数据，浏览器端没有截止时间。25 秒后虽显示可以恢复查询，按钮仍因 `busy` 禁用；首页提交也可能一直显示处理中。
- **建议：**为请求及无进展的订阅设置合理截止时间；允许终止订阅并查询已创建的 Run，不要求用户刷新丢失上下文。

### 13. [P2 · 复现] 同一账号并发首次保存偏好，其中一次变成 503

- **位置：**[preferences/repository.py:30](src/backend/app/modules/preferences/repository.py#L30)。
- **场景与影响：**两个标签页同时首次保存。`FOR UPDATE` 锁不到尚不存在的行，两次读取都为空，随后同时插入；一次触发 `user_id` 唯一约束错误，被统一转成数据库不可用。
- **建议：**使用 PostgreSQL 冲突更新，或先锁定已存在的用户行；让保存操作的并发语义明确。

### 14. [P2 · 静态] 每进程只执行一单，排队时间不计入预算

- **位置：**[task/service.py:49](src/backend/app/modules/task/service.py#L49)、[runner.py:87](src/backend/app/modules/decision/service/runner.py#L87)。
- **场景与影响：**多位用户同时请求时，Worker 等上一单全部执行完才领取下一单。三单各执行约 15 秒，第三单仅排队就约 30 秒；默认 20 秒预算没有限制这段等待。
- **建议：**先定义排队期限和繁忙提示，再按上游配额决定有限并发。上述时间为代码推导，未经压测。

### 15. [P2 · 复现] 明知配料限制无法验证，仍先检索和补全详情

- **位置：**[graph.py:77](src/backend/app/modules/decision/workflow/graph.py#L77)、[llm.py:55](src/backend/app/modules/decision/service/llm.py#L55)。
- **场景与影响：**意图已经包含 `excluded_ingredients`，当前规则最终一定返回空结果，但判断直到重排才执行。此前仍调用高德；高德故障时，请求会先失败，无法得到规则原本要求的正常空结果。
- **建议：**在进入搜索前完成这项准入判断，直接生成带明确原因的空结果。

### 16. [P2 · 复现/静态] 金额格式及精度在前后端不一致

- **位置：**[schemas.ts:28](src/frontend/src/lib/schemas.ts#L28)、[preferences/schemas.py:13](src/backend/app/modules/preferences/schemas.py#L13)、[preferences/models.py:21](src/backend/app/modules/preferences/models.py#L21)。
- **场景与影响：**前端将 `0x10` 和纯空格判断为合法金额，后端 Decimal 拒绝，用户得到泛化的输入错误（已复现）。双方又允许超过两位小数，而偏好表是 `Numeric(10, 2)`，保存后重新读取会发生舍入（由表结构确定）。
- **建议：**统一十进制格式、空值和小数精度；在输入边界拒绝或明确规范化，再用于推荐和持久化。

### 17. [P2 · 复现] 登录密码没有后端长度上限

- **位置：**[auth/schemas.py:28](src/backend/app/modules/auth/schemas.py#L28)、[auth/schemas.py:45](src/backend/app/modules/auth/schemas.py#L45)。
- **场景与影响：**注册限制 128 字，但登录密码和修改密码时的旧密码没有上限；百万字符的登录密码仍通过模型校验并可进入密码验证。前端 `maxLength` 不能限制直接调用 API 的请求。
- **建议：**为所有密码输入设置与注册一致的上限，尽早拒绝无效长输入，减少不必要的资源消耗。

### 18. [P2 · 复现] 任务运行配置允许零和负数

- **位置：**[config.py:23](src/backend/app/core/config.py#L23)。
- **场景与影响：**`decision_timeout_seconds=-1`、`task_lease_seconds=0`、`task_poll_seconds=0` 均通过配置校验，分别可能导致推荐立即超时、任务租约立即失效、空队列高频轮询数据库。
- **建议：**像高德超时配置一样添加正数约束；无效配置应在启动时失败。

### 19. [P2/P3 · 复现] 时间新旧没有贯穿缓存与详情合并

- **位置：**[cache.py:78](src/backend/app/infrastructure/amap/cache.py#L78)、[filter_places.py:43](src/backend/app/modules/decision/workflow/nodes/filter_places.py#L43)。
- **场景与影响：**并发请求中较旧响应晚写入时，会无条件覆盖较新的缓存及有效期（P2，已复现）。另外，合并新详情虽更新字段时间，却保留原 `data_updated_at`，页面的统一更新时间不能体现这次详情更新（P3，已复现）。
- **建议：**缓存仅接受不早于已保存采集时间的数据；同时明确统一更新时间的含义，或展示相关字段的采集时间。

### 20. [P2 · 复现] 测试和文档入口已失效，无法复验关键业务

- **位置：**[pyproject.toml:42](src/backend/pyproject.toml#L42)、[vitest.config.ts:11](src/frontend/vitest.config.ts#L11)、[playwright.config.ts:57](src/frontend/playwright.config.ts#L57)、[README.md:83](README.md#L83)。
- **场景与影响：**审查时不存在后端 `tests/`、前端 `tests/` 和 `docs/testing.md`。pytest 返回退出码 5，Vitest 返回退出码 1；浏览器启动依赖的 `tests.serve` 也无法导入。README 的工作流/提示词版本仍为 `8/6`，代码实际为 `9/7`。第一条修复已补充前端认证草稿的 12 项回归测试，其他缺失的验证入口仍待恢复。
- **建议：**恢复当前实现对应的测试与启动夹具，并同步文档。上一轮测试数量不能作为当前工作区的验证结论。

## 需要明确的产品取舍

这些行为有既有设计依据，不按实现错误处理，但会影响操作直觉：

- **调整推荐会删除已保存的选择和旧结果。**[transaction.py:175](src/backend/app/modules/decision/repository/transaction.py#L175) 在新一轮被接受时执行删除；新推荐失败也不会恢复旧历史。至少在已有选择时说明操作后果。
- **“更近／更便宜／换口味”是排序偏好。**[policies.py:79](src/backend/app/modules/decision/rules/policies.py#L79) 调整权重，不保证结果一定更近、更便宜或不同。提示语应表达“优先寻找”，避免用户误解为硬性保证。
- **营业状态、真实道路距离、配料安全没有被验证。**继续保留现有事实边界，不应将未知信息展示成满足条件。

## 本次验证

| 检查 | 当前结果 |
|---|---|
| Ruff：`ruff check app` | 通过 |
| mypy：`mypy app` | 通过，126 个源文件 |
| 前端业务及测试配置类型检查 | 通过；类型检查通过不代表缺失的测试已运行 |
| ESLint | 通过 |
| Vite 生产构建 | 通过；主包约 536 kB，有体积提示及依赖注释警告 |
| 项目 pytest / Vitest | 审查时均无测试文件；第一条修复后新增前端 12 项测试通过，后端测试仍缺失 |
| 浏览器后端入口 `python -B -m tests.serve` | 失败：模块不存在 |
| 临时前端自检 | 7 项通过，确认刷新、跳转、Escape、GPS、表单同步、偏好失败和金额格式问题 |
| 临时后端自检 | 确认半径参数、旧快照、详情失败、配料判断、密码长度、配置和时间处理问题 |
| 隔离 PostgreSQL 自检 | 确认首次保存偏好的竞态及旧缓存覆盖；仅使用 `food_nav_test` 的临时 schema，已清理 |

## 结论与限制

先修复状态恢复、历史兼容、参数转换和单候选异常隔离，再恢复正式回归测试；不需要整体重写业务分层。

未检查第三方依赖源码、生成文件和密钥内容；未调用真实高德或 LLM，未执行真实浏览器、性能压测或完整数据库迁移往返。临时自检文件会清理，仅保留本报告；静态确认的并发和交互结论仍应补入正式回归测试。
