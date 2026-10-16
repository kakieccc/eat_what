## 当前问题

### R01〔高〕软偏好被当成必须满足的条件

**位置：** [llm.py:106](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/decision/service/llm.py:106)。

**触发与影响：** 选择“适合聊天”等场景，餐厅缺乏相关信息，评估全部为 `unknown` 时，代码直接剔除餐厅。即使预算、距离均符合，也可能返回空结果。软偏好实际变成了硬筛选。已用合法的未知评估结果复现。

**建议：** 软偏好用于排序和提示；未知或不匹配的餐厅保留为后备候选。

### R02〔高〕读取账户偏好失败后，首页悄悄使用默认条件

**位置：** [home.tsx:71](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/home.tsx:71)。

**触发与影响：** 新会话读取 `/preferences` 返回 `503`，首页直接显示默认预算、范围和空排除列表，没有错误提示，并允许提交。用户已保存的“不吃什么”等条件因此缺失。组件测试和浏览器均已复现。

**建议：** 加载失败显示错误与重试，不把“读取失败”当成“没有保存偏好”。

### R03〔高〕保存账户偏好会覆盖本次选餐草稿

**位置：** [home.tsx:123](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/home.tsx:123)。

**触发与影响：** 首页填写本次说明、4 人、晚餐，再去偏好页保存，`draft.setPreferences(saved)` 会把本次内容替换为账户偏好加默认值：说明清空、人数变 1、餐段变午餐。旧 `runId` 却仍保留，草稿与已有推荐可能不一致。桌面和手机宽度均已复现。

**建议：** 保存账户偏好只更新账户数据与缓存，保留已有本次草稿；在开始新选餐时明确应用默认偏好。

### R04〔高〕离开页面后，旧请求仍能跳转和写回状态

**位置：** [home.tsx:47](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/home.tsx:47)、[discover.tsx:170](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/discover.tsx:170)。

**触发与影响：** 提交推荐后，在响应返回前进入选址页，旧响应仍会写入 `runId` 并强制跳回推荐页。若已发起新的选餐，旧响应还可能覆盖新入口。首页场景已复现；“选这家”请求完成后也存在无页面有效性检查的跳转路径。

**建议：** 为请求绑定页面及草稿代次，离开页面或开始新操作后，忽略旧请求的跳转和过时状态写回。

### R05〔中〕请求挂起时，“恢复查询”也无法使用

**位置：** [api.ts:74](/Users/kakie/Resource/code/eat_what/src/frontend/src/lib/api.ts:74)、[discover.tsx:155](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/discover.tsx:155)。

**触发与影响：** 普通 `fetch` 没有客户端超时；调整推荐时如果 POST 或 SSE 一直不结束，`busy` 持续为真。25 秒后虽提示可以恢复查询，但“查询结果”按钮仍被禁用，自动查询也因 `!busy` 停止。已用挂起请求及模拟时钟复现。

**建议：** 增加请求超时与可中断的恢复入口；恢复查询时退出挂起状态，并按已知会话查询当前结果。

### R06〔中〕迟到的 SSE 会取消“另一页已选定”的刷新

**位置：** [discover.tsx:83](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/discover.tsx:83)、[recommendations.ts:60](/Users/kakie/Resource/code/eat_what/src/frontend/src/lib/recommendations.ts:60)。

**触发与影响：** B 页选定餐厅，A 页收到通知并开始 GET 刷新；此时旧 SSE `result` 到达，调用 `cancelQueries` 取消刷新，并写回尚未选择的快照。A 页继续显示可换批状态，且轮询已关闭。后端仍会拒绝修改，但前端结束状态没有及时生效。已复现该事件顺序。

**建议：** 收到选定通知后保留权威刷新，忽略此前的未选定 SSE 快照；不能仅依赖缓存中已经存在 `choice` 才保护结束状态。

### R07〔中〕调整推荐后返回首页，条件退回调整前

**位置：** [discover.tsx:120](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/discover.tsx:120)、[discover.tsx:226](/Users/kakie/Resource/code/eat_what/src/frontend/src/pages/discover.tsx:226)。

**触发与影响：** 从 2 km 调整为 1 km 后，当前 Run 已是 1 km，但本次草稿未同步。“调整条件”只是跳转首页，表单仍选中 2 km；预算调整也有相同路径。已复现半径场景。

**建议：** 调整入口统一用当前 `run.request` 回填表单，可复用已有 `editRequest`；明确处理旧补充说明，避免再次提交时与新条件冲突。

### R08〔中〕另一标签页切换账户后，本页身份和请求账户错位

**位置：** [auth.tsx:85](/Users/kakie/Resource/code/eat_what/src/frontend/src/lib/auth.tsx:85)、[api.ts:77](/Users/kakie/Resource/code/eat_what/src/frontend/src/lib/api.ts:77)。

**触发与影响：** 两页登录 A，另一页退出后登录 B，共享 Cookie 已变成 B；本页只在挂载时检查身份，仍保留 A 的用户、缓存、草稿归属和 CSRF。随后 GET 可读取 B 的数据，写操作却带 A 的 CSRF 而返回 `403`。已用会话切换模拟复现身份与返回数据不一致。

**建议：** 登录、退出和改密时广播会话变化，其他页重新检查 `/auth/me`，再同步身份并清理不属于当前账户的缓存和草稿。

### R09〔中〕首次同时保存偏好，会有一个请求失败

**位置：** [repository.py:30](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/preferences/repository.py:30)。

**触发与影响：** 新账户在两个标签页同时保存，双方都查询不到偏好行。`FOR UPDATE` 没有行可锁，随后同时插入，只有一个成功，另一个触发唯一约束错误，被 HTTP 层映射成 `503`。已在独立 PostgreSQL schema 中复现。

**建议：** 使用按 `user_id` 冲突更新的原子 upsert，或先锁定始终存在的用户行。

### R10〔中〕配料限制注定返回空结果，却先执行整套检索

**位置：** [llm.py:26](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/decision/service/llm.py:26)、[llm.py:55](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/decision/service/llm.py:55)。

**触发与影响：** “不能含香菜”等要求解析到 `excludedIngredients` 后，仍创建任务、搜索并补详情，最后重排直接返回空列表。页面显示“附近没有合适选择”并建议改预算/距离，但真正原因是无法核实配料。已在完整 Graph 中复现先检索、后空结果。

**建议：** 在解析阶段返回明确的“无法核实配料要求”错误，停止无效检索，不自动忽略这项限制。

### R11〔中〕表单不会跟随重新读取的账户偏好更新

**位置：** [preferences-form.tsx:36](/Users/kakie/Resource/code/eat_what/src/frontend/src/components/preferences-form.tsx:36)。

**触发与影响：** 页面先用旧查询缓存渲染，后台 GET 得到更新偏好后，`initial` 虽改变，但 `useForm.defaultValues` 和 `foodInputs` 都只初始化一次。用户看到旧值，再保存可能覆盖服务器新值。已用更新 `initial` 的组件测试复现。

**建议：** 区分数据刷新与用户编辑；未编辑的表单在来源更新时执行 `reset`，并同步高级文本状态，避免覆盖正在输入的内容。

### R12〔中〕预算格式和小数精度在三层之间不一致

**位置：** [schemas.ts:28](/Users/kakie/Resource/code/eat_what/src/frontend/src/lib/schemas.ts:28)、[schemas.py:13](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/preferences/schemas.py:13)、[models.py:21](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/preferences/models.py:21)。

**触发与影响：** 前端把 `0x10`、纯空格当合法金额，后端 Decimal 会拒绝。两端还允许超过两位小数，但数据库只存两位：保存 `20.001–60.999` 时响应仍是原值，重新读取却变成 `20.00–61.00`。这两种差异均已复现。

**建议：** 两端统一普通十进制格式和最多两位小数；保存响应与实际存储值保持一致。

### R13〔中〕登录及旧密码校验缺少长度上限

**位置：** [schemas.py:29](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/auth/schemas.py:29)。

**触发与影响：** 注册和新密码限制为 128 字符，登录 `password`、改密 `currentPassword` 却不限制长度，超长输入会继续进入密码校验。已确认 10 万字符能通过这两个请求模型，增加了不必要的内存和哈希处理负担。

**建议：** 在请求边界统一密码长度上限，拒绝超过账户密码规格的输入。

### R14〔中〕部分运行参数允许零值和负值

**位置：** [config.py:23](/Users/kakie/Resource/code/eat_what/src/backend/app/core/config.py:23)。

**触发与影响：** LLM 超时、推荐超时、Task 租约和轮询间隔没有正数约束。自检中 `0/-1` 均被接受；可导致请求立即超时、租约立即过期，或 Worker 无等待地反复查库。错误配置未在启动时被拦截。

**建议：** 为这些参数增加正数和合理范围校验，并保证租约长于心跳间隔。

### R15〔中〕较旧的缓存响应能覆盖较新的数据

**位置：** [cache.py:78](/Users/kakie/Resource/code/eat_what/src/backend/app/infrastructure/amap/cache.py:78)。

**触发与影响：** 同一缓存键发生并发未命中，较早采集的响应若较晚写入，会无条件覆盖较新响应及其有效期。已在 PostgreSQL 中验证“先写新、后写旧”会读到旧数据；上层字段合并也无法恢复已被覆盖的缓存。

**建议：** 冲突更新时比较响应的 `fetched_at`，仅允许不旧于现有缓存的数据覆盖。

### R16〔中〕一条坏 POI 会使整页正常餐厅一起失效

**位置：** [schemas.py:45](/Users/kakie/Resource/code/eat_what/src/backend/app/infrastructure/amap/schemas.py:45)、[mappers.py:87](/Users/kakie/Resource/code/eat_what/src/backend/app/infrastructure/amap/mappers.py:87)。

**触发与影响：** 搜索页中某条 POI 坐标为空或字段异常时，整体模型校验或列表转换直接失败，正常记录也被丢弃，可能使整个推荐返回上游错误。已用一条正常 POI 加一条空坐标 POI 复现整批转换失败。

**建议：** 逐条校验、转换 POI，剔除坏记录并记录数量；整体响应结构损坏仍按错误处理。

### R17〔中〕任务恢复后，已消耗的执行预算被重新发放

**位置：** [runner.py:87](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/decision/service/runner.py:87)、[repository.py:112](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/task/repository.py:112)。

**触发与影响：** 节点检查点只保存 State，没有累计执行耗时；`run.duration_ms` 在任务完成时才增加。进程中断后恢复仍只扣除意图解析耗时，重新获得后台预算。已在 PostgreSQL 中复现：预算 80 ms，先执行 50 ms 后中断，恢复再执行 50 ms 仍正常完成。

**建议：** 在检查点持久化累计耗时或剩余预算，恢复时扣除；预算已耗尽则直接结束任务。

### R18〔中〕真实验收入口失效，用例还在验证已取消的改选规则

**位置：** [playwright.config.ts:57](/Users/kakie/Resource/code/eat_what/src/frontend/playwright.config.ts:57)、[app.live.spec.ts:247](/Users/kakie/Resource/code/eat_what/src/frontend/e2e/app.live.spec.ts:247)。

**触发与影响：** E2E 启动命令依赖不存在的 `tests.serve`，实际执行报 `No module named tests.serve`。即使补齐入口，用例仍查找已删除的“已选这家”“返回推荐”，并要求改选第二家，与“选定即结束”冲突。另有 README 引用不存在的 `docs/testing.md`、`pytest -m live` 收集不到用例、`ref.md` 保留旧改选规则及旧版本号。

**建议：** 修复独立测试服务入口，更新结束规则的真实流程用例，并同步测试说明及设计文档，移除无效命令。

### R19〔低〕部分畸形历史游标会返回 500

**位置：** [repository.py:34](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/history/repository.py:34)。

**触发与影响：** 游标解码为 `[有效时间, 123]` 时，`UUID(123)` 抛出未捕获的 `AttributeError`，落入 500 处理，而不是预期的 `400 INVALID_CURSOR`。已复现仓储异常路径。

**建议：** 先验证解码结果的结构和字段类型，再校验时间及 UUID；所有无效游标统一返回输入错误。

### R20〔低／容量限制〕默认 Worker 串行执行，没有排队等待上限

**位置：** [service.py:29](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/task/service.py:29)、[runner.py:78](/Users/kakie/Resource/code/eat_what/src/backend/app/modules/decision/service/runner.py:78)。

**触发与影响：** 默认单进程只有一个 Worker，每次等待当前任务执行完才领取下一个。入队等待不计入推荐执行预算，页面也未区分排队和执行。假设 3 个后台任务各需 15 秒，第 3 个约 45 秒后才结束；这是代码路径推演，未做真实服务压测。

**建议：** 先显示排队状态并设置最长等待；有并发需求时再增加受限的执行并发，继续遵守上游配额。

## 本轮验证

| 检查 | 结果 |
| --- | --- |
| 后端 pytest 默认测试 | 61 通过，12 项集成测试默认排除 |
| PostgreSQL 集成测试 | 独立 `food_nav_test` 中 12 通过，临时 schema 已清理 |
| Ruff / mypy | 通过；mypy 检查 126 个源文件 |
| 前端 Vitest | 73 通过 |
| 业务及测试 TypeScript / ESLint / Vite build | 全部通过；构建仍有已有的主包大于 500 kB 和 Zod 注释警告 |
| 后端定向自检 | 11 组确认，包括实际数据库并发、金额精度、缓存覆盖及恢复预算 |
| 临时前端自检 | 10 项通过，确认表单、导航、账户切换和 SSE 时序问题 |
| 浏览器复核 | Playwright，桌面 1280×900、手机宽度 390×844；复现 R02、R03，无运行时异常或框架错误遮罩，无手机横向溢出 |
| 验收入口检查 | `tests.serve` 缺失；`pytest -m live --collect-only` 无用例，均已记入 R18 |
| 源码保护 | 校验 167 个源码、测试及迁移文件，本轮未改动；项目交付仅重写本报告 |

浏览器测试路径为：首页读取偏好失败 → 显示默认表单；首页编辑本次条件 → 保存账户偏好 → 返回首页确认草稿被清空。使用响应模拟，控制台唯一 HTTP 错误为预期注入的 `503`。当前未提供 Browser 插件，采用 Playwright（`Browser plugin not available`）。

临时复现脚本与截图位于 `/private/tmp/eat-what-review-20261016/`，未加入项目。现有测试通过不代表上述问题已修复；定向自检是确认缺陷的证据。

## 未覆盖范围

未调用真实高德或 LLM，未进行生产压力测试、超大密码哈希压测、Safari 或真实手机 GPS 验证。上游真实数据质量、响应时间及实际并发容量仍需单独验证。
