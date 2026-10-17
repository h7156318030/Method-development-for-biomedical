# MethodFlow（分析方法开发管理）

[English](README.md) | [中文](README.zh-CN.md)

[![tests](https://github.com/h7156318030/Method-development-for-biomedical/actions/workflows/test.yml/badge.svg)](https://github.com/h7156318030/Method-development-for-biomedical/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**MethodFlow 管理分析方法从开发到批准的全过程。** “项目”把相关的方法放在一起；每个方法按九个阶段推进，在评审门上有复核和批准并留下电子签名，所有操作进入防篡改的审计追踪；最后可生成可直接送审的方案与报告（Word 和 PDF）。

适用于生物医药研发实验室（例如细胞与基因治疗的质控），可在一台电脑上或实验室局域网内使用。界面有中文和英文两种语言。

> **本程序不是已验证的 GxP 系统。** MethodFlow 是辅助工具。用于受监管用途时，须由使用单位按计算机化系统验证（CSV / GAMP 5）流程完成风险评估、IQ/OQ/PQ、SOP、账号管理以及备份与灾难恢复。模板中的数值都是**示例**，须按本单位的 ATP 确认；标注“条款待核对”的法规引用须对照现行原文核实。详见[局限与合规声明](#局限与合规声明)。

语言：界面跟随浏览器语言，可在右下角切换（“中文 / EN”）。内置模板和知识库目前是中文。用户手册有两个版本：[English](docs/user-manual_en.md) 和 [中文](docs/用户手册_中文.md)。

---

## 目录

- [它能做什么](#它能做什么)
- [运行环境](#运行环境)
- [快速开始](#快速开始)
- [工作流程](#工作流程)
- [角色与职责分离](#角色与职责分离)
- [电子签名与审计追踪](#电子签名与审计追踪)
- [文档（Word 与 PDF）](#文档word-与-pdf)
- [配置](#配置)
- [数据、备份与恢复](#数据备份与恢复)
- [在实验室局域网中使用](#在实验室局域网中使用)
- [自动测试](#自动测试)
- [目录结构](#目录结构)
- [文档索引](#文档索引)
- [贡献、安全与许可证](#贡献安全与许可证)
- [局限与合规声明](#局限与合规声明)

## 它能做什么

- **项目与方法。** 项目（产品或管线层面的容器）下可以有多个分析方法；每个方法有自己的团队和自己的九阶段开发记录。
- **九个阶段、六个评审门。** 从立项与背景、分析目标概况（ATP）、技术选择与试剂策略、风险评估（FMEA）、开发方案、可行性实验、稳健性（DoE）与控制策略，到开发报告和进入验证的批准。评审门要求复核人；方案、控制策略和报告还要求批准人（QA）。
- **职责分离。** 编辑过某阶段内容的人，不能复核或批准该阶段；复核人与批准人必须是不同的人。
- **电子签名。** 签名时须重新输入口令。每个签名保存姓名、时间（UTC）、签名含义、意见、修订号以及签名内容的 SHA-256 哈希。
- **审计追踪。** 保存、提交、签名、重新打开、生成文档等操作都写入哈希链（HMAC）。直接修改数据库的行为可被发现。
- **实验与结果。** 实验带有设计和接受标准；结果行按判据自动判定（≥、≤、范围、±）；统计计算器（描述统计、准确度、带 ANOVA 方差分量的精密度、线性、LOD/LOQ、配对 TOST 等效性、计数 CV）；支持 CSV 导入。
- **台账与运行记录。** 试剂、参比品、仪器与设备，记录批号、效期和校准到期日；运行记录由第二人核对；过期项目自动警示。
- **偏离。** 未关闭的“主要”或“严重”偏离会阻止其所属阶段提交；关闭偏离需要电子签名，且不能由提出人本人关闭。
- **审计追踪审核与检查包。** 定期审核审计追踪（含哈希链和签名校验，可设提醒）；一键导出包含完整记录的 zip 检查包。
- **模板。** 七种方法类型，包括流式细胞术、色谱、生物活性、细胞法功能/效力、qPCR/ddPCR、免疫化学与结合法，以及通用类型。每个模板预置术语、参考文件、FMEA、实验、系统适用性和检查清单。预置内容须经“确认”后才计为已完成。
- **知识库。** 规则、陷阱、操作指南，以及法规、药典、指南等资源链接库，并可检查链接有效性。
- **协作。** 章节评论与 @提醒、站内通知，可选邮件与 Webhook 通知（企业微信、钉钉、飞书）、全局搜索、已批准方法的修订版，以及可选的修改原因。
- **安全基础。** 口令策略（长度、字母与数字、可选有效期与历史）、多次失败后锁定账号、登录频率限制、会话超时、CSRF 防护。

## 运行环境

- Python 3.9 或更高版本。`requirements.txt` 中的版本已在 Python 3.9（Windows）上验证。
- 主要面向 Windows（启动脚本为 `.bat`）。Python 代码本身不依赖 Windows。
- 可选：[LibreOffice](https://www.libreoffice.org/)，用于输出 PDF。没有它仍可生成 Word 文档。

## 快速开始

### Windows

1. 安装 Python 3.9 以上版本，安装时勾选 *Add python.exe to PATH*。
2. 双击 `start.bat`。它会查找 Python、询问是否安装依赖、启动服务，并在浏览器中打开 <http://127.0.0.1:8780/>。
3. 首次访问时**没有任何预设账号**。创建第一个管理员（用户名、姓名、至少 10 位且同时含字母和数字的口令）。该账号同时拥有四种全局角色。
4. 进入 **管理 → 用户管理**，创建其他用户并分配角色。新用户首次登录必须修改口令。

如果 Python 不在 PATH 中，可在运行 `start.bat` 前设置环境变量 `METHODFLOW_PYTHON`，值为 `python.exe` 的完整路径。

### 命令行（任何平台）

```bash
python -m pip install -r requirements.txt
python run.py                       # http://127.0.0.1:8780/
python run.py --port 8790           # 换端口
python run.py --data /path/to/data  # 换数据目录
python run.py --no-browser          # 不自动打开浏览器
```

设置的优先级（从高到低）：命令行参数、环境变量（`METHODFLOW_DATA`、`METHODFLOW_HOST`、`METHODFLOW_PORT`）、`config.json`、内置默认值。

按 Ctrl+C 停止服务，数据不受影响。

## 工作流程

| # | 阶段 | 评审门 | 谁签名 |
|---|---|---|---|
| 1 | 立项与背景 | 无（提交即完成） | — |
| 2 | 分析目标概况 ATP | G1 | 复核人 |
| 3 | 技术选择与试剂策略 | G2 | 复核人 |
| 4 | 风险评估 FMEA | 无 | — |
| 5 | 开发方案与实验设计 | GP | 复核人，然后批准人 |
| 6 | 可行性与优化实验 | G3 | 复核人 |
| 7 | 稳健性、稳定性与参数范围（DoE） | 无 | — |
| 8 | 参比品与控制策略 | G4 | 复核人，然后批准人 |
| 9 | 预验证与开发报告 | G5 | 复核人，然后批准人 |

- 某阶段的前置阶段通过后，该阶段才开放（可用 `enforce_stage_order` 配置）。
- 某阶段被重新打开后，依赖它的阶段会变为“已失效”，须重新提交复核后，覆盖它们的评审门才能签署。
- 开发方案批准后新增的实验，必须填写设计和接受标准。
- 提交前检查会列出所有阻断提交的原因，例如缺少核心内容、实验未完成、FMEA 高风险项无控制措施、没有可用的复核人。
- 判据中仍带有“示例值”标记时，提交方案或报告会给出警告。请按 ATP 确认数值并去掉标记。

分步说明见用户手册：[English](docs/user-manual_en.md)（第 4 节）或[中文](docs/用户手册_中文.md)。程序左侧菜单中还有“新手指引”。

## 角色与职责分离

**全局角色**（在账号上）：管理员、开发人员（可新建项目和方法）、复核人、批准人（QA）。

**项目角色**：负责人、成员、只读。

**方法角色**：负责人、开发人员、复核人、批准人（QA）、只读。一人可以兼任多个方法角色，但有手册中说明的限制。方法团队成员必须先是所属项目的成员。项目角色不授予方法的编辑或签名权限。

凡是对某阶段有过贡献的人（保存、提交过该阶段内容，或编辑过其下实验或附件的人），都不能复核或批准该阶段。

## 电子签名与审计追踪

- 复核、批准、重新打开、变更生命周期，以及把方法或项目改回“进行中”，都需要重新输入口令。
- 服务器核对签名人看到的修订号和内容哈希。如果期间内容已变化，签名会被拒绝。
- 审计追踪记录所有变更。哈希链以 `data/.audit_key` 为密钥。管理页面可随时校验整条链和全部签名。
- 电子签名是口令重新认证并绑定修订号与内容哈希，**不是**数字证书。

## 文档（Word 与 PDF）

在方法的 **文档** 页可生成 **开发方案** 或 **开发报告**：

- 总是生成 Word 文件（`.docx`）；若安装了 LibreOffice，还生成 PDF（`.pdf`）。生成约需 20–60 秒。
- 封面、受控页眉页脚、修订历史、目录、各章节、签署页和附录均按方法所用模板生成。
- 每次生成都会判定状态：**已批准版本**（各阶段均已通过、无失效阶段、签名完整）、**草稿**（有阶段未通过或已失效），或**完整性校验失败**（已签署内容与签名不一致）。草稿会标明不得作为批准文件使用。
- 文件保存在 `data/documents/<方法编号>/`。
- 英文导出：文档语言选择 *English*。封面、表头、章节标题、签署页等固定文字会翻译为英文；模板正文和用户填写的内容保持原样。
- 文件没有数字签名，也没有写保护。受控发放须按企业的文件管理程序办理。

PDF 由 LibreOffice 生成。程序按以下顺序查找 `soffice`：管理页“文档设置”中的路径、`config.json` 中的 `soffice_path`、系统 PATH，最后是默认安装目录。

## 配置

如需修改设置，在程序文件夹中新建 `config.json`。只写需要修改的键，必须是合法的 JSON。修改后需要重启服务。

| 键 | 默认值 | 含义 |
|---|---|---|
| `host` | `127.0.0.1` | 监听地址。`0.0.0.0` 表示允许局域网访问 |
| `port` | `8780` | 监听端口 |
| `session_hours` | `12` | 会话绝对有效期（小时） |
| `idle_minutes` | `60` | 空闲超时（分钟） |
| `max_failed_logins` | `5` | 连续输错口令多少次后锁定账号 |
| `lock_minutes` | `15` | 锁定时长（分钟） |
| `enforce_stage_order` | `true` | 阶段按顺序开放 |
| `strict_completeness` | `false` | 设为 `true` 时，所有必填项都会阻断提交 |
| `rpn_threshold` | `120` | FMEA：RPN 达到此值须有控制措施 |
| `severity_threshold` | `8` | FMEA：严重度达到此值须有控制措施 |
| `min_password_length` | `10` | 口令最短长度（同时要求字母和数字） |
| `password_max_days` | `0` | 口令有效天数（0 = 永不过期） |
| `password_history` | `5` | 新口令不得与最近 N 个口令相同 |
| `audit_review_days` | `90` | 审计追踪审核的提醒周期（0 = 不提醒） |
| `require_change_reason` | `false` | 修改已退回或已重新打开的阶段时须填写原因 |
| `setup_token` | `""` | 若设置，首个管理员只能凭此口令创建。局域网部署时建议设置 |
| `allowed_hosts` | `null` | 允许的主机名，例如 `["lab.example.org"]` |
| `cookie_secure` | `null` | 会话 Cookie 是否带 `Secure`（监听网络地址时自动设为真） |
| `soffice_path` | `""` | LibreOffice 的 `soffice` 路径 |
| `pdf_enabled` | `true` | 设为 `false` 时只输出 Word |
| `smtp_host` 等 | — | 邮件通知相关设置（`smtp_host`、`smtp_port`、`smtp_user`、`smtp_password`、`smtp_from`、`smtp_tls`） |
| `webhook_url`、`webhook_kind` | `""`、`generic` | Webhook 通知（`generic`、`wecom`、`feishu`、`dingtalk`） |
| `public_url` | `""` | 通知链接中使用的基础地址 |

完整列表见用户手册：[English](docs/user-manual_en.md)（第 11.3 节）或[中文](docs/用户手册_中文.md)（第 11.3 节）。**`config.json` 中可能含有邮件和 Webhook 的密钥，切勿提交到仓库。**

## 数据、备份与恢复

默认数据保存在程序文件夹下的 `data/` 中：

| 路径 | 内容 |
|---|---|
| `data/methodflow.db` | SQLite 数据库（用户、项目、方法、签名、实验、审计追踪、知识库） |
| `data/uploads/` | 附件，带 SHA-256 校验 |
| `data/documents/` | 生成的 Word 与 PDF 文件 |
| `data/backups/` | 数据库备份；启动时和每 24 小时自动生成，也可手动生成 |
| `data/.audit_key` | 审计哈希链的密钥。**必须与备份一同保管；丢失后审计链无法校验，也无法继续写入。** |
| `data/audit_head.json` | 审计链锚点 |

- 用 `backup.bat`（或 `python tools/backup.py`）备份；加 `--files` 可同时打包附件和文档。
- 把 `data/.audit_key`、`data/audit_head.json` 和备份目录复制到另一处保存。同一块磁盘上的备份挡不住磁盘故障。
- 用 `python tools/restore.py` 恢复（先停止服务）。恢复时会检查备份，把当前数据库另存为 `prerestore_*.db`，不改动附件和文档。
- 服务运行时不要直接复制 `methodflow.db`，请使用备份工具。
- 忘记管理员口令时（先停止服务）：

  ```bash
  python tools/reset_admin.py --username admin
  ```

  会打印一次性临时口令，下次登录须修改，并写入审计记录。

## 在实验室局域网中使用

默认只有本机能访问。多人使用时：

- **推荐：** 服务仍监听 `127.0.0.1`，前面加一层 **HTTPS 反向代理**（例如 Caddy 或 nginx）。把代理的主机名填入 `allowed_hosts`，并设置 `setup_token`。
- **直接用明文 HTTP 访问：** 设置 `"host": "0.0.0.0"` 和 `"cookie_secure": false`，在防火墙中放行端口，同事访问 `http://<服务器IP>:8780/`。明文 HTTP 会在网络上传输口令和会话，只能用于可信的内网。

服务器时钟是签名和审计追踪的时间来源，请保持与时间服务器同步。每个数据库只运行一个服务。

## 自动测试

```bash
python -X utf8 -m unittest discover -s tests    # 约 10 分钟，163 项
python tools/run_tests_report.py                # 运行测试并重写 docs/自动化测试报告.md
```

每个测试模块使用各自的临时数据目录。未安装 LibreOffice 时跳过 PDF 相关测试。测试名中的 `test_URS<n>_…` 对应 [`docs/URS_需求与测试追溯.md`](docs/URS_需求与测试追溯.md) 中的需求编号。这些是开发者回归测试，不是 IQ/OQ/PQ。

## 目录结构

```
app/           FastAPI 后端（main、workflow、records、compliance、stats、docgen、db、auth、audit 等）
app/static/    纯 JavaScript 单页前端（无构建步骤、无 CDN，可离线使用）
tests/         自动测试，按需求编号命名
tools/         备份、恢复、管理员重置、审计锚点、数据迁移、测试报告、翻译辅助脚本
docs/          用户手册（中英文）、需求与追溯、设计说明、验证模板
run.py         启动脚本
start.bat      Windows 启动器
backup.bat     Windows 备份启动器
```

## 文档索引

| 文档 | 语言 |
|---|---|
| [`README.md`](README.md) | English |
| [`README.zh-CN.md`](README.zh-CN.md)（本文件） | 中文 |
| [`docs/user-manual_en.md`](docs/user-manual_en.md) | English，完整用户手册 |
| [`docs/用户手册_中文.md`](docs/用户手册_中文.md) | 中文，完整用户手册 |
| [`docs/URS_需求与测试追溯.md`](docs/URS_需求与测试追溯.md) | 中文（开头有英文摘要），需求与测试追溯 |
| [`docs/V0.2需求与设计_项目方法分离与审批级文档.md`](docs/V0.2需求与设计_项目方法分离与审批级文档.md) | 中文（开头有英文摘要），设计说明 |
| [`docs/前端契约.md`](docs/前端契约.md) | 中文（开头有英文摘要），前端与接口契约 |
| [`docs/后端加固清单.md`](docs/后端加固清单.md) | 中文（开头有英文摘要），后端加固清单 |
| [`docs/调研与设计依据.md`](docs/调研与设计依据.md) | 中文（开头有英文摘要），调研与设计依据 |
| [`docs/CSV验证模板/`](docs/CSV验证模板/README.md) | 英文 README；IQ/OQ/PQ、风险评估、SOP 起点模板 |
| [`CHANGELOG.md`](CHANGELOG.md) | 英文，版本历史 |
| [`ROADMAP.md`](ROADMAP.md) | 英文，未完成事项 |

## 贡献、安全与许可证

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)（英文）。欢迎帮助的方向见 [ROADMAP.md](ROADMAP.md)。
- 问题与缺陷报告：[SUPPORT.md](SUPPORT.md)（英文）。报告时请去除真实数据和口令。
- 安全问题：请通过 GitHub 的 **Report a vulnerability** 私下报告，见 [SECURITY.md](SECURITY.md)。
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
- 采用 [Apache License 2.0](LICENSE) 许可，见 [NOTICE](NOTICE)。

## 局限与合规声明

- 不是已验证的 GxP 系统。自动测试是开发者回归测试，不是 IQ/OQ/PQ。
- 模板中的示例值不是经过验证的判据。程序会警告，但不判断数值是否合理。
- 模板和知识库中的法规、药典引用并非都已对照现行原文核实，标注“待核对”的须在使用前核实。
- 仅支持本地账号，没有 SSO，没有多因素认证。内置为 HTTP，网络使用时请在前面加 HTTPS。
- 时间取自服务器时钟，不做校时检测，也不防时钟回拨。
- 单节点 SQLite 数据库，没有高可用。
- 审计哈希链只能发现数据库中的篡改；同时掌握数据库和 `.audit_key` 的人可以重算整条链。
- Word 与 PDF 文档没有数字签名，也没有写保护；PDF 版面依赖 LibreOffice。
- 验证、转移、常规监控等开发阶段之后的生命周期，目前只作为状态记录，没有流程模板。见 [ROADMAP.md](ROADMAP.md)。
