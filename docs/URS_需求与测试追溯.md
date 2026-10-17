# MethodFlow 用户需求规格（URS）与测试追溯

版本：V0.4　适用程序版本：MethodFlow 0.4.0（数据库结构版本 5）

> **重要声明**
> **本程序不是已验证的 GxP 系统：用于受监管用途须由企业 QA 按 CSV/GAMP 5 流程评估、补充 IQ/OQ/PQ、SOP、账号管理、备份与灾难恢复、电子签名法规符合性评估。**
> 本文件与 `自动化测试报告.md` 是开发方提供的“需求—测试”证据，只证明程序的核心规则在开发环境中按设计工作，**不等同于**企业的验证文件包，也不构成 21 CFR Part 11 / EU GMP Annex 11 的符合性声明。

## 1. 目的与范围

MethodFlow 是辅助分析方法开发（ICH Q14 / Q2(R2) 思路，对应 USP <1220> 生命周期的“设计”阶段）的轻量网页程序：阶段化管理、评审门复核、电子签名、审计追踪、附件、知识库、Word 方案/报告生成。范围外：验证、转移、持续监控阶段的数据管理，LIMS/ELN/CDS 功能，统计计算。

## 2. 追溯规则

- 自动测试位于 `tests\test_workflow.py`（URS-01 ~ 51 的核心规则）、`tests\test_hardening.py`（URS-80 ~ 97，后端加固：每条独立审查发现都有复现其场景的回归测试，场景脚本见 `docs\后端加固清单.md`）、`tests\test_projects.py`（URS-100 ~ 110：项目/方法分离、模板种子、知识库同步、旧库拒绝与迁移）和 `tests\test_templates.py`（URS-111：模板内容完整性，不需要数据库），**测试方法名中的 `URSnn` 即本表的 ID `URS-nn`**。各测试模块用各自的临时数据库（`config.set_data`），互不影响。
- 运行方式：`python -m unittest discover -s tests`，或 `python tools\run_tests_report.py`（同时生成 `docs\自动化测试报告.md`）。
- “验证方式”：**自动** = 有自动测试直接覆盖；**部分自动** = 自动测试只覆盖其中一部分，余下为人工；**人工** = 无自动测试，需按企业方案手工执行；**UI** = 只在浏览器界面体现，自动测试未覆盖（界面代码 `app\static\*` 没有单元/端到端测试）。
- 本表中“人工 / UI”项**尚无书面的人工测试记录**（除第 6 节注明的开发者手工检查），企业使用前须自行编写并执行 OQ 方案。

## 3. 需求与测试追溯表

### 3.1 账号与访问控制

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-01 | 口令策略与登录锁定：口令至少 `min_password_length` 位且含字母和数字；连续 `max_failed_logins` 次失败后账号锁定 `lock_minutes` 分钟，锁定期间即使口令正确也拒绝；口令以加盐 bcrypt 保存 | 部分自动 | `TestAuth.test_URS01_password_policy_and_lockout` | 自动测试覆盖弱口令拒绝与锁定；未测口令过期/历史（程序无此功能），bcrypt 存储为代码审查项 |
| URS-02 | 所有业务接口须有效会话，未登录返回 401 | 自动 | `TestAuth.test_URS02_session_required` | 仅抽测 `/api/dashboard`；其余接口通过统一的 `current_user` 调用，建议 OQ 逐个确认 |
| URS-03 | 防跨站请求：所有非 GET 的 `/api/` 请求必须带 `X-Requested-With: MethodFlow` 标头，否则 403；会话 Cookie 为 HttpOnly + SameSite=Lax | 部分自动 | `TestAuth.test_URS03_csrf_header_required` | Cookie 的 `HttpOnly`/`Max-Age`/`Secure` 见 URS-95（自动测试）；`Secure` 仅在监听地址非本机（或 `cookie_secure=true`）时设置，纯 HTTP 局域网部署须设 `cookie_secure=false` 或改用 HTTPS（见第 5 节） |
| URS-04 | 会话有绝对时长（`session_hours`）与空闲超时（`idle_minutes`）；退出登录使会话失效；停用账号或管理员重置口令时清除其会话 | 人工 | — | 无自动测试；时间类行为需 OQ 中用缩短的配置值手工验证 |
| URS-05 | 管理员可创建/停用账号、分配全局角色、重置口令（重置后须首次修改）；不能停用自己或移除自己的管理员角色 | 人工 / UI | — | `setUpModule` 间接创建了账号；权限边界无专项测试。“首次登录必须修改口令”现由 API 强制（URS-89，自动测试） |
| URS-06 | 全局审计查看与审计链校验仅限管理员/批准人；创建项目、新增方法、新增知识库条目限开发人员/管理员（见 URS-100/101） | 人工 | — | 无专项自动测试 |

### 3.2 评审门工作流与电子签名

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-10 | 阶段提交前，必填章节、必填检查项、必填表格最小行数须满足，否则拒绝提交（422）并列出阻断原因 | 自动 | `TestGateFlow.test_URS10_required_content_blocks_submission` | |
| URS-11 | 评审门流程：提交 → 复核（通过/退回）→ 退回须填原因 → 修改后再提交 → 通过后阶段锁定，锁定后任何编辑被拒（409）；退回产生新修订号；全部签名记录“完好” | 自动 | `TestGateFlow.test_URS11_review_reject_resubmit_approve_and_lock` | 同时覆盖签名口令错误时不产生签名（URS-19） |
| URS-12 | 职责分离（1）：编辑过某阶段内容（含该阶段实验/附件）的人，不得复核/批准该修订；若方法团队中没有符合条件的复核人则不能提交 | 自动 | `TestGateFlow.test_URS12_separation_of_duties` | 现以累计的“贡献者”（`contributors`：保存人、提交人、实验编辑人、附件上传/删除人，撤回/退回/重开不清除）判定，加固后的完整场景见 URS-80/81；本测试通过“无可用复核人”阻断来验证 |
| URS-13 | 职责分离（2）：作者（开发人员）不能在自己提交的评审门上签字 | 自动 | `TestGateFlow.test_URS13_author_cannot_sign_own_gate` | |
| URS-14 | 两步评审门（GP/G4/G5）：复核人先、批准人后；批准人不能抢先；同一人同一修订不得重复签署；两步均通过才“已通过” | 自动 | `TestGateFlow.test_URS14_two_step_gate_and_downstream_dependency` | |
| URS-15 | 阶段前置依赖：前置阶段未通过/完成（或已失效）时，后续阶段不能提交 | 自动 | `TestGateFlow.test_URS15_prerequisites_enforced` | 仅测“前置未通过”分支；“前置已失效”分支由 URS-18 间接覆盖 |
| URS-16 | FMEA 规则：RPN 达到 `rpn_threshold` 或严重度 S 达到 `severity_threshold` 的失效模式必须填写控制措施才能提交风险评估 | 自动 | `TestGateFlow.test_URS16_fmea_high_risk_requires_control` | 只测 S=9/RPN=270 一例；阈值可配置，修改后需重新确认 |
| URS-17 | 乐观并发：保存阶段内容须带版本号，版本落后返回 409，防止覆盖他人修改 | 自动 | `TestGateFlow.test_URS17_optimistic_concurrency` | 实验记录同样使用版本号，无专项测试 |
| URS-18 | 重新打开已通过阶段：须填原因 + 口令；其下游已通过阶段标记“已失效(stale)”，待复核的被退回；失效阶段须“重新提交复核”后恢复 | 自动 | `TestReopenAndStale.test_URS18_reopen_invalidates_dependents_and_recertify` | |
| URS-19 | 电子签名：每次签名/重新打开均需重新输入口令；签名记录含姓名、时间、含义、角色及与阶段数据绑定的 SHA-256 哈希；签名后数据被改变可被发现（`intact` 标志）；认证失败进入审计并计入锁定次数 | 部分自动 | `TestGateFlow.test_URS11_review_reject_resubmit_approve_and_lock`（口令错误→403、签名 `intact`）；`TestReopenAndStale.test_URS18_reopen_invalidates_dependents_and_recertify`（重新打开需口令/原因） | 签名绑定所见内容见 URS-86；“签名后篡改数据→`intact`=false”见 URS-83/85（自动测试）；“认证失败进入审计/计入锁定”仅 URS-89 对改口令的旧口令校验有测试 |

### 3.3 实验

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-20 | 实验规则：开发方案（plan）批准且未失效之前不得开始实验；完成实验须有结论；状态转换受限 | 自动 | `TestExperiments.test_URS20_experiments_need_approved_plan_and_conclusion` | 取消须原因、已开始实验不可删除等分支无专项测试 |
| URS-21 | 阶段提交时，其下登记的实验必须全部完成（有结论）或取消（有说明） | 自动 | `TestExperiments.test_URS21_stage_needs_all_experiments_closed` | |
| URS-22 | 阶段进入待复核/已通过后，其实验记录与附件被锁定 | 部分自动 | 附件锁定见 `TestAuditAndFiles.test_URS31_attachments_hash_and_lock`；实验与实验附件的锁见 URS-82（`TestExperimentLocks`，测试名以 URS82 编号，故报告的覆盖统计仍把 URS-22 列为无专名测试） | 删除附件、改派实验、`stage_key` 置空均不能绕过锁（自动测试）；实验字段编辑/状态变更在锁定阶段被拒的分支无专项测试 |

### 3.4 审计追踪与数据完整性

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-30 | 审计追踪只追加并形成哈希链；对任一记录的篡改可由“审计链校验”检出并定位首个异常记录 | 自动 | `TestAuditAndFiles.test_URS30_audit_chain_detects_tampering` | 检测不等于阻止（见第 5 节）。该测试故意篡改**临时库**（先 DROP 防篡改触发器），之后同模块内的链校验将失败；链的 HMAC、链头锚点、触发器见 URS-87 |
| URS-31 | 附件：保存时计算 SHA-256；下载内容与上传一致；磁盘文件被改后“校验完整性”失败；删除须原因（软删除）；阶段锁定后不能新增附件 | 自动 | `TestAuditAndFiles.test_URS31_attachments_hash_and_lock` | 软删除后磁盘文件保留 |
| URS-32 | 按成员资格控制访问：既不是方法成员也不是所属项目成员的人不能查看方法/项目（403），管理员可查看；项目成员可查看项目下全部方法（见 URS-102） | 自动 | `TestAuditAndFiles.test_URS32_access_control_between_projects` | 抽测方法详情、阶段详情、项目详情；其余接口统一调用 `require_view`/`require_view_project`，URS-102 逐接口覆盖项目成员的只读与不可写 |
| URS-33 | 所有写操作（保存、提交、签名、重开、实验、附件、用户、备份、文档生成）写入审计，含用户、时间、对象、变更前后值/原因 | 部分自动 | URS-30 的链有效性前提 | 未对每类操作逐一断言审计记录，须 OQ 补充 |

### 3.5 文档生成

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-40 | 生成《方法开发方案/报告》Word：含未通过/失效内容时标“草稿（含未复核内容）”（封面横幅与页眉），全部通过时标“已批准版本” | 自动 | `TestDocuments.test_URS40_document_draft_and_final_status` | 只检查文本标记与有效 docx；版面、签名页内容、甘特图/FMEA 图需人工目视 |
| URS-41 | 内置 7 种方法模板（流式、色谱、生物活性、qPCR/ddPCR、ELISA/SPR、细胞法功能/效力测定、通用）均能创建 9 阶段方法 | 自动 | `TestDocuments.test_URS41_all_templates_instantiate` | 只检查阶段数；预置内容见 URS-108/111；模板内容的科学性须由使用方评审 |
| URS-42 | Word 文档含文件控制表（内容哈希）、签名页（姓名/时间/含义/数据哈希）、附件清单、甘特图与 FMEA 图 | 人工 | — | 目视检查；图表依赖本机 matplotlib 与中文字体 |

### 3.6 知识库、备份与部署

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-50 | 知识库：按阶段/技术类型筛选推送；方法可沉淀“经验教训”并按关键字检索 | 自动 | `TestKbAndBackup.test_URS50_kb_filter_and_lessons` | |
| URS-51 | 备份：管理员可手动备份；程序启动时与每 24 小时自动备份；备份是可打开的 SQLite 文件；保留最近 `backup_keep` 份 | 部分自动 | `TestKbAndBackup.test_URS51_backup` | 自动测试只覆盖手动备份可生成且可读；定时备份与清理为人工/代码审查项 |
| URS-52 | 恢复：`tools\restore.py` 在服务器运行时拒绝；恢复前校验备份（完整性、结构版本、审计链）；先另存当前库；不改动 uploads/documents | 人工 | — | 2026-10-14 开发者在临时数据目录手工试跑通过（含“服务器运行→拒绝”“被篡改备份→拒绝”“正常恢复”），无正式记录 |
| URS-60 | 默认仅监听本机 `127.0.0.1`；局域网访问须显式配置 `host` | 人工 | — | 配置默认值为代码审查项；开放局域网时的 HTTPS/防火墙由部署方负责 |
| URS-61 | 数据持久化于 `data\`：SQLite（WAL）+ 附件文件 + 生成文档 + 备份；程序升级不改变数据（结构版本高于程序时拒绝启动） | 人工 | — | 旧库（项目 = 方法，结构版本 1/2）拒绝启动与迁移见 URS-106（自动测试）；结构版本 3 以后的原地升级框架（`db.MIGRATIONS`）尚无实例 |
| URS-70 | 界面：中文网页单页应用，离线可用（不依赖 CDN）；工作台、项目与方法列表/总览、阶段编辑、实验、文档、审计、知识库、管理页 | UI | — | 无自动化 UI 测试；须按企业方案在目标浏览器上手工测试 |

### 3.7 后端加固（独立审查 + 运维检查发现；清单见 `后端加固清单.md`）

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-80 | 方法团队与职责分离（H1，现按方法计）：方法角色须匹配全局角色（负责人/开发人员需全局开发人员或管理员，复核人/批准人需对应全局角色）；同一人不得同时担任编辑类（负责人/开发人员）与签署类（复核人/批准人）角色，复核人与批准人不得为同一人；有阶段待复核时不得增删复核人/批准人；非法成员列表一律 400 | 自动 | `TestSeparationOfDuties.test_URS80_project_roles_must_match_global_roles_and_not_mix`；`..._set_members_same_rules_and_frozen_while_in_review` | 运行期还要求签署人当前仍具备相应全局角色；管理员事后改全局角色不会自动改方法团队。方法团队成员另须是所属项目成员（URS-103） |
| URS-81 | 累计贡献者（H1）：保存人、提交人、实验编辑人、实验附件上传/删除人都计入阶段的 `contributors`，撤回/退回/重开/修订号递增均不清除；贡献者永远不能复核/批准该阶段 | 自动 | `test_URS81_contributors_are_cumulative_across_withdraw_and_role_changes`；`..._submitter_who_never_saved_is_a_contributor`；`..._experiment_and_experiment_attachment_work_counts_for_the_stage` | 旧库转换时 `contributors` 由已有的编辑者和提交人回填，更早的历史无从得知 |
| URS-82 | 实验与附件不绕过阶段锁（H2）：实验一旦分配阶段不可置空；改派的目标阶段须存在且可编辑；删除附件同时检查其实验所在阶段的锁；锁定阶段的编辑者/贡献者列表不被改写 | 自动 | `TestExperimentLocks.test_URS82_stage_key_cannot_be_cleared_or_moved_into_locked_stage`；`..._delete_attachment_checks_the_experiment_lock` | |
| URS-83 | 签名哈希覆盖范围（H3）：阶段哈希含该阶段实验（编号/名称/目的/设计/接受标准，非方案阶段另含结果/结论/偏离/状态）及附件 SHA-256；GP 哈希含批准时点已存在、未标记追加的全部实验；方案提交/批准后方案内实验的名称/目的/设计/接受标准/所属阶段冻结（409）、不可删除；之后新增的实验标记 `added_after_plan`，不影响 GP 哈希，文档中单列“方案外追加”；方案提交/批准后新增实验必须填写设计和接受标准（否则 400，避免方案阶段无法重新复核） | 自动 | `TestSignatureCoverage.test_URS83_plan_experiments_frozen_after_approval_and_late_ones_flagged`；`..._experiment_added_after_the_plan_needs_design_and_acceptance`；`..._signed_hash_covers_experiments_and_attachments` | 由旧库转换而来的已批准阶段的旧哈希（hv=1/2）继续用旧算法验证，其实验/附件不在覆盖范围内，须重开重批才获得新覆盖 |
| URS-84 | 元数据覆盖（H3/L14，现按方法/项目计）：方法的 `name/analyte/matrix/intended_use` 与所属项目的 `product` 并入立项阶段及覆盖它的评审门的哈希（hv=3）；任一阶段已批准/完成后方法的这四项以及所属项目的 `product` 不可改（409）；项目其余字段（名称、适应症、阶段、说明、日期、状态）和方法的 `phase`/`method_version`/日期不在哈希内，可改 | 自动 | `TestSignatureCoverage.test_URS84_method_metadata_frozen_after_approval_and_covered_by_hash` | 项目的 `product` 一经任一方法的阶段批准即冻结，项目负责人如需更正须先重新打开相应阶段；直接改库（方法或项目）会使签名 `intact` 失效 |
| URS-85 | 篡改检测（H4）：评审记录的 `intact` = 当前修订按提交时的算法重算哈希与签名哈希相符，历史修订对照只追加的快照表；阶段详情返回 `signatures_ok`；任一已批准阶段签名失败时生成的 Word 标“完整性校验失败”（封面红字、页眉）而不是“已批准版本”；`/api/audit/verify` 返回 `signatures_ok`/`bad_signatures`；方法详情、导出、文档列表一并返回 | 自动 | `TestTamperDetection.test_URS85_intact_flag_documents_and_audit_verify_detect_tampering`；`..._history_is_checked_against_the_snapshot_table` | 失效（stale）阶段只核对快照，不重算（其内容依赖的上游已改变，属预期） |
| URS-86 | 签名绑定所见内容（H5）：`POST .../review` 必须带 `revision` 与 `expected_hash`（阶段详情的 `revision`、`hash`）；缺失或类型错误 400；与事务内当前值不符 409“内容已更新，请刷新后重新审阅”；先于口令认证校验 | 自动 | `TestTamperDetection.test_URS86_signature_is_bound_to_what_the_reviewer_saw` | 接口不向后兼容旧前端（有意） |
| URS-87 | 审计与证据表防篡改（M1/L6）：audit_log、stage_revisions、reviews 禁止 UPDATE/DELETE（触发器）；审计链为 HMAC-SHA256（密钥 `data\.audit_key`，首次启动随机生成），记录体含 `project_id` 与 `method_id`（hv=3）；链头（id、记录数、哈希、MAC）写入 `data\audit_head.json` 并写入每份备份的旁注文件；校验要求链头记录仍在链中且记录数不少于锚点；锚点文件缺失/被改均报告，不被自动重建 | 自动 | `TestAuditProtection.test_URS87_append_only_triggers`；`..._keyed_chain_rewrite_truncation_and_anchor`；另见 URS-106（旧链 hv=1/2 转换后继续验证）、URS-110（改写 `method_id` 被检出） | 同时取得密钥文件和数据库写权限者仍可伪造整条链并同步锚点——密钥文件与备份须由 IT 另行保管；`tools\audit_anchor.py --reset` 仅在链本身通过校验时重建锚点 |
| URS-88 | 状态（M2）：方法**或其所属项目**非“进行中”时，所有写操作（保存、提交、撤回、复核、重开、实验增改删/状态、附件上传删除、团队调整、新增方法）一律被拒（409）；由暂停/完成/归档/取消恢复为进行中须原因 + 口令重新认证（方法与项目均如此）；`update_method`/`update_project` 校验字段类型与非空、日期先后 | 自动 | `TestProjectStatus.test_URS88_nothing_can_be_written_in_a_non_active_method`；`..._a_non_active_project_blocks_writes_to_its_methods`；`..._reactivating_needs_reason_and_password`；`..._update_method_validates_fields`；`..._update_project_validates_fields` | 生成文档、登记经验教训、变更生命周期在非进行中状态仍允许（开发完成后出终稿、转入验证的合理需要）|
| URS-89 | 强制改口令（M3）：`must_change` 用户只能调用 `/api/me`、`/api/me/password`、`/api/logout`，其余 403 `{"error":"须先修改密码","must_change":true}`；改口令后删除该用户其他会话；改口令时的旧口令校验计入失败次数与锁定并写审计 | 自动 | `TestAccounts.test_URS89_must_change_is_enforced_by_the_api`；`..._change_password_counts_failures_and_locks` | |
| URS-90 | 登录（M4/L13）：未知用户也做一次 bcrypt 比对；未知用户、错口令、停用账号的错口令返回同一 401 文字；锁定（含对不存在用户名的同样“伪锁定”）返回同一 423 通用文字，即使口令正确；停用账号仅在口令正确时才提示；按（用户名，来源 IP）每分钟失败次数限速（429）；未知用户的失败审计按用户名在锁定窗口内去重；登录时清理过期会话 | 自动 | `TestAccounts.test_URS90_login_does_not_reveal_which_accounts_exist`；`..._rate_limit_and_audit_dedupe_for_unknown_names`；`..._login_clears_expired_sessions` | 限速与伪锁定状态在进程内存中，重启后清零；反向代理后所有请求来源 IP 相同 |
| URS-91 | 上传（M5）：端点流式写入临时文件并边写边算 SHA-256；读取请求体之前先校验成员、编辑权限、阶段锁与 `Content-Length`；超过 `max_upload_mb` 即中止并清理；全局请求体上限（JSON 接口 `max_json_mb` = 20 MB）；认证不在事件循环上阻塞；已存在的文件不被覆盖（内容不符时另存） | 自动 | `TestUploads.test_URS91_upload_checks_before_reading_and_enforces_limits`；`..._upload_endpoint_is_streaming_and_does_not_block_the_event_loop`；`..._existing_file_is_never_overwritten` | 无病毒扫描、无文件类型白名单 |
| URS-92 | 备份（M6）：备份后 `PRAGMA integrity_check`，不通过则标记 `.corrupt` 并报错；启动备份与每日/手动备份分开保留（`backup_keep_startup`/`backup_keep`）；每份备份旁写 `.manifest.json`（数据库完整性、结构版本、审计链头、uploads/documents 文件 SHA-256 清单）；`tools\restore.py` 比对旁注链头与文件清单并重建锚点；`tools\backup.py --files` 仍可用 | 自动 | `TestBackups.test_URS92_backup_is_checked_and_comes_with_a_manifest`；`..._startup_and_daily_backups_are_retained_separately`；`..._backup_that_fails_integrity_check_is_rejected`；`..._backup_tool_with_files_still_works`；另见 URS-96 的还原工具测试 | 备份与数据仍在同一磁盘；`.audit_key` 不在 .db 备份内，须随备份另行保管；自动备份不含 uploads/documents 本体 |
| URS-93 | 文档生成稳健（M7）：去除 XML 非法控制字符；矩阵权重/得分容错；FMEA S/O/D 保存时规范为 1–10 的整数，异常值拒绝（400）；图表用 `matplotlib.figure.Figure`（非 pyplot）；渲染在任何写事务之外，提交前复核数据未变（否则 409）；每方法每分钟最多 `docs_per_minute` 份 | 自动 | `TestDocuments.test_URS93_documents_survive_control_characters_and_junk_numbers`；`..._fmea_scores_are_validated_on_save`；`..._charts_use_the_figure_api_not_pyplot`；`..._rendering_does_not_hold_the_database_write_lock`；`..._parallel_generation_in_two_projects`（两个方法并行） | 超出 1–10 的 S/O/D 被拒绝而不是被静默夹取（静默改写用户输入不符合数据完整性原则）；版面仍须人工目视 |
| URS-94 | 输入校验与统一错误（M8/L1/L5）：按章节定义校验 text/fields/table/matrix/fmea 结构与类型，检查项、实验字段、成员、项目字段、用户字段、知识库字段同；全局异常处理器把 TypeError/ValueError/AttributeError/KeyError/OverflowError 与请求格式错误转为 400 JSON，其他内部错误 500 JSON，均不泄露堆栈；旧数据（校验前存入的畸形内容）不会使阶段/项目/工作台/文档 500 | 自动 | `TestValidation.test_URS94_malformed_sections_are_rejected_and_never_brick_the_stage`；`..._data_stored_before_validation_existed_cannot_brick_the_stage`；`..._bad_requests_get_400_json_never_500_or_a_stack_trace` | 文本章节上限 50 万字符，单元格 1 万字符，表格 500 行 |
| URS-95 | 其他加固：实验 `owner_id` 须为方法团队成员（L2）；`limit` 夹到 [1, 2000]（L3）；失效沿依赖传递闭包传播（L4）；Cookie `Max-Age`、非本机监听时 `Secure`、CSP、Host 头校验与 `allowed_hosts`（L7）；`/api/users` 对非管理员只返回在用账号（L9）；认证用只读连接且 `last_seen` 超过 60 s 才写（L10）；生成文档需方法的负责人/开发人员/复核人/批准人或管理员（仅项目成员不可），并按方法限速（L11） | 自动 | `TestMisc` 中 `test_URS95_*` 共 7 项 | `/api/users` 仍含用户名（前端依赖）；Host 校验在局域网部署默认放行任意主机名，须配置 `allowed_hosts` 才限制 |
| URS-96 | 运维：`setup_token`（配置了则初始化必须提供）；离线重置管理员口令 `tools\reset_admin.py`（须停服务，随机临时口令，强制改口令，写审计）；审计锚点工具 `tools\audit_anchor.py`；`tools\restore.py` 的旁注比对与重建锚点 | 自动 | `TestOperations.test_URS96_setup_token`；`..._reset_admin_tool`；`..._audit_anchor_tool_rebuilds_a_lost_anchor_only_for_a_valid_chain`；`..._restore_tool_checks_the_manifest_and_reanchors` | 工具以操作系统文件权限为信任基础：能运行它们的人即能重置管理员口令，这一动作会留下审计记录 |
| URS-97 | 接口修正：上传文件名只解码一次（含 `%` 的文件名不被破坏）；工作台“我的实验”条目的 `code` 为实验编号、`method_code` 为方法编号、`project_code` 为项目编号 | 自动 | `TestUploads.test_URS97_filenames_are_not_decoded_twice`；`TestMisc.test_URS97_dashboard_experiment_entries_keep_experiment_and_method_codes_apart` | |

### 3.8 项目 / 方法分离、模板与知识库同步（V0.2 新增；`tests\test_projects.py`、`tests\test_templates.py`）

| ID | 需求 | 验证方式 | 自动化测试 | 说明与局限 |
|---|---|---|---|---|
| URS-100 | 项目（Project）：编号 `PRJ-YYYY-NNN`，含名称、产品、适应症、阶段、说明、起止日期、状态（进行中/暂停/完成/归档）、项目负责人与项目团队（owner/member/viewer，一人一个角色）；全局开发人员/管理员可新建，创建者自动为负责人；仅负责人可改信息与调整团队（负责人须具备全局开发人员/管理员角色，至少保留一名）；列表/详情仅对项目成员和管理员可见；改为“完成”要求项目下没有进行中的方法；恢复为进行中须原因 + 口令；仍在方法团队中的人不能移出项目 | 自动 | `TestProjects.test_URS100_project_crud_team_and_codes`；`..._project_team_rules`；`..._project_status_rules` | 项目团队只管“能否看到并创建方法”，不授予任何方法内的编辑/签署权 |
| URS-101 | 新增方法：须是该项目的负责人或成员（项目只读成员、非成员不可）且全局角色含开发人员（或管理员且为项目成员）；创建者自动成为方法负责人 + 开发人员；编号 `AM-YYYY-NNN`（全局序号）；项目须进行中；模板、日期、团队等输入校验 | 自动 | `TestMethods.test_URS101_method_creation_requires_project_membership_and_author_role` | |
| URS-102 | 查看权限继承：方法可被方法成员、所属项目的任意成员和管理员查看（阶段、实验、附件、审计、知识、文档、导出、列表、工作台）；编辑与签署只取决于方法角色——仅项目成员不能保存/提交/上传/登记实验/生成文档/调整团队/变更生命周期/签署；非成员一概 403 | 自动 | `TestMethods.test_URS102_view_is_inherited_from_the_project_but_edit_and_sign_are_not` | |
| URS-103 | 方法团队成员必须是所属项目成员（管理员除外），在创建方法和调整团队时均校验；方法负责人或项目负责人可调整方法团队（项目负责人不因此获得编辑权），至少一名方法负责人 | 自动 | `TestMethods.test_URS103_method_team_members_must_belong_to_the_project` | 职责分离、全局角色匹配、待复核时冻结签署人等规则沿用（URS-80） |
| URS-104 | 克隆方法到同一项目或另一项目（目标项目权限同新增方法）：复制章节内容，检查清单重置，不复制签名/团队/实验结果，写审计 | 自动 | `TestMethods.test_URS104_clone_a_method_into_the_same_or_another_project` | |
| URS-105 | 生命周期（开发/验证/转移/常规使用/停用）由方法负责人或批准人变更，须原因 + 口令重新认证，写审计（含变更前后值与原因），在任何开发状态下都允许；不能通过一般字段修改 | 自动 | `TestMethods.test_URS105_lifecycle_change_is_audited_and_needs_reason_and_password` | V0.2 只有开发流程；其余生命周期阶段仅作状态字段，无流程 |
| URS-106 | 旧库（项目 = 方法，结构版本 1/2，或有表但无版本号）拒绝启动：不改动数据、不创建密钥，给出备份并删除/迁移的清晰提示，Web 应用启动同样失败；`tools\migrate_v1_to_v2.py` 把每个旧项目转换为一个方法并自动建同名项目，保留签名（旧哈希公式 hv=1/2 继续验证）、保留审计链（旧记录原样，追加一条 `schema.migrate`），原库另存为 `premigrate_*.db`；服务器运行时拒绝 | 自动 | `TestOldDatabases.test_URS106_old_databases_are_refused_with_a_clear_message`；`..._migration_tool_converts_a_version_1_database`；`..._migration_tool_converts_a_version_2_database_and_keeps_the_keyed_chain`；`..._migration_tool_refuses_running_servers_and_unknown_databases` | 仅验证了测试夹具构造的小库；真实库转换前须先备份（工具自动备份）并核对方法/签名数；旧项目的 `product` 变成项目的产品，旧 `attribute` 变成方法的“被测属性”，样品基质留空 |
| URS-107 | 列表与工作台形状：`GET /api/dashboard`（projects/methods/to_review/my_stages/my_experiments，条目含 method_id/method_code/method/project_code）、`GET /api/methods` 的 q/status/project_id/technique/lifecycle 筛选、`GET /api/projects/{pid}/methods`、方法详情（含 project 摘要与 permissions） | 自动 | `TestMethods.test_URS107_dashboard_and_method_list_shapes_and_filters`；`..._method_detail_carries_project_and_permissions` | 字段清单见 `前端契约.md`；界面未自动化测试 |
| URS-108 | 模板预置进入方法：新建方法时每个带 `seed_rows` 的表格、带 `default` 的文本按模板预置，FMEA/ATP/SST/实验种子照旧（7 个模板逐一检查）；`plan`/`report` 阶段在数据或实验接受标准仍含“示例值，须按ATP确认”时给出警告（不阻断提交），确认后警告消失，已取消的实验不计 | 自动 | `TestTemplatesInMethods.test_URS108_template_seeds_reach_new_methods`；`..._unconfirmed_example_values_warn_but_do_not_block` | 警告只是提示：程序不判断示例值是否合理，须由使用方专家确认 |
| URS-109 | 内置知识库同步：启动时与管理员接口 `POST /api/admin/kb-sync` 按标题补充缺失的内置条目；用户创建/编辑/已停用的条目不被覆盖或恢复；重复执行无变化；写审计 `kb.sync`；非管理员 403 | 自动 | `TestKnowledgeBaseSync.test_URS109_kb_sync_adds_missing_builtin_items_and_never_overwrites` | 以标题为键：内置条目改标题后会被视为新条目 |
| URS-110 | 项目级审计聚合：`GET /api/projects/{pid}/audit` 返回项目本身及其全部方法的记录（不含其他项目），每条审计记录同时带 `project_id` 与 `method_id`（均参与链哈希，改写被链校验检出）；权限同可见性 | 自动 | `TestProjects.test_URS110_project_audit_aggregates_its_methods_and_records_both_keys` | |
| URS-111 | 模板内容完整性（模板 1.1）：7 个技术、9 阶段 key/评审门不变、章节 key 唯一、章号稳定唯一、表格种子行与列一致、每技术 FMEA ≥10 / 实验 ≥8 / SST ≥4、占位与帮助、必填比例、无无法核对的条款号、知识库新增写作指南/常见缺陷条目 ≥30 条且来源/类型合规 | 自动 | `tests\test_templates.py` 中 `TestTemplates.test_URS111_*` 共 10 项 | 只检查结构与合规性，**科学内容未经评审**（见第 5 节） |


### 3.9 审批级文档导出：模板驱动、受控文件外观、Word + PDF（V0.4 新增；`tests\test_docgen.py`）

| 编号 | 需求 | 验证方式 | 对应自动测试 | 备注 |
|---|---|---|---|---|
| URS-120 | 章节驱动渲染：方案 15 章 / 报告 21 章按 `template.doc_structure` 与各章节 `ch[kind]` 输出“n  标题”“n.m  标题”，自动块（实验清单 11.3/12.3、实验结果 13.4、甘特图 14.1 后、签署页 15/21.2）插在对应章；不输出阶段标题、阶段状态行与给编辑者看的阶段说明 | 自动 | `TestChapterDrivenLayout.test_URS120_plan_follows_the_template_structure_and_hides_editor_text` / `test_URS120_report_has_21_chapters_and_result_block` | 只检查章节标题与文本，不检查页面外观（外观见第 6 节的目视检查） |
| URS-121 | 草稿标记：空的必填章节以红色高亮“【待填写】”，选填空章节写“（未填写）”；仍带“示例值，须按ATP确认”标记的内容在草稿中黄底红字高亮；草稿页眉红色“草稿—不得作为批准文件使用”；已批准版本无任何草稿标记 | 自动 | `test_URS121_empty_required_sections_and_example_values_are_flagged_in_drafts` / `test_URS121_final_documents_have_no_draft_marks` | 示例标记只靠文本匹配，不能判断数值是否合理（见第 5 节第 17 条） |
| URS-122 | 表格版式：固定布局并写明 tblW / tblGrid / tcW（LibreOffice 与 Word 均按列宽显示），表头行跨页重复，≥ 9 列的表（FMEA）与实验清单、签署页使用横向小节，数字列右对齐、日期列居中 | 自动 | `test_URS122_tables_use_fixed_layout_with_explicit_grid_and_repeat_headers` | 列宽是否“好看”靠目视检查 |
| URS-123 | `fields` 章节：textarea 字段按行分段；报告“结论性意见”渲染为按结论着色的摘要横幅 | 自动 | `test_URS123_fields_textarea_and_verdict_banner` | |
| URS-124 | 附录：A 检查清单含依据与指引，B 附件清单（SHA-256 前 12 位），C 引用依据含参考文件表（`refdocs`）与检查项引用条款 | 自动 | `test_URS124_appendices_show_guidance_refs_and_reference_documents` | 条款引用是否正确不由程序核对 |
| URS-125 | 旧模板创建的阶段定义（没有 `ch`）按当前模板的同名章节定位，不丢章节；无法定位且有内容的章节列入附录 D | 自动 | `test_URS125_legacy_stage_definitions_without_ch_are_still_placed` | |
| URS-126 | 受控文件外观：页眉（公司名称、文件名称、文件编号 `[前缀]方法编号-PLAN/RPT-Vn`、版本、状态）、页脚（配置文字、第 X 页/共 Y 页、生成时间）、封面编制/复核/批准姓名与日期表（取自电子签名记录）、修订历史（文档版本 + 阶段提交 + 评审退回 + 重新打开/撤回原因）、Word TOC 字段（含超链接与页码域）、每个评审门一张签署表（角色/姓名/含义/日期时间/修订号/哈希前 12 位/完整性） | 自动 | `TestControlledDocument.test_URS126_cover_signature_page_revision_history_and_toc` | 未用 Microsoft Word 打开验证（只用 python-docx、LibreOffice 与 XML 次序检查） |
| URS-127 | 签名完整性失败：封面横幅、页眉红字“完整性校验失败—不得作为批准文件使用”、签署页对应行标红，文档状态为“完整性校验失败” | 自动 | `test_URS127_integrity_failure_is_shown_everywhere` | 与 URS-85 配合 |
| URS-128 | 系统设置：`GET/PUT /api/admin/settings`（仅管理员；公司名称、页脚文字、文件编号前缀、soffice 路径；类型/长度/字符校验，soffice 路径须是存在的 soffice 程序；修改写审计 `settings.update`），设置影响文件编号、页眉、页脚 | 自动 | `TestControlledDocument.test_URS128_document_number_prefix_company_and_footer_come_from_settings` / `TestSettingsAndCapabilities.test_URS128_settings_api_validation_permissions_and_audit` / `test_URS128_soffice_path_accepts_an_existing_soffice` | 最后一项需已安装 LibreOffice，否则跳过 |
| URS-129 | 一次生成同时产出 `.docx` 与 `.pdf`（LibreOffice `soffice --headless --convert-to pdf`，私有用户配置目录 + 超时；先查设置/config.json 路径、再 PATH、再默认安装目录）；每种格式一行 `generated_docs`（共享 `gen_id`，记录文件 SHA-256）；无 LibreOffice / 转换失败 / 超时只产出 Word 并返回 `pdf_available=false` 与说明；`GET /api/system/capabilities` 任何登录用户可查；目录页码经两遍转换写入 | 自动 | `TestSettingsAndCapabilities.test_URS129_capabilities_for_any_logged_in_user` / `TestPdfOutput.test_URS129_without_libreoffice_only_word_is_produced_and_nothing_crashes` / `test_URS129_conversion_failure_and_timeout_are_reported_not_raised` / `test_URS129_word_and_pdf_are_produced_together` | 末项需已安装 LibreOffice，否则跳过；目录页码回填需要 `pypdf` 或 PyMuPDF，否则 PDF 目录无页码 |
| URS-93（延续） | 生成过程中数据变化 409 并清理已写出的文件；频率限制按“次生成”（每种格式不重复计）；其余模板（hplc/cell_based/generic）方案 15 章、报告 21 章均可生成 | 自动 | `TestHardeningStillHolds.test_URS93_*`（3 项） | |

## 4. 追溯矩阵（测试 → 需求）

| 自动测试 | 需求 |
|---|---|
| `TestAuth.test_URS01_password_policy_and_lockout` | URS-01 |
| `TestAuth.test_URS02_session_required` | URS-02 |
| `TestAuth.test_URS03_csrf_header_required` | URS-03 |
| `TestGateFlow.test_URS10_required_content_blocks_submission` | URS-10 |
| `TestGateFlow.test_URS11_review_reject_resubmit_approve_and_lock` | URS-11，URS-19（部分） |
| `TestGateFlow.test_URS12_separation_of_duties` | URS-12 |
| `TestGateFlow.test_URS13_author_cannot_sign_own_gate` | URS-13 |
| `TestGateFlow.test_URS14_two_step_gate_and_downstream_dependency` | URS-14 |
| `TestGateFlow.test_URS15_prerequisites_enforced` | URS-15 |
| `TestGateFlow.test_URS16_fmea_high_risk_requires_control` | URS-16 |
| `TestGateFlow.test_URS17_optimistic_concurrency` | URS-17 |
| `TestReopenAndStale.test_URS18_reopen_invalidates_dependents_and_recertify` | URS-18，URS-19（部分） |
| `TestExperiments.test_URS20_experiments_need_approved_plan_and_conclusion` | URS-20 |
| `TestExperiments.test_URS21_stage_needs_all_experiments_closed` | URS-21 |
| `TestAuditAndFiles.test_URS30_audit_chain_detects_tampering` | URS-30 |
| `TestAuditAndFiles.test_URS31_attachments_hash_and_lock` | URS-31，URS-22（部分） |
| `TestAuditAndFiles.test_URS32_access_control_between_projects` | URS-32，URS-102（部分） |
| `TestDocuments.test_URS40_document_draft_and_final_status` | URS-40 |
| `TestDocuments.test_URS41_all_templates_instantiate` | URS-41，URS-108（部分） |
| `TestKbAndBackup.test_URS50_kb_filter_and_lessons` | URS-50 |
| `TestKbAndBackup.test_URS51_backup` | URS-51 |

`tests\test_hardening.py`（类名.方法名；方法名中的 URS 编号即主要对应的需求，其余为部分覆盖）：

| 自动测试 | 需求 |
|---|---|
| `TestSeparationOfDuties.test_URS80_project_roles_must_match_global_roles_and_not_mix` / `test_URS80_set_members_same_rules_and_frozen_while_in_review` | URS-80 |
| `TestSeparationOfDuties.test_URS81_contributors_are_cumulative_across_withdraw_and_role_changes` / `test_URS81_submitter_who_never_saved_is_a_contributor` / `test_URS81_experiment_and_experiment_attachment_work_counts_for_the_stage` | URS-81，URS-12 |
| `TestExperimentLocks.test_URS82_stage_key_cannot_be_cleared_or_moved_into_locked_stage` / `test_URS82_delete_attachment_checks_the_experiment_lock` | URS-82，URS-22 |
| `TestSignatureCoverage.test_URS83_plan_experiments_frozen_after_approval_and_late_ones_flagged` / `test_URS83_experiment_added_after_the_plan_needs_design_and_acceptance` / `test_URS83_signed_hash_covers_experiments_and_attachments` | URS-83，URS-19 |
| `TestSignatureCoverage.test_URS84_method_metadata_frozen_after_approval_and_covered_by_hash` | URS-84 |
| `TestTamperDetection.test_URS85_intact_flag_documents_and_audit_verify_detect_tampering` / `test_URS85_history_is_checked_against_the_snapshot_table` | URS-85，URS-19 |
| `TestTamperDetection.test_URS86_signature_is_bound_to_what_the_reviewer_saw` | URS-86 |
| `TestAuditProtection.test_URS87_append_only_triggers` / `test_URS87_keyed_chain_rewrite_truncation_and_anchor` | URS-87，URS-30 |
| `TestProjectStatus.test_URS88_nothing_can_be_written_in_a_non_active_method` / `test_URS88_a_non_active_project_blocks_writes_to_its_methods` / `test_URS88_reactivating_needs_reason_and_password` / `test_URS88_update_method_validates_fields` / `test_URS88_update_project_validates_fields` | URS-88 |
| `TestAccounts.test_URS89_must_change_is_enforced_by_the_api` / `test_URS89_change_password_counts_failures_and_locks` | URS-89，URS-05（部分） |
| `TestAccounts.test_URS90_login_does_not_reveal_which_accounts_exist` / `test_URS90_rate_limit_and_audit_dedupe_for_unknown_names` / `test_URS90_login_clears_expired_sessions` | URS-90，URS-01 |
| `TestUploads.test_URS91_upload_checks_before_reading_and_enforces_limits` / `test_URS91_upload_endpoint_is_streaming_and_does_not_block_the_event_loop` / `test_URS91_existing_file_is_never_overwritten` | URS-91，URS-31 |
| `TestBackups.test_URS92_backup_is_checked_and_comes_with_a_manifest` / `test_URS92_startup_and_daily_backups_are_retained_separately` / `test_URS92_backup_that_fails_integrity_check_is_rejected` / `test_URS92_backup_tool_with_files_still_works` | URS-92，URS-51 |
| `TestDocuments.test_URS93_documents_survive_control_characters_and_junk_numbers` / `test_URS93_fmea_scores_are_validated_on_save` / `test_URS93_charts_use_the_figure_api_not_pyplot` / `test_URS93_rendering_does_not_hold_the_database_write_lock` / `test_URS93_parallel_generation_in_two_projects` | URS-93，URS-40 |
| `TestValidation.test_URS94_malformed_sections_are_rejected_and_never_brick_the_stage` / `test_URS94_data_stored_before_validation_existed_cannot_brick_the_stage` / `test_URS94_bad_requests_get_400_json_never_500_or_a_stack_trace` | URS-94 |
| `TestMisc.test_URS95_experiment_owner_must_be_a_project_member` / `test_URS95_audit_limit_is_clamped` / `test_URS95_staleness_propagates_transitively` / `test_URS95_cookie_csp_and_host_header` / `test_URS95_user_list_hides_inactive_accounts_from_ordinary_users` / `test_URS95_authentication_reads_without_the_write_lock_and_throttles_last_seen` / `test_URS95_document_generation_needs_edit_or_review_role_and_is_rate_limited` | URS-95，URS-03（部分），URS-04（部分，空闲超时），URS-18（传递失效） |
| `TestOperations.test_URS96_setup_token` / `test_URS96_reset_admin_tool` / `test_URS96_audit_anchor_tool_rebuilds_a_lost_anchor_only_for_a_valid_chain` / `test_URS96_restore_tool_checks_the_manifest_and_reanchors` | URS-96，URS-52（部分） |
| `TestUploads.test_URS97_filenames_are_not_decoded_twice` / `TestMisc.test_URS97_dashboard_experiment_entries_keep_experiment_and_method_codes_apart` | URS-97 |

`tests\test_projects.py` 与 `tests\test_templates.py`：

| 自动测试 | 需求 |
|---|---|
| `TestProjects.test_URS100_project_crud_team_and_codes` / `test_URS100_project_team_rules` / `test_URS100_project_status_rules` | URS-100，URS-06（部分） |
| `TestMethods.test_URS101_method_creation_requires_project_membership_and_author_role` | URS-101，URS-06（部分） |
| `TestMethods.test_URS102_view_is_inherited_from_the_project_but_edit_and_sign_are_not` | URS-102，URS-13（部分），URS-32 |
| `TestMethods.test_URS103_method_team_members_must_belong_to_the_project` | URS-103，URS-80（部分） |
| `TestMethods.test_URS104_clone_a_method_into_the_same_or_another_project` | URS-104 |
| `TestMethods.test_URS105_lifecycle_change_is_audited_and_needs_reason_and_password` | URS-105，URS-19（部分） |
| `TestOldDatabases.test_URS106_old_databases_are_refused_with_a_clear_message` / `test_URS106_migration_tool_converts_a_version_1_database` / `test_URS106_migration_tool_converts_a_version_2_database_and_keeps_the_keyed_chain` / `test_URS106_migration_tool_refuses_running_servers_and_unknown_databases` | URS-106，URS-61（部分），URS-87（部分） |
| `TestMethods.test_URS107_dashboard_and_method_list_shapes_and_filters` / `test_URS107_method_detail_carries_project_and_permissions` | URS-107 |
| `TestTemplatesInMethods.test_URS108_template_seeds_reach_new_methods` / `test_URS108_unconfirmed_example_values_warn_but_do_not_block` | URS-108，URS-41 |
| `TestKnowledgeBaseSync.test_URS109_kb_sync_adds_missing_builtin_items_and_never_overwrites` | URS-109，URS-50（部分） |
| `TestProjects.test_URS110_project_audit_aggregates_its_methods_and_records_both_keys` | URS-110，URS-30（部分），URS-87（部分） |
| `TestTemplates.test_URS111_*`（10 项） | URS-111 |
| `TestChapterDrivenLayout.*`（URS120 ×2、URS121 ×2、URS122、URS123、URS124、URS125） | URS-120 ~ 125 |
| `TestControlledDocument.*`、`TestSettingsAndCapabilities.*`、`TestPdfOutput.*` | URS-126 ~ 129 |
| `TestHardeningStillHolds.*`（3 项） | URS-93（部分） |

无自动测试覆盖（仅人工/UI）：URS-04、05、06、42、52、60、61、70（其中 04、05、52、61 在上表被个别测试部分触及，但没有以其编号命名的测试，故报告的“无自动测试”清单仍会列出它们）。

## 5. 已知缺口与局限（如实列出）

下列事项是**程序当前的真实局限**，用于受监管用途前须由企业评估并以流程、技术措施或二次开发补足。

**身份与访问**
1. 仅本地账号（口令 + bcrypt）；无 SSO/AD/LDAP 集成，无多因素认证，无口令过期/历史/复杂度策略（仅长度 + 字母 + 数字）。
2. （已在后端加固中解决，URS-89）“首次登录必须修改口令”现由 API 强制；剩余局限：口令策略仍只有长度 + 字母 + 数字。
3. （已解决，URS-80/81/103）方法角色须匹配被指派者的全局角色，方法团队成员须是所属项目成员，且同一人不得同时拥有编辑类与签署类角色。剩余局限：管理员事后修改某人的全局角色不会自动调整其已有的方法/项目成员身份（运行期签署时会再核对全局角色）；账号与角色的合理性仍须由管理流程（SOP）保证。项目成员（含项目负责人）可只读查看项目下**全部**方法（URS-102），包括未让其参与的方法——需要按方法保密时须另建项目。
4. （基本解决，URS-90/95）未知用户、错口令、停用账号的错口令返回同一提示，锁定返回同一通用提示，限速与审计去重；`GET /api/users` 对非管理员只返回在用账号，但仍包含用户名、姓名与角色（前端选择成员所需）。剩余局限：能提供正确口令的人可区分“账号已停用”；限速状态在进程内存中。
5. 默认无 TLS：口令与会话经 HTTP 传输（本机回环可接受；局域网必须加 HTTPS 反向代理）。Cookie 已设 `Max-Age`，监听地址非本机时自动加 `Secure`（纯 HTTP 局域网须显式设 `cookie_secure=false`，否则浏览器会丢弃 Cookie），已设 CSP（`default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:`）与 Host 头校验（本机部署自动限本机名称，局域网须配置 `allowed_hosts` 才限制）。

**电子记录与签名**
6. 电子签名为程序内签名：重新输入口令 + 记录姓名/时间/含义/数据哈希；不包含数字证书、生物识别、签名与打印件的法定“签名含义”逐字段呈现（界面与 Word 签名页以表格呈现，无按字段的打印签名显示、无纸质—电子混合流程支持）。
7. 时间戳取服务器本机时钟（存 UTC），**没有与时间服务器同步或防时钟回拨**；有操作系统管理权限者可改系统时间。
8. 审计链与证据表的防篡改**是多层的“抬高门槛 + 检测”，不是防护**：审计链用 HMAC-SHA256（密钥 `data\.audit_key`），链头锚点在 `data\audit_head.json` 与每份备份的旁注文件中，审计表/快照表/评审表有禁止 UPDATE/DELETE 的触发器，签名哈希覆盖阶段内容、实验、附件和方法/项目信息（方法名称、被测属性、样品基质、预期用途与所属项目的产品）。只能改数据库文件的人（不知道密钥）无法伪造通过校验的链，也无法掩盖尾部删除；但能同时读取 `.audit_key` 和写数据库/锚点文件的人（例如服务器管理员）仍可重建一切。须配合操作系统权限（密钥文件仅服务账号可读）、把 `.audit_key` 与备份一起异地保管，并定期复核 `/api/audit/verify`。由旧库转换而来的记录（hv=1 的 SHA-256 链、hv=2 的 HMAC 链）保留并按旧算法验证，其 `method_id` 列由转换工具补填、**不在旧哈希覆盖范围内**；转换前已批准的阶段使用旧签名哈希（hv=1 不含实验/附件；hv=2 的项目信息快照使用“方法名称/项目产品/被测属性/预期用途”），重开重批后才获得当前（hv=3）覆盖。
9. 附件文件存于磁盘，靠 SHA-256 与记录对比发现篡改，上传为流式写盘并有大小上限；删除附件为软删除（文件保留）；内容与记录不符的同名文件不会被覆盖。无病毒扫描与文件类型限制。
10. 生成的 Word 文档为普通 .docx，无数字签名或写保护；以“内容数据哈希”标识来源数据，文件本身被编辑后不会被程序发现。

**架构与运维**
11. SQLite 单节点、单机部署：无高可用/灾备；写入串行化；并发用户数较多时性能受限。
12. 备份与恢复：自动备份与手动备份的 .db **只含数据库**（旁注文件记录 uploads/documents 的 SHA-256 清单、链头和完整性检查结果，恢复时比对）；`uploads\`、`documents\` 须另行复制（`tools\backup.py --files` 可打包）；`.audit_key` 不在备份内，必须随备份另行保管，丢失则审计链无法验证、程序拒绝启动；备份与数据在同一磁盘，**不是异地备份**；恢复演练、保留期限与灾难恢复流程须企业制定。
13. 自动测试为开发者回归测试，不是 IQ/OQ/PQ；界面（`app\static`）无自动化测试；无性能/负载/安全渗透测试；各测试模块（`test_workflow.py`、`test_hardening.py`、`test_projects.py`）各用独立临时数据库；各模块内的测试仍共享该模块的数据库（URS-30 故意篡改审计表后，同模块后续用例不应再校验审计链）。
14. 方法模板、FMEA 种子、知识库内容来自公开指南与项目经验的整理，**科学内容须由使用方专家评审**，不能替代法规原文与企业 SOP。
15. （V0.2）项目/方法分离的局限：方法不能在项目之间移动（只能克隆，签名与实验结果不随克隆走）；项目状态“暂停/完成/归档”会冻结其下全部方法的写操作；生命周期（验证/转移/常规使用/停用）只是带审计的状态字段，没有对应的流程模板；项目的 `product` 一经其下任一方法的阶段批准即冻结（因其并入签名哈希）。
16. （V0.2）旧库转换工具 `tools\migrate_v1_to_v2.py` 仅在测试夹具上验证（URS-106），旧项目的“样品基质”“适应症”无从得知而留空；转换后旧编号 `MD-…` 只保存在方法的 `meta.legacy_code`，已生成文档的文件名不变。
17. （V0.2）模板 1.1 的数值判据、FMEA 初值、实验接受标准均为**示例**（带“示例值，须按ATP确认”标记）；程序只能在 `plan`/`report` 阶段提示标记仍在，**不能判断数值是否合理**；知识库 102 条中部分条款只写名称并标“待核对”，使用前须核对原文。
18. 未提供变更控制/发布记录、软件版本验证清单、供应商评估材料；依赖的第三方包（FastAPI、uvicorn、python-docx、matplotlib、bcrypt 等）版本见 `requirements.txt`，升级须重新回归。
19. （V0.4）文档导出：Word 文件按 OOXML 次序规则生成并经 python-docx / LibreOffice 打开与转换验证，**没有用 Microsoft Word 实际打开检查**；目录是带超链接与页码域的 TOC 字段，页码由 LibreOffice 的版式算出并写入缓存，Word 的分页可能略有出入，在 Word 中右键“更新域”即可；没有 LibreOffice 时目录无页码，文件设置了“打开时更新域”（Word 会提示一次）。PDF 转换依赖本机的 LibreOffice 与中文字体（微软雅黑/宋体），转换由任何有生成权限的用户触发，以服务进程的权限运行；`soffice_path` 只接受名为 soffice 的程序，但管理员仍可借此指定任意同名程序，须按“管理员可信”对待。生成的 Word / PDF 无数字签名，文件被改动后不会被程序发现（SHA-256 只记录在数据库与审计中）。草稿的“水印”是页眉红字与封面横幅，不是页面水印。

## 6. 开发者手工检查记录（非正式）

| 日期 | 内容 | 结果 |
|---|---|---|
| 2026-10-14 | `run.py` 在临时数据目录与端口 8794 启动，`GET /api/state` 返回 200；重复启动提示端口占用 | 通过 |
| 2026-10-14 | `start.bat` 在 Windows 下启动同一服务 | 通过 |
| 2026-10-14 | `tools\backup.py`（含 `--files`）生成并校验备份；`tools\restore.py`：服务器运行时拒绝、审计链被篡改的备份被拒绝、正常恢复并复检 | 通过 |

## 7. 修订历史

| 版本 | 日期 | 说明 |
|---|---|---|
| V0.1 | 2026-10-14 | 首版：21 个自动测试与 URS 对应；列出已知缺口 |
| V0.2（加固） | 2026-10-14 | 后端加固（独立审查 5 项高危 + 8 项中危 + 低危及运维项）：新增 URS-80 ~ 97 与 `tests\test_hardening.py`（52 项）；数据库结构升级为版本 2（贡献者、快照哈希版本、方案外追加标记、审计链 HMAC）；`POST .../review` 必须带 `revision` 与 `expected_hash`（有意的接口变化）；修订第 5 节已解决/仍存在的局限 |
| V0.3 | 2026-10-15 | 项目 / 方法分离（数据模型 v2，数据库结构版本 3）：新增 URS-100 ~ 111 与 `tests\test_projects.py`、`tests\test_templates.py`；原有测试全部改按方法接口重写（URS 编号不变，URS-84/88/97 的测试名与内容随之调整，旧的单级库升级测试 URS-87 子项由 URS-106 取代）；审计链记录体增加 `method_id`（hv=3）；签名哈希公式升为 hv=3；模板升至 1.1（7 个技术、内置知识库 102 条）；新增 `tools\migrate_v1_to_v2.py`；修订第 5 节 |
| V0.4 | 2026-10-15 | 审批级文档导出：`docgen.py` 重写为模板驱动（`doc_structure` + `ch`）的 Word + PDF 导出（受控文件页眉页脚、封面签名表、修订历史、TOC、签署页、附录 A/B/C、横向小节、固定列宽、草稿/完整性失败标记）；新增系统设置 API、`/api/system/capabilities`；`generated_docs` 每格式一行（共享 `gen_id`）；新增 URS-120 ~ 129 与 `tests\test_docgen.py`；其他测试模块默认关闭 PDF 以保持速度；第 5 节增加第 19 条 |


## V0.3 增补（2026-10-15）

| URS | 需求 | 测试 |
|---|---|---|
| URS-130 | 前置步骤通过后后一步才开放（`blocked_by`，保存被拒 409，配置 `enforce_stage_order`） | test_URS15 / test_URS130 |
| URS-131 | 渐进补充：核心内容缺失阻断提交，其余必填项仅警示并记入审计（`strict_completeness` 可恢复全部必填） | test_URS131 |
| URS-132 | 模板预置内容须“确认”才计为已填写；含“示例值”或“XX”占位符的章节不能确认；未确认不计进度 | test_URS132 |
| URS-133 | 含未确认内容/示例值的文档标为“待确认版”，不得标“已批准版本”；已批准版封面披露未填章节 | test_URS133 |
| URS-140 | 站内通知：提交→待签署人，签署→下一签署人，退回/通过/重新打开→团队；仅本人可见，可标记已读 | test_URS140 |
| URS-141 | 修订对比：复核人可见与上一修订的章节差异 | test_URS141 |
| URS-142 | 批量启动/取消实验（逐个校验，按个报告失败）；批量“确认示例值” | test_URS142 / test_URS148 |
| URS-143 | 重排计划：从某步起按周数重排未锁定步骤及其未完成实验 | test_URS143 |
| URS-144 | 工作台：可开始的下一步进入“我的阶段”；方案批准前的计划中实验不显示 | test_URS144 |
| URS-145 | 知识库资源链接库：分类、搜索、增改停用（审计）、重复网址拒绝 | test_URS145 |
| URS-146 | 链接检查：仅检查公网地址（防 SSRF），记录状态码与时间 | test_URS146 |
| URS-147 | 数据库结构 3→4 原位升级并自动备份 | test_URS147 |
| URS-148 | 方案提交时实验设计/接受标准仍含示例值即阻断 | test_URS148 |
| UI-i18n | 界面中英文切换（运行时翻译层 + 生成的词表）；浏览器目检，无自动测试 | 手工 |

已知缺口见《ROADMAP.md》。

## V0.5 增补（2026-10-15，数据库结构版本 5）

| URS | 需求 | 测试 |
|---|---|---|
| URS-150 | 结果行按判据自动判定（≥、≤、范围、±），人工判定不同时在提交前警示 | test_URS150 |
| URS-151 | 统计计算器：描述统计、精密度（ANOVA）、线性、准确度、LOD/LOQ、等效性、计数 CV；另有 `tests/test_stats.py` | test_URS151 / test_stats |
| URS-152 | 材料/仪器台账 + 运行记录（第二人核对；过期/校准过期自动警示） | test_URS152 |
| URS-153 | 偏离记录：未关闭的主要/严重偏离阻止所属步骤提交；关闭需电子签名，不得由提出人关闭 | test_URS153 |
| URS-154 | 审计追踪审核（含哈希链与签名完整性校验），签署需重新输入密码；逾期提醒 | test_URS154 |
| URS-155 | 检查包（zip）：内容、实验、运行、偏离、签名清单、审计追踪、附件哈希清单、已生成文档 | test_URS155 |
| URS-156 | 章节评论与 @提醒 | test_URS156 |
| URS-157 | 全局搜索遵守项目可见性 | test_URS157 |
| URS-158 | 已批准方法的修订版（保留旧版、记录变更说明、需重新评审） | test_URS158 |
| URS-159 | 密码有效期与历史（不得重复使用最近 N 个） | test_URS159 |
| URS-160 | 可选“修改原因”（`require_change_reason`），记入审计 | test_URS160 |
| URS-161 | 文档后台生成（异步 + 进度），支持英文导出（固定文字） | test_URS161 |
| URS-162 | 邮件 / Webhook 外发通知 | test_URS162 |
| UI-en2 | 新增页面的英文界面；浏览器目检 | 手工 |
| URS-163 | 英文文档导出：封面、表头、章节标题、签署页等固定文字为英文；模板正文与用户填写内容保持原样 | test_URS163 |
