"""Method-development workflow templates (V1.1).

A template = the common 9-stage workflow (charter -> ATP -> technique -> risk -> plan -> explore -> robustness ->
control strategy -> report) + technique-specific professional presets (glossary / reference documents / key
reagents and instruments / initial method conditions / FMEA seeds / experiment seeds / SST seeds / checklist
additions / writing placeholders).  Content distilled from ICH Q14, ICH Q2(R2), ICH Q9(R1), ICH M10, FDA 2015
analytical-procedures guidance, FDA 2024 CAR-T guidance, FDA 2023 potency-assurance draft, USP <1220>/<1225>/<1226>/
<111>/<1032-1034>, and the CD19/CD22 CAR flow case developed in this project.

Document-structure metadata (new in 1.1)
-----------------------------------------
Every section carries ``ch = {"plan": "6.1", "report": "7.1"}``: the heading number the section gets in the
approval-level 《分析方法开发方案》(plan) and 《分析方法开发报告》(report).  ``DOC_STRUCTURE`` (also returned as
``template["doc_structure"]``) lists the chapters of each document (number, title, auto-generated blocks).  A
document generator renders chapter by chapter in numeric order, and inside a chapter the sections ordered by their
``ch`` value; sections without a ``ch`` entry for a document are not part of that document.

Seeds
-----
Table sections may carry ``seed_rows`` (list of dicts keyed by column key) and text sections ``default`` (boiler-
plate text).  The engine copies them into the stage data on creation (see CHANGELOG: engine request E1).

All numeric acceptance values in presets are EXAMPLES and are tagged ``SAMPLE_TAG`` where they are in experiment /
validation seeds; they must be confirmed against the ATP before use.  Regulatory references are cited by document
title/version; section numbers appear only where they were checked against the guideline text, otherwise the
reference is marked "（条款待核对）".
"""
import copy

TEMPLATE_VERSION = "1.1"
SAMPLE_TAG = "（示例值，须按ATP确认）"

CHANGELOG = [
    {"version": "1.1", "date": "2026-10-14", "changes": [
        "方案文档按 15 章、报告文档按 21 章重新规划；每个章节带 ch 编号（plan/report），新增 doc_structure",
        "新增职责(RACI)、缩略语、参考文件、方法原理、初始方法条件、仪器、样品、石川图(表)、S/O/D 评分标准、风险-实验映射、统计分析、数据完整性(ALCOA+)、偏离与变更、里程碑等章节",
        "报告文档新增：结论性意见、风险再评估、使用批号、SOP 草案(原理…注意事项 11 节)、偏离清单、遗留问题、验证矩阵、结论",
        "所有技术模板预置：术语、参考文件、关键试剂/材料/仪器/软件、初始条件、FMEA(≥10)、实验种子(≥8)、ATP 判据、SST、稳定性/DoE 因子、EC 建议、验证矩阵",
        "新增技术模板 cell_based（细胞法功能/效力测定）；共 7 个技术模板",
        "文本章节增加 placeholder 示例句与 help 写作要点；检查清单增加并标注引用；必填项重新平衡",
        "条款引用核对：Q14/Q2(R2)/M10/FDA 2015/FDA 2024 CAR-T/FDA 2023 效力草案的章节号对照官方文本核对",
    ]},
    {"version": "1.0", "date": "2026-10-13", "changes": ["初版：9 阶段通用流程 + 6 个技术模板（flow/hplc/bioassay/qpcr/elisa/generic）"]},
]


# ------------------------------------------------------------------ helpers
def ck(key, text, guidance="", ref="", required=True, evidence=False):
    return {"key": key, "text": text, "guidance": guidance, "ref": ref, "required": required, "evidence": evidence}


def CH(plan=None, report=None):
    """Heading numbers of a section in the plan / report documents."""
    d = {}
    if plan:
        d["plan"] = plan
    if report:
        d["report"] = report
    return d


def text(key, title, help="", required=False, placeholder="", ch=None, default=""):
    d = {"key": key, "title": title, "type": "text", "help": help, "required": required, "placeholder": placeholder,
         "ch": ch or {}}
    if default:
        d["default"] = default
    return d


def fields(key, title, flds, help="", required=False, ch=None):
    return {"key": key, "title": title, "type": "fields", "fields": flds, "help": help, "required": required, "ch": ch or {}}


def fld(key, label, type="text", options=None, hint="", required=False):
    return {"key": key, "label": label, "type": type, "options": options or [], "hint": hint, "required": required}


def table(key, title, cols, help="", required=False, min_rows=0, ch=None, seed_rows=None):
    return {"key": key, "title": title, "type": "table", "columns": cols, "help": help,
            "required": required, "min_rows": min_rows, "seed_rows": seed_rows or [], "ch": ch or {}}


def col(key, label, type="text", options=None, width=None):
    return {"key": key, "label": label, "type": type, "options": options or [], "width": width}


def special(key, title, type, help="", required=True, ch=None):
    """matrix / fmea sections (engine-special)."""
    return {"key": key, "title": title, "type": type, "help": help, "required": required, "ch": ch or {}}


def F(mode, cause, effect, S, O, D, control=""):
    return {"mode": mode, "cause": cause, "effect": effect, "S": S, "O": O, "D": D, "control": control}


def X(code, title, objective, design, acceptance, stage_key, weeks=1):
    """Experiment seed.  ``design`` should state sample size / replicates; ``acceptance`` states the criterion and
    the decision rule and carries SAMPLE_TAG."""
    return {"code": code, "title": title, "objective": objective, "design": design, "acceptance": acceptance,
            "stage_key": stage_key, "weeks": weeks}


def S_(t):
    """Append the example-value tag to an acceptance text."""
    return t + SAMPLE_TAG


# ------------------------------------------------------------------ document structure (plan / report)
PLAN_CHAPTERS = [
    ("1", "目的与范围", []), ("2", "适用对象与职责", []), ("3", "缩略语与术语", []), ("4", "参考文件与法规依据", []),
    ("5", "背景与研发目标", []), ("6", "分析目标概况（ATP）", []), ("7", "技术选择与方法原理", []),
    ("8", "材料、试剂、参比品与仪器", []), ("9", "样品与基质", []), ("10", "风险评估", []),
    ("11", "开发策略与实验设计", ["experiments"]), ("12", "数据处理、可追溯性与数据完整性", []),
    ("13", "偏离与变更处理", []), ("14", "进度计划与里程碑", ["gantt"]), ("15", "方案批准记录", ["approval"]),
]
REPORT_CHAPTERS = [
    ("1", "摘要与结论", []), ("2", "目的与范围", []), ("3", "适用对象与职责", []), ("4", "缩略语与术语", []),
    ("5", "参考文件与法规依据", []), ("6", "背景与研发目标", []), ("7", "分析目标概况（ATP）", []),
    ("8", "技术选择与方法原理", []), ("9", "材料、试剂、参比品与仪器", []), ("10", "样品与基质", []),
    ("11", "风险评估", []), ("12", "开发策略与实验设计（方案回顾）", ["experiments"]),
    ("13", "实验结果汇总", ["experiment_results"]), ("14", "稳健性、稳定性与参数范围（DoE / PAR / MODR）", []),
    ("15", "控制策略", []), ("16", "对照 ATP 的达成情况", []), ("17", "方法描述草稿（SOP 草案）", []),
    ("18", "数据处理、可追溯性与数据完整性", []), ("19", "偏离清单", []),
    ("20", "遗留问题、经验教训与验证建议", []), ("21", "结论与批准", ["approval"]),
]


def doc_structure():
    return {
        "plan": [{"no": n, "title": t, "auto": a} for n, t, a in PLAN_CHAPTERS],
        "report": [{"no": n, "title": t, "auto": a} for n, t, a in REPORT_CHAPTERS],
        "auto_blocks": {
            "experiments": "实验清单与设计（来自“实验”页：编号/名称/目的/设计/接受标准/计划日期）",
            "experiment_results": "全部实验的结果、结论、偏离（按阶段分组）",
            "gantt": "阶段甘特图（来自阶段计划日期）",
            "approval": "按评审门列出的签署页（角色/姓名/含义/日期时间/修订号/数据哈希/完整性）",
        },
    }


# ------------------------------------------------------------------ common seeds (all techniques)
COMMON_SEEDS = {
    "charter.raci": [
        ["方案编制", "方法开发人员", "方法负责人", "统计人员、QC", "QA"],
        ["方案复核", "复核人（QC / 分析开发）", "复核人", "统计人员", "方法负责人"],
        ["方案批准", "批准人（QA）", "批准人（QA）", "工艺开发、质量负责人", "全体相关人员"],
        ["实验执行与原始记录", "方法开发人员", "方法负责人", "统计人员", "复核人"],
        ["数据复核（第二人）", "第二分析员 / 复核人", "方法负责人", "QA", "—"],
        ["仪器确认、校准与维护", "仪器管理员 / 设备部门", "QC 负责人", "方法开发人员", "QA"],
        ["试剂、参比品、标准品管理", "试剂管理员", "QC 负责人", "方法开发人员", "QA"],
        ["偏离与变更处理", "方法负责人", "QA", "方法开发人员、复核人", "项目负责人"],
        ["开发报告编制与批准", "方法开发人员", "方法负责人（编制）/ QA（批准）", "统计人员、工艺开发", "全体相关人员"],
    ],
    "charter.glossary": [
        ["ATP", "Analytical Target Profile 分析目标概况", "预期用途、被测属性，以及可报告结果必须满足的性能特性与判据；技术中立（ICH Q14）。"],
        ["CQA", "Critical Quality Attribute 关键质量属性", "其数值应在适当限度内以保证产品质量的物理、化学、生物学或微生物学属性。"],
        ["EC", "Established Condition 已确立条件", "在监管文件中描述、变更时需按规定类别报告的分析程序要素（ICH Q12 / Q14）。"],
        ["PAR", "Proven Acceptable Range 参数范围", "单个分析程序参数的范围，范围内方法已被数据证明适用于预期用途；范围内移动无需监管通知（ICH Q14）。"],
        ["MODR", "Method Operable Design Region 方法可操作设计空间", "两个或以上参数的组合范围，范围内方法适用于预期用途（ICH Q14）。"],
        ["SST", "System Suitability Test 系统适用性试验", "随每次运行执行、用于确认测量系统与操作在分析时段内适用的预设检验。"],
        ["DoE", "Design of Experiments 实验设计", "多因子同时变化的结构化实验，用于估计主效应、交互作用与响应面。"],
        ["FMEA / RPN", "失效模式与影响分析 / 风险优先数", "按严重度 S、发生度 O、可检测度 D 评分，RPN = S × O × D（ICH Q9(R1)）。"],
        ["LLOQ / QL", "Lower Limit of Quantification 定量下限", "满足预设准确度与精密度的最低可报告水平。"],
        ["LOD / DL", "Limit of Detection 检测限", "可与空白区分但不一定能定量的最低水平。"],
        ["RSD / CV", "相对标准偏差 / 变异系数", "标准偏差与均值之比；生物测定常用几何变异系数（GCV）。"],
        ["TOST", "Two One-Sided Tests 双单侧检验", "等效性检验：差值的置信区间完全落入预设等效界值内。"],
        ["可报告结果", "Reportable result", "按规定的重复数与计算规则得到、并与规格比较的最终结果（ICH Q2(R2)）。"],
        ["ALCOA+", "可归属、清晰、同步、原始、准确（+完整、一致、持久、可用）", "数据完整性原则。"],
        ["IQ / OQ / PQ", "安装 / 运行 / 性能确认", "仪器确认的三个阶段。"],
        ["OOS / OOT", "超标 / 超趋势", "检验结果超出规格 / 偏离历史趋势。"],
        ["RACI", "Responsible, Accountable, Consulted, Informed", "职责分配矩阵：执行、负责、咨询、知会。"],
        ["PACMP", "Post-Approval Change Management Protocol 上市后变更管理方案", "事先约定变更类型、桥接研究与报告类别的方案（ICH Q12 / Q14）。"],
    ],
    "charter.refdocs": [
        ["法规/指南", "ICH Q14 Analytical Procedure Development", "ICH Step 4，2023-11-01 采纳（EMA/CHMP/ICH/195040/2022）", "ATP、知识与风险管理、稳健性与参数范围、控制策略、EC、生命周期"],
        ["法规/指南", "ICH Q2(R2) Validation of Analytical Procedures", "ICH Step 4，2023-11-01 采纳", "性能特性、报告范围、验证设计、Annex 2 各技术示例"],
        ["法规/指南", "ICH Q9(R1) Quality Risk Management", "2023", "风险评估（石川图 / FMEA）原则与主观性管理"],
        ["法规/指南", "ICH Q12 Technical and Regulatory Considerations for Pharmaceutical Product Lifecycle Management", "ICH Step 4，2019", "EC、上市后变更报告类别、PACMP"],
        ["法规/指南", "FDA Guidance for Industry: Analytical Procedures and Methods Validation for Drugs and Biologics", "FDA，2015-07", "分析程序内容（第 IV 节）、验证（第 VI 节）、统计（第 VII 节）、生命周期（第 VIII 节）"],
        ["法规/指南", "ICH M10 Bioanalytical Method Validation and Study Sample Analysis", "ICH Step 4，2022-05", "仅借用其关键试剂管理、稳定性、平行性等原则；不直接适用于质量控制分析"],
        ["法规/指南", "FDA Data Integrity and Compliance With Drug CGMP: Questions and Answers", "FDA，2018-12", "数据完整性（ALCOA）、审计追踪"],
        ["法规/指南", "21 CFR Part 11 Electronic Records; Electronic Signatures", "现行版", "电子记录与电子签名"],
        ["药典", "USP <1220> Analytical Procedure Life Cycle", "USP–NF 现行版（条款待核对）", "分析程序生命周期：设计、性能确认、持续性能验证"],
        ["药典", "USP <1225> Validation of Compendial Procedures；USP <1226> Verification of Compendial Procedures", "USP–NF 现行版（条款待核对）", "药典方法验证 / 确认"],
        ["企业文件", "企业《分析方法开发 / 验证管理 SOP》", "（编号待填）", "开发流程与评审要求"],
        ["企业文件", "企业《偏差管理 SOP》《变更控制 SOP》《数据完整性 SOP》《仪器确认与校准 SOP》《试剂与参比品管理 SOP》", "（编号待填）", "偏离与变更、数据、仪器、试剂管理"],
    ],
    "risk.scoring": [
        ["1", "无影响", "几乎不会发生", "现有控制几乎必然检出"],
        ["3", "轻微：不影响结果判定或精密度", "偶尔发生", "现有控制很可能检出"],
        ["5", "中等：影响精密度或需重复，但不致错判", "可能发生（例如约每 20 次运行 1 次）", "现有控制可能检出"],
        ["7", "显著：可能使结果偏离 ATP 判据或导致错误结论", "常见", "现有控制不易检出"],
        ["9–10", "严重：可能导致错误放行/拒收、数据完整性问题或影响患者安全", "几乎每次运行都发生", "现有控制无法检出"],
    ],
    "plan.alcoa": [
        ["可归属 Attributable", "能追溯到谁在何时做了什么", "个人账号登录；电子记录自动记录操作人与时间；纸质记录签名并注明日期"],
        ["清晰 Legible", "可读且永久", "优先电子记录；纸质用不可擦除墨水；不得涂改，修改须划改并注明原因"],
        ["同步 Contemporaneous", "操作时即记录", "实时录入；确需补记须注明补记时间与原因"],
        ["原始 Original", "原始记录或经认证的真实副本", "保留仪器原始文件（FCS / 色谱 / 板读数等）；导出的副本须核对并注明"],
        ["准确 Accurate", "无错误；修改可追溯", "计算模板/脚本受控并经验证；人工转录经第二人核对；审计追踪开启"],
        ["完整 Complete", "含全部数据（含重复、失败、排除）", "无效/失败运行保留并说明原因；排除数据须依预设规则"],
        ["一致 Consistent", "格式与时序一致", "统一命名规则；仪器与记录系统时钟同步"],
        ["持久 Enduring", "在保存期内保持可读", "定期备份；归档介质与格式迁移计划"],
        ["可用 Available", "审核/检查时可调阅", "按实验编号-文件名建立索引；权限与检索路径明确"],
    ],
    "plan.change_control": [
        ["接受标准、统计方法或样本量变更", "重大", "实施前书面评估；复核人/批准人认可；记入方案修订历史；已批准阶段须重新开启复核", "方法负责人 / QA"],
        ["接受标准未达到", "重大", "按偏离处理并调查原因；不得事后修改判据或剔除数据以“通过”；保留首次结果", "方法负责人 / QA"],
        ["关键试剂 / 参比品更换供应商或规格", "重大", "并排比较或桥接研究；评估对判据与 SST 的影响；更新试剂数据表", "方法负责人 / QA"],
        ["关键试剂 / 参比品更换批号", "次要", "按批放行规则做并排比较（滴定 / 参比品比较）后使用", "方法负责人"],
        ["仪器更换、重大维修或软件升级", "次要", "重新确认 / 校准；必要时做性能比对；记录", "仪器管理员 / 方法负责人"],
        ["实验未按设计完成或需增补", "次要", "记录偏离与原因；评估对结论的影响；必要时补充实验并修订方案", "方法负责人"],
        ["数据缺失、无审计追踪的修改或疑似数据完整性问题", "重大", "立即通知 QA；封存相关记录；按数据完整性 SOP 调查", "QA"],
    ],
    "plan.milestones": [
        ["M1 立项与背景确认", "立项与背景", "", "背景、目的、范围、职责、术语、参考文件", "—"],
        ["M2 ATP 批准（G1）", "分析目标概况", "", "ATP 与判据依据", "M1"],
        ["M3 技术与试剂策略确定（G2）", "技术选择", "", "评分矩阵、方法原理、初始条件、关键试剂策略", "M2"],
        ["M4 风险评估完成", "风险评估", "", "石川图、FMEA、风险-实验映射", "M2"],
        ["M5 开发方案批准（GP）", "开发方案", "", "本方案；实验设计与统计计划；材料与仪器清单", "M3、M4"],
        ["M6 可行性复核通过（G3）", "可行性与优化", "", "可行性与优化实验结论", "M5"],
        ["M7 稳健性与稳定性完成", "稳健性", "", "DoE、PAR、稳定性时限", "M6"],
        ["M8 控制策略复核通过（G4）", "控制策略", "", "SST、参比品、试剂管理、EC", "M7"],
        ["M9 预验证与开发报告批准（G5）", "预验证与报告", "", "开发报告、SOP 草案、验证策略", "M8"],
    ],
}

APPEND_SEEDS = ("charter.glossary", "charter.refdocs")   # technique rows are appended to the common rows


# ------------------------------------------------------------------ common stages
def common_stages():
    S = []
    # ---------------------------------------------------------------- 1 charter
    S.append({
        "key": "charter", "title": "立项与背景", "weeks": 1, "gate": None, "requires": [],
        "desc": "明确为什么要开发这个方法、给谁用、受什么约束，并建立文件的基础信息（职责、术语、参考文件）。内容对应方案第 1–5 章。",
        "checklist": [
            ck("c1", "已明确产品/样品类型与要测的质量属性", "写清属性名称与它为何影响安全性或有效性。", "ICH Q14 §3"),
            ck("c2", "已明确监管背景与所处阶段（IND 早期 / 确证性 / BLA / 上市后）", "阶段决定验证强度：I 期通常不要求完整验证，确证性研究前应完成确认（qualification），BLA 必须验证。", "FDA 2024 CAR-T §IV.C.2；FDA 2023 效力草案 V.C.3"),
            ck("c3", "已确定项目负责人、复核人和批准人", "复核人与批准人不得是内容编辑者；建议在成员页指定至少 1 名复核人、1 名批准人。", "21 CFR Part 11；FDA 数据完整性问答（2018）"),
            ck("c4", "已识别已有方法/平台方法/文献经验，并记录先验知识来源", "平台方法用于新产品可缩短开发；记录采用了哪些先验知识。", "ICH Q14 §4.1"),
            ck("c5", "已确定整体时间计划与资源（人员、仪器、材料）", "", "", False),
            ck("c6", "已建立职责分配（RACI），编制/复核/批准职责分离", "RACI 中“负责（A）”每项只能有一个角色。", "ICH Q10 药品质量体系（管理职责相应章节，条款待核对）"),
            ck("c7", "参考文件清单已列出并核对版本（含药典通则与企业 SOP）", "列文件名称+版本/日期；不确定的版本写“待核对”。", "ICH Q14 §4.1", False),
            ck("c8", "已确定采用最小方法还是增强方法（或待定），并说明理由", "增强方法要求更多风险评估与多变量研究，换来更灵活的参数范围与变更管理。", "ICH Q14 §2.1"),
        ],
        "sections": [
            text("objective", "目的与成功标准", "用 1–3 句话写清：开发什么方法、测什么属性、用在什么场景，以及“开发完成”的标准（通常是对照 ATP 全部达成或有批准的处置计划、控制策略定稿、预验证通过）。",
                 True, "开发并确认一个用于 XX 产品放行与稳定性检测的 XX 方法，测定 XX 属性。开发完成的标准为：对照 ATP 的全部性能特性达成或有已批准的处置计划，控制策略定稿，预验证演练通过并获批进入验证。",
                 CH("1.1", "2.1")),
            text("scope", "适用范围与不在范围", "分“范围内 / 范围外”两栏写；范围外的内容要说明与本方法的接口（例如效力、VCN 由另行方法测定）。",
                 True, "范围内：XX 的方法原理确定、条件优化、稳健性与稳定性、控制策略与预验证。\n范围外：XX 效力测定、XX 的验证与转移（另行方案）；接口：本方法的 XX 结果作为 XX 计算的分母。",
                 CH("1.2", "2.2")),
            text("audience", "适用对象与场所", "写明谁需要遵守本文件：开发人员、复核人、批准人、使用本方法的 QC 实验室；以及适用的产品、样品类型和实验场所。",
                 False, "本方案适用于参与 XX 方法开发、复核和批准的人员；适用产品：XX；实验场所：XX 实验室（编号/房间）。", CH("1.3", "2.3")),
            fields("context", "监管阶段与区域", [
                fld("phase", "产品阶段", "select", ["临床前/研究", "I 期 IND", "II 期", "确证性研究前", "BLA/上市申请", "上市后变更"], "", True),
                fld("region", "目标区域", "select", ["中国 NMPA", "美国 FDA", "欧盟 EMA", "多区域"], "", True),
                fld("approach", "开发方式（ICH Q14）", "select", ["最小方法", "增强方法", "待定"], "增强方法需更完整的风险评估、多变量研究与控制策略论证"),
                fld("ref_docs", "主要依据文件（摘要）", "text", [], "例：ICH Q14/Q2(R2)；FDA 2024 CAR-T；完整清单见第 4 章"),
            ], "", False, CH("1.4", "2.4")),
            table("raci", "职责分配（RACI）", [
                col("activity", "活动", "text", [], 200), col("r", "执行 R", "text", [], 140), col("a", "负责 A", "text", [], 140),
                col("c", "咨询 C", "text", [], 130), col("i", "知会 I", "text", [], 110)],
                "按活动列出谁执行(R)、谁负责(A，每项只能一个)、谁被咨询(C)、谁被知会(I)；可用岗位名称，姓名在成员页与签署页体现。批准人不得是内容编辑者。",
                True, 4, CH("2.1", "3.1")),
            table("glossary", "缩略语与术语", [
                col("term", "缩略语/术语", "text", [], 110), col("full", "全称/中文", "text", [], 190), col("definition", "本文件中的含义", "text", [], 320)],
                "只列正文用到的缩略语；与 ICH Q14/Q2(R2) 术语表保持一致；技术特有术语已预置，请删除不用的并补充产品特有术语。",
                False, 0, CH("3.1", "4.1")),
            table("refdocs", "参考文件与法规依据", [
                col("category", "类别", "select", ["法规/指南", "药典", "行业标准", "文献", "企业文件"], 90),
                col("title", "文件名称", "text", [], 280), col("number", "文件编号/版本/日期", "text", [], 170),
                col("relevance", "适用章节/用途", "text", [], 230)],
                "写文件名称+版本或日期；不确定的版本/章节写“待核对”，不要凭记忆写条款号。企业 SOP 写受控编号。",
                True, 3, CH("4.1", "5.1")),
            text("background", "背景", "产品与属性背景 → 为什么需要这个方法 → 现状不足（无方法 / 旧方法局限 / 变更驱动）→ 与所处法规阶段的关系。写与本产品相关的事实并引用来源，不要整段复制指南。",
                 True, "XX 为 XX 类产品，其 XX 属性影响 XX（安全性/有效性）。目前 XX（尚无可用方法 / 现有方法存在 XX 局限）。拟在 XX 阶段用于 XX。", CH("5.1", "6.1")),
            text("dev_goals", "研发目标（可度量）", "把成功标准拆成可逐项回答“达到/未达到”的目标：性能目标（对应 ATP）、通量与周转、可转移性、时间与成本约束。",
                 False, "1) 对照 ATP 全部性能特性达成；2) 单次运行 ≤ 1 个工作日完成；3) 方法可由第二实验室按 SOP 执行；4) 开发周期 ≤ 26 周。", CH("5.2", "6.2")),
            text("prior", "已有方法与先验知识", "列出平台方法、文献、既往项目教训、供应商数据，并说明哪些先验知识被直接采用、哪些需在本次开发中验证后才采用（ICH Q14 知识管理）。",
                 False, "平台方法 XX 已用于 XX 产品（来源：XX）；文献 XX 报道了 XX；既往项目 XX 的教训：XX。本次直接采用：XX；需验证后采用：XX。", CH("5.3", "6.3")),
        ],
    })
    # ---------------------------------------------------------------- 2 atp
    S.append({
        "key": "atp", "title": "分析目标概况（ATP）", "weeks": 2,
        "gate": {"key": "G1", "name": "G1 ATP 复核", "roles": ["reviewer"], "covers": []}, "requires": ["charter"],
        "desc": "ATP 是开发与验证的依据：预期用途 + 被测属性 + 性能特性与判据。判据用统计区间表达并说明依据；同时规定样品与基质。内容对应方案第 6、9 章。",
        "checklist": [
            ck("a1", "预期用途明确（放行/稳定性/过程控制；样品类型）", "", "ICH Q14 §3"),
            ck("a2", "被测属性与规格（或预期规格）已写明", "", "ICH Q14 §3"),
            ck("a3", "报告范围由规格推导，并说明下限/上限依据", "Q2(R2) 表 2 示例：含量 80%–120%；效力 规格下限 −20% 至上限 +20%（规格 80–125% → 64–150%）。比例类属性的下限常由可靠定量下限决定。", "ICH Q2(R2) §2.3、Table 2"),
            ck("a4", "可报告结果的重复数已规定（几管/几次运行取均值）", "验证设计须反映常规使用的重复数。", "ICH Q2(R2) §2.1"),
            ck("a5", "准确度与精密度判据以统计区间表达，并给出依据", "示例：相对偏倚的 90% CI；中间精密度几何 CV 的 95% CI 上限。避免只写“RSD ≤ x%”。", "ICH Q14 Annex A 抗 TNF-α 效力示例 Table 4"),
            ck("a6", "专属性要求写明（干扰物/对照/稳定性指示）", "", "ICH Q2(R2) §3.1；§2.4（稳定性指示）"),
            ck("a7", "ATP 不预设具体技术（技术中立）", "技术在 ATP 之后才选择。", "ICH Q14 §3"),
            ck("a8", "样品类型、基质、取样与保存要求（含最长保存时间要求）已写明", "保存要求会决定稳定性研究的范围。", "FDA 2015 §IV.E（样品制备）；ICH Q14 §3"),
            ck("a9", "每条判据的依据类型已区分：规格推导 / 产品知识 / 法规或药典 / 暂定待确认", "暂定值在 G1 后须有确认计划。", "ICH Q14 §3", False),
            ck("a10", "对 ATP 的假设与约束（如产品构型、规格尚未最终确定）已记录", "假设变化会触发 ATP 重新评估。", "ICH Q14 §7（生命周期管理）", False),
        ],
        "sections": [
            text("use", "预期用途", "写清五件事：样品类型、测定对象、用途（放行/稳定性/过程控制/表征）、执行场所与站点数、产品阶段。保持技术中立，不要写“用流式/HPLC”。",
                 True, "测定 XX 样品（XX 形态）中 XX 的 XX（含量/百分比/相对效力）；用于放行、稳定性与过程控制；可在 XX 个站点执行；适用阶段 XX。", CH("6.1", "7.1")),
            text("attribute", "被测属性与规格", "写属性名称、规格（或预期规格及其来源）、与 CQA / 作用机制的关联。规格未定时写预期范围与待定原因。",
                 True, "属性：XX。规格：XX（预期）。与 CQA 的关联：XX 是 XX 的前提，影响 XX。本方法不替代 XX（接口：XX）。", CH("6.2", "7.2")),
            fields("reportable", "可报告结果与范围", [
                fld("replicates", "可报告结果的重复数", "text", [], "例：每样品 2 个独立染色管，取均值；每次运行含 SST", True),
                fld("range", "报告范围", "text", [], "例：5%–95%（LLOQ 初定 ≥ 5%）", True),
                fld("range_basis", "范围推导依据", "text", [], "规格下限 −20% / 可靠定量下限 …"),
                fld("decision_rule", "与规格比较的判定规则", "text", [], "是否考虑测量不确定度；修约规则；重复/复测规则"),
            ], "", False, CH("6.3", "7.3")),
            table("criteria", "性能特性与判据", [
                col("characteristic", "性能特性", "select", ["准确度", "精密度-重复性", "精密度-中间精密度", "联合评价(总误差)", "线性/响应", "专属性", "定量下限", "稳健性/稳定性", "其他"], 130),
                col("criterion", "判据（统计区间表达）", "text", [], 280),
                col("rationale", "依据", "text", [], 220),
                col("source", "来源/参考", "text", [], 140),
            ], "每条判据都要有依据；数值是后续验证接受标准的来源。预置数值均为示例，须按规格与产品风险确认。", True, 3, CH("6.4", "7.4")),
            text("specificity", "专属性与干扰", "列出需要排除的干扰（基质、相关物质、降解物、同类靶点）、阴性/阳性对照、稳定性指示要求，以及如何证明。",
                 False, "需排除的干扰：XX。阴性对照：XX；阳性对照：XX。若需稳定性指示：用强降解样品证明可检出 XX 的变化。", CH("6.5", "7.5")),
            text("assumptions", "假设与约束", "写会改变 ATP 的前提（产品构型、规格是否已定、阶段、样品可得性）。假设变更时回到本章评估。",
                 False, "假设：产品构型为 XX；规格下限暂按 XX 设定，待工艺能力数据确认。约束：样品量有限（每批 ≤ XX）。", CH("6.6", "7.6")),
            table("samples", "样品类型与基质", [
                col("sample", "样品/对照", "text", [], 150), col("description", "说明（基质/形态/批次来源）", "text", [], 210),
                col("storage", "保存与运输条件", "text", [], 150), col("hold", "最长保存时间要求", "text", [], 130),
                col("purpose", "在开发中的用途", "text", [], 170)],
                "列出开发中会用到的全部样品与对照（代表性批次、阴/阳性对照、加标/降解/混合样品）；批次须覆盖报告范围的低、中、高水平。",
                True, 2, CH("9.1", "10.1")),
            text("sampling", "取样、前处理、保存与稳定性要求", "写取样量与方法、样品处理（复苏/稀释/匀浆等）、保存条件、容许保存时间、冻融次数及其依据；样品量受限时写明优先级。",
                 False, "取样：XX；保存：XX ℃，不超过 XX h；冻融：不超过 XX 次。稳定性研究见开发实验 XX。", CH("9.2", "10.2")),
        ],
    })
    # ---------------------------------------------------------------- 3 tech
    S.append({
        "key": "tech", "title": "技术选择与试剂策略", "weeks": 2,
        "gate": {"key": "G2", "name": "G2 技术与试剂复核", "roles": ["reviewer"], "covers": []}, "requires": ["atp"],
        "desc": "ATP 驱动技术选择：用评分矩阵比较候选技术，写出方法原理，列出初始方法条件，并确定关键试剂策略。内容对应方案第 7、8.1 章。",
        "checklist": [
            ck("t1", "至少比较 2 种候选技术/原理，并给出评分与讨论", "评分 = Σ(权重 × 得分)；评分只是起点，须写文字理由。", "ICH Q14 §3；§2.1"),
            ck("t2", "关键试剂/对照/参比的来源与替代方案已确定", "关键试剂需数据表与寿命管理（身份、来源、批号、纯度、浓度、稳定性、储存）。", "ICH M10 §4.1.2（原则可借用）"),
            ck("t3", "已评估是否存在正交方法用于准确度评价", "", "ICH Q2(R2) §3.1.1.2；§3.3.1.3"),
            ck("t4", "已确认所选技术能满足 ATP 的报告范围与精密度要求", "", "ICH Q14 §3"),
            ck("t5", "方法原理已用文字描述，并与 ATP / CQA 的关联清楚", "技术原理本身可作为 EC，更换原理通常属较大变更。", "ICH Q14 §6.1"),
            ck("t6", "初始方法条件已列表，并注明来源（文献/平台/预实验）和待研究范围", "初始条件是 DoE 与 PAR 的起点；每个参数写“为什么是这个值”。", "ICH Q14 §4.1；§5.2"),
            ck("t7", "关键试剂与材料的关键性已评估（关键/重要/一般）及其风险控制", "关键性高的试剂须有批放行或再确认规则。", "ICH M10 §4.1.2（原则可借用）"),
            ck("t8", "与既有方法/平台的关系已说明（复用范围、桥接需求）", "", "ICH Q14 §4.1", False),
        ],
        "sections": [
            special("matrix", "技术选择评分矩阵", "matrix", "得分 1–5；权重按重要性设定；系统自动计算加权总分。准则应直接来自 ATP（专属性、范围、精密度、稳定性指示等）。", True, CH("7.1", "8.1")),
            text("decision", "选择结论与理由", "为什么选它、为什么不选其他、已知局限、局限如何由控制策略补偿。评分相近时写决定性的定性理由。",
                 True, "选择 XX。理由：XX 能满足 ATP 的 XX 与 XX；备选 XX 因 XX 未被采用。已知局限：XX，由 XX 控制。", CH("7.2", "8.2")),
            text("principle", "方法原理描述", "用 1–3 段写清：测量的物理/化学/生物学基础、信号如何产生、计算什么、关键假设；让同行不看 SOP 也能理解方法。",
                 True, "样品经 XX 处理后，XX 与 XX 特异结合/反应，产生与 XX 成比例的信号；以 XX 为参比，按 XX 计算 XX。关键假设：XX。", CH("7.3", "8.3")),
            table("conditions", "初始方法条件与参数", [
                col("category", "类别", "select", ["样品", "试剂/溶液", "反应/染色/孵育", "仪器/检测", "数据处理", "保存/稳定性", "其他"], 110),
                col("parameter", "参数", "text", [], 150), col("initial", "初始设定", "text", [], 170),
                col("range", "拟研究范围", "text", [], 150), col("basis", "来源与依据", "text", [], 200)],
                "初始条件均为起点，须经开发实验确认；“拟研究范围”决定后续 DoE 的因子水平。",
                True, 3, CH("7.4", "8.4")),
            table("reagents", "关键试剂与参比品策略", [
                col("name", "试剂/材料", "text", [], 150), col("role", "作用", "text", [], 110),
                col("source", "来源/供应商", "text", [], 120), col("critical", "关键性", "select", ["关键", "重要", "一般"], 70),
                col("risk", "主要风险", "text", [], 160), col("mitigation", "控制措施", "text", [], 170)],
                "关键性 = 对结果的影响 × 批间变异的可能性；关键试剂须有数据表、批放行与桥接规则。", True, 1, CH("8.1", "9.1")),
            text("bridge", "与既有方法/平台的关系", "平台方法复用的范围、与旧方法的比较需求、方法变更时的桥接设想。",
                 False, "本方法复用平台方法 XX 的 XX 部分，新增 XX。若替换现行方法 XX，需做并排比较（样品：XX，判据：XX）。", CH("5.4", "6.4")),
        ],
    })
    # ---------------------------------------------------------------- 4 risk
    S.append({
        "key": "risk", "title": "风险评估（FMEA）", "weeks": 1, "gate": None, "requires": ["atp"],
        "desc": "用石川图识别因素，用 FMEA 排序，并把高风险项映射到开发实验或控制措施。内容对应方案第 10 章。",
        "checklist": [
            ck("r1", "已用石川图或等效方法识别影响结果的因素（样品/试剂/仪器/方法/人员与分析/环境）", "", "ICH Q14 §4.2；Annex A 石川图示例"),
            ck("r2", "FMEA 已评分，S/O/D 标准已按企业 SOP 固化；S ≥ 8 的项目不论 RPN 都有专门控制", "RPN = S×O×D；RPN 只用于排序，不是客观量。", "ICH Q9(R1)"),
            ck("r3", "RPN 高的项目已有控制措施，并映射到开发实验", "", "ICH Q14 §4.2"),
            ck("r4", "已识别两个及以上测量通道/靶点/分析物之间的灵敏度差异风险（如适用）", "", "", False),
            ck("r5", "风险评估由跨职能团队（开发、QC、QA、工艺/统计）完成，评分过程有记录", "ICH Q9(R1) 强调管理评分的主观性与偏倚。", "ICH Q9(R1)", False),
            ck("r6", "风险–实验映射表已建立：每个高风险项对应实验编号或控制措施", "", "ICH Q14 §4.2", False),
        ],
        "sections": [
            table("ishikawa", "石川图要点（按因素类别）", [
                col("category", "类别", "select", ["样品", "试剂与材料", "仪器", "方法", "人员与分析", "环境与流程"], 120),
                col("factors", "潜在影响因素", "text", [], 300), col("effect", "可能影响的性能特性", "text", [], 170),
                col("control", "现有/拟定控制", "text", [], 200)],
                "每一类至少列出 2–3 个因素；预置行为该技术的典型因素，请按实际增删。", False, 0, CH("10.1", "11.1")),
            table("scoring", "S / O / D 评分标准", [
                col("level", "分值", "text", [], 60), col("s", "严重度 S", "text", [], 280),
                col("o", "发生度 O", "text", [], 200), col("d", "可检测度 D", "text", [], 220)],
                "评分标准示例；须与企业《质量风险管理 SOP》一致并在评分前固化。", False, 0, CH("10.2", "11.2")),
            special("fmea", "FMEA 风险表", "fmea", "S/O/D 为 1–10。RPN ≥ 阈值或 S ≥ 8 的行必须填写控制措施。预置行为该技术常见失效模式，评分为初值，须由团队重新打分。", True, CH("10.3", "11.3")),
            table("risk_map", "风险–实验映射", [
                col("risk", "失效模式（FMEA）", "text", [], 200), col("experiment", "对应实验/控制", "text", [], 150),
                col("how", "如何评估或控制", "text", [], 260), col("residual", "预期剩余风险", "select", ["高", "中", "低"], 80)],
                "每个高风险项至少对应一个开发实验或明确的控制措施；剩余风险在报告中回写。", False, 0, CH("10.4", "11.4")),
            table("risk_review", "风险再评估（开发后）", [
                col("risk", "失效模式", "text", [], 200), col("rpn_before", "开发前 RPN", "number", [], 80),
                col("rpn_after", "开发后 RPN", "number", [], 80), col("evidence", "依据/实验编号", "text", [], 220),
                col("status", "结论", "select", ["已降低", "已接受", "仍需验证确认", "新增风险"], 110)],
                "开发结束后对 FMEA 重新评分，写明依据；新增风险也应记录。", False, 0, CH(None, "11.5")),
        ],
    })
    # ---------------------------------------------------------------- 5 plan
    S.append({
        "key": "plan", "title": "开发方案与实验设计", "weeks": 2,
        "gate": {"key": "GP", "name": "GP 开发方案批准", "roles": ["reviewer", "approver"],
                 "covers": ["charter", "atp", "tech", "risk"]},
        "requires": ["tech", "risk"],
        "desc": "把前面的决定变成可执行的方案：分阶段实验、判据、统计方法、材料仪器、数据完整性要求、偏离变更程序与时间。方案批准后才能开始实验。内容对应方案第 8.2–8.3、11–14 章。",
        "checklist": [
            ck("p1", "开发分为若干阶段，每阶段有目的、设计、分析方法、决策规则和输出", "参考：P0 材料可行性 / P1 滴定与专属性 / P2 条件优化 / P3 稳定性 / P4 门控或积分规则 / P5 DoE 稳健性 / P6 参比品 / P7 控制策略 / P8 预验证。", "FDA 2015 §III（分析方法开发）"),
            ck("p2", "所有拟做实验已在“实验”页登记，并写明设计、样本量与接受标准", "接受标准含决策规则，并注明数值为示例时须按 ATP 确认。", ""),
            ck("p3", "统计方法与样本量依据已写明", "DoE 设计类型、回归/方差分析、等效性检验、软件与版本。", "ICH Q14 §5.2；FDA 2015 §VII"),
            ck("p4", "高 RPN 风险项已映射到具体实验", "", "ICH Q14 §4.2"),
            ck("p5", "材料与仪器清单已填写（含关键性、再确认计划与仪器确认状态）", "仪器须在使用前确认合格。", "", True),
            ck("p6", "已识别需要提前决策的开放问题（待决策清单）", "", "", False),
            ck("p7", "数据完整性要求（ALCOA+）、软件与版本、原始数据保存方式已写明", "", "FDA 数据完整性问答（2018）；21 CFR Part 11"),
            ck("p8", "偏离与变更处理规则已写明，含“不得事后修改判据”的约束", "", "ICH Q14 §7；企业偏差/变更 SOP"),
            ck("p9", "进度计划与里程碑已确定，依赖关系清楚", "", "", False),
        ],
        "sections": [
            text("strategy", "开发总体策略", "用一页内说明开发思路：先做什么后做什么、为什么这样排序、哪些实验并行、哪些是门（失败即回到技术选择）。",
                 True, "先以最小对比（阴性 vs 阳性）验证可行性（P0），再确定关键试剂工作浓度与专属性（P1），随后优化条件（P2）；稳定性与 DoE（P3、P5）在条件固定后开展；参比品（P6）与 SST（P7）在 DoE 结果后定稿；P8 预验证演练后进入验证。", CH("11.1", "12.1")),
            table("phases", "开发阶段计划", [
                col("phase", "阶段", "text", [], 60), col("objective", "目的", "text", [], 170),
                col("design", "设计与分析方法", "text", [], 250), col("acceptance", "决策规则/判据", "text", [], 230),
                col("weeks", "周数", "number", [], 60)], "把 ATP 与风险评估转为实验计划。预置阶段来自该技术的实验种子，请删改。", True, 3, CH("11.2", "12.2")),
            text("statistics", "统计分析计划", "回归与残差、方差分量（ANOVA/REML）、DoE 分析（效应、曲率、伪标准误）、容忍区间/等效性检验、异常值规则、软件与版本。应在看到数据前写定。",
                 True, "线性：最小二乘，报告斜率/截距 95% CI 与残差图；精密度：ANOVA 方差分量，报告重复性与中间精密度的 RSD 及 95% CI；稳定性：相对 0 h 的 TOST 或回归斜率 CI；统计软件：XX 版本 XX（已验证）。", CH("11.4", "12.4")),
            text("sample_size", "样本量与重复数依据", "说明每个实验的样本量（样品数、水平数、运行数、重复数）及其依据：统计功效、CI 宽度、样品可得性、与可报告结果重复数的一致性。",
                 False, "核心精密度实验：4 水平 × 6 运行 × 2 重复；运行间方差估计在 6 个运行时 CI 较宽，故以 XX 作为判据的安全余量。", CH("11.5", "12.5")),
            text("decision_rules", "决策规则与判据变更原则", "写清：未达标时下一步怎么走（调查→改进→重复）、什么情况回到技术选择、谁有权决定；判据一经批准，不得事后修改。",
                 False, "任一门控实验未达标：调查原因并经方法负责人与复核人认可后改进条件并重复；连续两次改进仍未达标，回到技术选择阶段重新评估。判据不得在数据产生后修改。", CH("11.6", "12.6")),
            text("open_issues", "待决策事项与假设", "列出会改变设计的未决问题、默认选择、负责人与期限。",
                 False, "1) 抗原试剂形式（默认：直接荧光偶联；负责人：XX；期限：P0 前）。2) 规格下限（默认：XX；期限：G1 前）。", CH("11.7", "12.7")),
            table("materials", "材料、试剂、参比品与耗材清单", [
                col("item", "项目", "text", [], 150), col("category", "类别", "select", ["试剂", "参比品/标准品", "对照", "耗材", "溶液/缓冲液", "细胞/生物材料"], 90),
                col("supplier", "供应商/货号/规格", "text", [], 180), col("lot", "批号", "text", [], 100), col("expiry", "效期", "text", [], 90),
                col("critical", "关键性", "select", ["关键", "重要", "一般"], 70), col("requal", "再确认/复验计划", "text", [], 170),
                col("status", "状态", "select", ["待采购", "已到位", "已确认(IQ/OQ/PQ)", "待确认"], 110)],
                "关键试剂、参比品须有批号、效期与再确认规则；批号未定时留空，实际使用的批号在报告的“使用批号”表中记录。",
                True, 3, CH("8.2", "9.2")),
            table("instruments", "仪器与设备", [
                col("instrument", "仪器/设备", "text", [], 150), col("config", "型号/配置", "text", [], 170), col("use", "用途", "text", [], 150),
                col("qual", "确认状态", "select", ["待确认", "已确认(IQ/OQ/PQ)", "校准有效", "不适用"], 110),
                col("cal", "校准/维护/质控计划", "text", [], 170), col("asset", "资产编号", "text", [], 90)],
                "仪器须在使用前完成确认并在校准有效期内；多站点使用须规定仪器协调方式。", True, 1, CH("8.3", "9.3")),
            table("software", "软件与计算机化系统", [
                col("software", "软件/系统", "text", [], 170), col("version", "版本", "text", [], 80), col("purpose", "用途", "text", [], 160),
                col("csv", "验证状态", "select", ["已验证", "待验证", "供应商认证", "不适用"], 90),
                col("audit", "审计追踪", "select", ["开启", "部分", "无", "不适用"], 80)],
                "列出采集、分析、统计、记录用软件；统计与计算用软件须验证或确认；审计追踪应开启。", False, 0, CH("12.1", "18.1")),
            text("data_handling", "数据处理、原始数据保存与计算规则", "写原始数据在哪里、怎么命名、谁复核；计算用什么模板；重新处理（重新积分/门控/排除）的规则。已预置通用条款，按本方法修改。",
                 False, "", CH("12.2", "18.2"),
                 default="1) 原始数据（仪器原始文件、读数文件、电子表格、照片）保存在采集系统/受控目录，并在实验记录中注明文件名、版本和位置；不得以截图或手抄代替原始电子数据。\n2) 所有计算使用受控模板或经验证的软件；模板/脚本须有版本号，修改须经变更控制；人工转录的数据须经第二人核对。\n3) 数据按实验编号归档；附件上传后系统记录 SHA-256，替换产生新记录并保留原记录。\n4) 审计追踪保持开启；数据修改须保留原值、修改人、时间和原因。\n5) 重新积分/重新门控/排除数据点须按预先规定的规则执行并记录理由，不得选择性处理以满足接受标准。"),
            table("alcoa", "数据完整性（ALCOA+）落实措施", [
                col("principle", "原则", "text", [], 130), col("meaning", "含义", "text", [], 180), col("measures", "本方法的落实措施", "text", [], 330)],
                "逐条写明本方法开发中如何落实；已预置通用措施，请按实际修改。", False, 0, CH("12.3", "18.3")),
            text("deviation", "偏离处理程序", "写明偏离如何记录、评估、批准，哪些情况必须通知 QA，以及未达接受标准时的处理原则。已预置通用条款，按企业 SOP 修改。",
                 True, "", CH("13.1", None),
                 default="开发过程中发生的任何偏离方案的情况（实验未按设计执行、材料/仪器替代、接受标准未达到、数据异常）须在发生当日记录于“实验”页的“偏离/说明”栏，注明：发生时间、描述、影响评估、处置决定及决定人。\n对判据、统计方法、样本量、关键材料的变更，须在实施前由方法负责人评估，经复核人/批准人认可后记入方案修订历史；已批准方案的变更须重新开启相应阶段并重新复核（系统将使受影响的后续阶段失效）。\n未达到接受标准时，不得修改判据或剔除数据以“通过”；应调查原因（仪器/试剂/操作/样品/方法），经批准后重复或改进方法，并保留最初结果及其处置记录。\n重大偏离（影响 ATP 判据、数据完整性或产品质量判断）须通知 QA，按企业《偏差管理 SOP》处理。"),
            table("change_control", "变更与偏离分类", [
                col("trigger", "触发情形", "text", [], 220), col("class", "分类", "select", ["重大", "次要"], 70),
                col("action", "处理要求", "text", [], 320), col("approver", "批准", "text", [], 130)],
                "预先约定哪些变更需要重新评审，避免事后争议；已预置通用情形。", False, 0, CH("13.2", None)),
            table("milestones", "里程碑", [
                col("milestone", "里程碑", "text", [], 200), col("stage", "对应阶段", "text", [], 110), col("date", "计划日期", "date", [], 100),
                col("deliverable", "交付物", "text", [], 230), col("depends", "依赖", "text", [], 100)],
                "与阶段计划日期一致；甘特图由系统按阶段日期生成。", False, 0, CH("14.1", None)),
            text("timeline", "时间计划说明", "关键里程碑、关键路径与依赖（例如参比品定值需 ≥ 20 次独立运行，周期长，应尽早启动）；资源冲突与应对。",
                 False, "关键路径：试剂到货 → P1 滴定 → P5 DoE → P6 参比品定值（≥20 次运行，约 4 周）→ P8 预验证。风险：关键试剂交期；应对：双供应商。", CH("14.2", None)),
        ],
    })
    # ---------------------------------------------------------------- 6 explore
    S.append({
        "key": "explore", "title": "可行性与优化实验", "weeks": 4,
        "gate": {"key": "G3", "name": "G3 可行性复核", "roles": ["reviewer"], "covers": []}, "requires": ["plan"],
        "desc": "执行方案中的可行性、滴定/条件筛选、专属性初筛、条件优化实验。每个实验记录结果并给出结论。结果汇总对应报告第 13 章。",
        "checklist": [
            ck("e1", "本阶段所有实验均已完成或取消，并有结论", "取消需写原因；结论须与接受标准对照。", ""),
            ck("e2", "方法在最简单对比（阴性 vs 阳性 / 空白 vs 标准）上可行，背景与分离满足预设", "", ""),
            ck("e3", "关键参数的最佳条件已确定并记录依据（如滴定、孵育、体积、梯度）", "", "FDA 2024 CAR-T §IV.C.2.a.iii（抗体滴定，适用时）", True),
            ck("e4", "所有偏离与异常结果已记录并评估影响", "", "", False),
            ck("e5", "每个实验的原始数据已保存并可追溯（附件/记录编号），结果与接受标准逐项对照", "结果表须能回溯到原始文件；不得只贴汇总图。", "FDA 数据完整性问答（2018）", False, True),
        ],
        "sections": [
            text("summary", "阶段小结", "做了什么、结果如何、结论是什么、对后续有什么影响。按实验编号逐个写 1–3 句，并给出“达标/未达标”。",
                 True, "P0：NTD 背景 0.4%（判据 ≤ 2%），达标；P1：…（逐项）。结论：方法在 XX 条件下可行，进入 XX。", CH(None, "13.1")),
            table("decisions", "本阶段形成的决定", [
                col("decision", "决定", "text", [], 220), col("evidence", "证据/实验编号", "text", [], 180), col("impact", "对后续影响", "text", [], 200)],
                "每个决定都要有证据；写明它改变了后续哪个实验或哪个控制措施。", False, 0, CH(None, "13.2")),
            text("issues", "问题与偏离", "列出异常结果、偏离、重复实验及其处置；与偏离清单一致。",
                 False, "P1 第 3 次运行因 XX 无效，已重复；原因：XX；影响评估：无。", CH(None, "13.3")),
        ],
    })
    # ---------------------------------------------------------------- 7 robust
    S.append({
        "key": "robust", "title": "稳健性、稳定性与参数范围（DoE）", "weeks": 3, "gate": None, "requires": ["explore"],
        "desc": "用 DoE 找关键参数并划定 PAR/MODR；研究样品、处理后、试剂与参比品的稳定性并确定最长保存时间。对应报告第 14 章。",
        "checklist": [
            ck("d1", "已按风险选择因子并设计 DoE（含中心点），分析方法已预先规定", "", "ICH Q14 §5.2；FDA 2015 §III"),
            ck("d2", "关键参数及其 PAR/设定点已确定，依据已记录", "PAR 内变动无需监管通知；验证须覆盖设定点。", "ICH Q14 §5.2"),
            ck("d3", "样品/处理后/试剂稳定性已评价，最长保存时间已确定并留有余量", "", "FDA 2024 CAR-T §IV.C.2.a.v（流式）；ICH Q14 §5.1（含样品制备与试剂稳定性）"),
            ck("d4", "稳健性结论已回写风险评估（FMEA 更新）", "", "ICH Q14 §5.1"),
            ck("d5", "稳健性与稳定性实验的原始数据已保存并可追溯", "", "FDA 数据完整性问答（2018）", False, True),
        ],
        "sections": [
            table("factors", "DoE 因子与水平", [
                col("factor", "因子", "text", [], 150), col("low", "低(−)", "text", [], 90), col("center", "中心(0)", "text", [], 90),
                col("high", "高(+)", "text", [], 90), col("rationale", "选择依据", "text", [], 200)],
                "因子来自 FMEA 高风险项；类别变量（仪器、批号、分析员）也可纳入设计。预置因子为该技术常见参数，水平为占位，须按初始条件设定。",
                False, 0, CH(None, "14.1")),
            text("analysis", "DoE 设计与分析结论", "设计类型（部分因子/Plackett-Burman/BBD/CCD）、运行数、随机化与分块、显著因子（效应与 CI 或伪标准误）、曲率检验、别名处理、结论如何影响 PAR。",
                 True, "采用 2^(5−2) 部分因子设计 8 次运行 + 3 次中心点，随机化；以 Lenth 伪标准误判定显著；因子 X、Y 显著；曲率不显著；据此将 X、Y 设为严格控制参数。", CH(None, "14.2")),
            table("par", "参数范围（PAR/设定点）", [
                col("parameter", "参数", "text", [], 150), col("setpoint", "设定点", "text", [], 100),
                col("par", "PAR/可接受范围", "text", [], 150), col("basis", "依据", "text", [], 230)],
                "写“设定点 ± 范围”及依据（实验编号）；未研究的参数不要写范围。", True, 1, CH(None, "14.3")),
            table("stability", "稳定性研究", [
                col("item", "项目", "text", [], 130), col("condition", "条件", "text", [], 130), col("times", "时间点", "text", [], 130),
                col("result", "结果", "text", [], 160), col("limit", "确定的时限", "text", [], 110)],
                "时限取满足判据的最长时间并留余量；写入 SOP，并在验证中确认。", True, 1, CH(None, "14.4")),
            text("risk_feedback", "稳健性结论对风险评估的回写", "说明稳健性/稳定性结果使哪些 FMEA 项的 O 或 D 下降或上升，哪些风险仍需控制。",
                 False, "FMEA 第 X 项（XX）：O 由 5 降为 3（DoE 显示 XX 影响小）；第 Y 项：D 由 5 降为 3（SST 增设 XX）。", CH(None, "14.5")),
        ],
    })
    # ---------------------------------------------------------------- 8 control
    S.append({
        "key": "control", "title": "参比品与控制策略", "weeks": 3,
        "gate": {"key": "G4", "name": "G4 控制策略复核", "roles": ["reviewer", "approver"],
                 "covers": ["robust"]}, "requires": ["robust"],
        "desc": "SST、样品适用性、参比品/对照、关键试剂管理与已确立条件（EC）、持续监控。控制策略应在验证前定义。对应报告第 15 章。",
        "checklist": [
            ck("s1", "SST 项目与判据来自开发数据，并能区分合格与不合格运行", "", "ICH Q14 §6"),
            ck("s2", "样品适用性判据已定义（如活率、事件数、重复差、平行性）", "", "ICH Q14 §6"),
            ck("s3", "参比品/对照的建立、定值、稳定性与替换协议已完成", "定值：多次独立运行；替换批相对现行批用预设统计评价。", "FDA 2023 效力草案 V.C.2"),
            ck("s4", "关键试剂数据表与批放行/桥接规则已建立", "", "ICH M10 §4.1.2（原则）"),
            ck("s5", "已确立条件（EC）与建议报告类别已分类", "", "ICH Q14 §6.1；ICH Q12"),
            ck("s6", "持续监控方案（控制图与规则）已定义", "", "ICH Q14 §6；FDA 2015 §VIII"),
            ck("s7", "分析程序描述足以让熟练分析员执行（步骤、重复数、计算公式）", "控制策略应在验证前定义、验证后确认。", "ICH Q14 §6"),
        ],
        "sections": [
            table("sst", "系统适用性（SST）", [
                col("item", "项目", "text", [], 150), col("criterion", "判据", "text", [], 190),
                col("risk", "检验的风险", "text", [], 170), col("action", "不合格处理", "text", [], 150)],
                "SST 的每个项目应对应一个 FMEA 风险；判据来自开发数据，而非仅取自文献。预置行为该技术常用项目，数值为示例。", True, 3, CH(None, "15.1")),
            text("sample_suitability", "样品适用性", "判据与不合格处理：样品响应是否满足预设标准（如活率、事件数、平行性、基质干扰），不合格时报告“不可评价”或复测的规则。",
                 True, "样品适用性：XX ≥ XX；两次重复差 ≤ XX；平行性判据见 XX。不合格：该样品结果无效，按规则复测一次，不得选择性取舍。", CH(None, "15.2")),
            table("references", "参比品与对照", [
                col("material", "材料", "text", [], 130), col("role", "用途", "text", [], 120), col("qualification", "鉴定/定值", "text", [], 210),
                col("stability", "稳定性", "text", [], 120), col("replacement", "替换协议", "text", [], 150)],
                "参比品须有来源、鉴定、定值方案、稳定性监测与替换批评价规则。", True, 1, CH(None, "15.3")),
            table("reagent_mgmt", "关键试剂管理", [
                col("reagent", "关键试剂", "text", [], 150), col("datasheet", "数据表要点", "text", [], 200),
                col("release", "批放行/验收测试", "text", [], 200), col("freq", "再确认频率", "text", [], 100),
                col("bridge", "变更/桥接规则", "text", [], 200)],
                "对关键性为“关键”的试剂逐一规定验收与再确认方式。", False, 0, CH(None, "15.4")),
            table("ecs", "已确立条件（EC）与建议报告类别", [
                col("element", "要素", "text", [], 190), col("risk", "风险", "select", ["高", "中", "低"], 70),
                col("category", "建议类别", "select", ["PA", "NM", "NL", "非EC"], 90), col("rationale", "理由", "text", [], 230)],
                "报告类别（PA/NM/NL）的实际定义以各区域规定及与监管机构的沟通为准；此处为内部建议。", False, 0, CH(None, "15.5")),
            text("trend", "持续监控方案", "控制图（对象、规则、控制限）、复核频率、年度回顾内容、触发调查的条件。",
                 False, "对 XX 与 XX 绘制控制图（个体值-移动极差），采用 Westgard 规则 1-3s、2-2s、4-1s、10x；每季度复核；SST 失败率与无效运行率纳入年度回顾。", CH(None, "15.6")),
        ],
    })
    # ---------------------------------------------------------------- 9 report
    S.append({
        "key": "report", "title": "预验证与开发报告", "weeks": 2,
        "gate": {"key": "G5", "name": "G5 进入验证批准", "roles": ["reviewer", "approver"],
                 "covers": ["explore", "robust", "control"]}, "requires": ["control"],
        "desc": "预验证演练、对照 ATP 的达成情况、SOP 草案、偏差与遗留问题、验证策略与经验教训。对应报告第 1、16–21 章及部分附注。",
        "checklist": [
            ck("g1", "预验证演练已完成：两名分析员按 SOP 草案全流程运行，SOP 可执行", "", ""),
            ck("g2", "SST 能拦截人为制造的失败（故意减量/降解/超时/参数偏离）", "", "ICH Q14 §6"),
            ck("g3", "开发结果与 ATP 逐项对照，未达标项有处置计划", "", ""),
            ck("g4", "验证策略与样本量依据已写明，判据来源于 ATP", "", "ICH Q2(R2) §2.1；§3"),
            ck("g5", "经验教训已记录（可写入知识库）", "", "", False),
            ck("g6", "方法描述草稿（SOP 草案）覆盖：原理、试剂、仪器、样品制备、设置、步骤、计算、可报告结果、SST", "", "FDA 2015 §IV.A–I（分析程序内容）"),
            ck("g7", "偏离清单完整，每项有影响评估与处置", "", "ICH Q14 §7", True),
            ck("g8", "遗留问题有负责人与期限；有条件进入验证时条件已写明", "", "", False),
            ck("g9", "风险再评估已完成并与 FMEA 一致；开发中使用的关键材料批号已记录", "", "ICH Q9(R1)", False),
        ],
        "sections": [
            text("summary", "开发结论摘要", "一页纸：方法是什么、做了哪些关键工作、主要结果、是否达到 ATP、关键限制、建议。数据数字要与正文一致。",
                 True, "本方法采用 XX 原理测定 XX。经 P0–P8 共 N 个实验，XX 性能特性达到 ATP，XX 部分达到，XX 未达到（处置：XX）。建议进入验证，条件：XX。", CH(None, "1.1")),
            fields("verdict", "结论性意见", [
                fld("overall", "对照 ATP 的总体结论", "select", ["全部达成", "部分达成（有处置计划）", "未达成"], "", True),
                fld("recommendation", "建议", "select", ["建议进入验证", "有条件进入验证", "需继续开发", "终止"], "", True),
                fld("conditions", "条件与限制", "textarea", [], "有条件进入验证时写清条件、负责人与期限"),
            ], "", True, CH(None, "1.2")),
            table("vs_atp", "对照 ATP 的达成情况", [
                col("characteristic", "性能特性", "text", [], 140), col("criterion", "ATP 判据", "text", [], 200),
                col("result", "开发结果", "text", [], 200), col("evidence", "证据/实验编号", "text", [], 120),
                col("met", "是否达成", "select", ["达成", "部分达成", "未达成", "待验证"], 90)],
                "逐条对照 ATP；“待验证”表示开发阶段无法完全证明、留待验证的项目（如中间精密度）。", True, 1, CH(None, "16.1")),
            text("sop_principle", "SOP 草案 1：原理与适用范围", "两三句：方法原理、测量对象、适用样品与范围；与 ATP 的关系。",
                 False, "本方法基于 XX 原理，测定 XX 样品中的 XX。适用范围：XX–XX；不适用：XX。", CH(None, "17.1")),
            text("sop_reagents", "SOP 草案 2：试剂、溶液与耗材", "列出试剂（名称/级别/来源/货号）、溶液配制（浓度/溶剂/配制步骤）、有效期与储存；关键试剂注明验收要求。",
                 False, "XX 缓冲液：称取 XX g，加水至 XX mL，pH 调至 XX，0.22 µm 过滤；2–8 ℃ 保存，有效期 XX 天。", CH(None, "17.2")),
            text("sop_instruments", "SOP 草案 3：仪器与设备", "列出仪器型号/配置、使用前确认与日常质控要求、软件与版本。",
                 False, "XX（型号 XX，配置 XX）；每日开机质控：XX；软件：XX 版本 XX。", CH(None, "17.3")),
            text("sop_settings", "SOP 草案 4：仪器设置与分析参数", "仪器与软件参数（电压/柱温/流速/循环程序/读数波长等）及门控/积分/拟合规则；参数与 PAR 一致。",
                 False, "参数 A：设定点 XX（PAR XX–XX）；参数 B：XX。", CH(None, "17.4")),
            text("sop_sample", "SOP 草案 5：样品制备", "样品处理的每一步（取样量、复苏、稀释、孵育、过滤等）及时限；保存时间限制。",
                 False, "取 XX µL 样品，加 XX 至终体积 XX；室温放置不超过 XX min；染色/处理前最长保存 XX h。", CH(None, "17.5")),
            text("sop_standards", "SOP 草案 6：对照品、参比品与标准溶液制备", "参比品/对照/标准曲线溶液的制备、使用与记录；注明批号管理与替换要求。",
                 False, "参比品 XX：复苏/稀释至 XX；每次运行平行制备 XX 份；批号记录于运行记录。", CH(None, "17.6")),
            text("sop_procedure", "SOP 草案 7：操作步骤", "按顺序编号列出每一步，写清数量、时间、温度与可接受的偏差，以及“停止点”。熟练分析员无需额外信息即可执行。",
                 True, "1. 开机质控并记录；2. 准备对照与样品（见 5、6）；3. XX（XX min，XX ℃）；4. XX；5. 采集/读数；6. 分析并记录。", CH(None, "17.7")),
            text("sop_calc", "SOP 草案 8：结果计算", "列出每个指标的公式（含分母）、拟合模型、平均/加权方式、修约规则、无效数据的判定。",
                 True, "指标 = 事件数 ÷ 分母 × 100；可报告结果 = 两个独立重复的算术平均；两重复差 > XX 判无效，复测一次。", CH(None, "17.8")),
            text("sop_reportable", "SOP 草案 9：可报告结果与判定", "写清可报告结果的定义（重复数、均值）、与规格比较的规则、复测规则、结果报告格式。",
                 False, "每样品 XX 个重复，取均值；与规格比较前不修约；结果以 XX 报告。", CH(None, "17.9")),
            text("sop_sst", "SOP 草案 10：SST 与接受标准", "列出 SST 项目、判据与不合格处理；样品适用性判据；运行有效性的总规则。",
                 True, "SST 见控制策略 15.1；全部 SST 通过且样品适用性满足 XX 时运行有效；任一失败运行无效，原因调查后重做。", CH(None, "17.10")),
            text("sop_notes", "SOP 草案 11：注意事项", "操作要点、已知陷阱（来自开发中的偏离与教训）、安全与废弃物处理。",
                 False, "注意：XX 步骤须避光；XX 试剂勿冻融超过 XX 次；开发中发现 XX 易引起 XX，需 XX。", CH(None, "17.11")),
            table("lots_used", "开发中使用的关键材料批号", [
                col("item", "材料", "text", [], 150), col("lot", "批号", "text", [], 100), col("expiry", "效期", "text", [], 90),
                col("coa", "CoA/数据表编号", "text", [], 130), col("used_in", "使用的实验/运行", "text", [], 180)],
                "记录关键试剂、参比品、对照的批号，便于追溯与桥接。", False, 0, CH(None, "9.4")),
            text("di_statement", "数据完整性评价", "说明开发数据如何保存与复核、是否有数据缺失/修改/排除、审计追踪审核情况。",
                 False, "开发数据均保存于 XX；抽查 XX% 的原始记录与报告数据一致；无未解释的数据排除；审计追踪于 XX 日审核，无异常。", CH(None, "18.4")),
            table("deviation_list", "偏离清单", [
                col("no", "编号", "text", [], 70), col("desc", "偏离描述", "text", [], 230), col("where", "发生阶段/实验", "text", [], 110),
                col("impact", "影响评估", "text", [], 190), col("disposition", "处置", "text", [], 160),
                col("status", "状态", "select", ["已关闭", "进行中", "转验证跟踪"], 90)],
                "汇总开发期所有偏离（含实验取消、材料替代、接受标准未达）。无偏离时写一行“无”。", True, 1, CH(None, "19.1")),
            text("deviations", "偏差与遗留问题说明", "对重大偏离作叙述性说明；对遗留问题说明为何可带入验证以及风险控制。",
                 False, "偏离 DEV-01：XX；根因：XX；已采取：XX；对结论的影响：XX。", CH(None, "19.2")),
            table("open_items", "遗留问题与后续行动", [
                col("item", "遗留问题", "text", [], 230), col("owner", "负责人", "text", [], 100), col("due", "期限", "date", [], 100),
                col("plan", "跟进计划", "text", [], 230), col("priority", "优先级", "select", ["高", "中", "低"], 70)],
                "", False, 0, CH(None, "20.1")),
            text("validation", "验证策略", "验证项目、样本量、统计方法、判据来源（均来自 ATP）；哪些开发数据可作为验证数据（如稳健性）；仍需在验证中补做的内容。",
                 True, "验证依据 ICH Q2(R2)：专属性/选择性、响应与范围、准确度、精密度、联合评价、定量下限、稳健性确认。核心实验：N 水平 × M 运行 × K 重复；判据来自 ATP。", CH(None, "20.2")),
            table("validation_matrix", "验证矩阵（建议）", [
                col("characteristic", "性能特性", "text", [], 130), col("design", "实验设计与样本量", "text", [], 260),
                col("levels", "样品/水平", "text", [], 160), col("basis", "判据来源/参考", "text", [], 180)],
                "给出验证的建议设计；数值为示例，须按 ATP 确认。已预置该技术的典型矩阵。", False, 0, CH(None, "20.3")),
            text("lessons", "经验教训", "做对了什么、踩过什么坑、下次怎么改；可通过“添加到知识库”沉淀。",
                 False, "做对：XX。踩坑：XX（原因：XX；以后：XX）。", CH(None, "20.4")),
            text("conclusion", "结论", "一段话：开发目标是否达成、方法是否可以进入验证、批准后的下一步。",
                 True, "XX 方法的开发已完成，对照 ATP 达成情况见第 16 章。建议批准进入验证（条件：XX）。", CH(None, "21.1")),
        ],
    })
    return S


# ====================================================================== technique presets
TECHNIQUES = {}

# ---------------------------------------------------------------------- flow
TECHNIQUES["flow"] = {
    "label": "流式细胞术（CAR-T 表达/表型）",
    "desc": "细胞产品流式检测：CAR 表达、表型、活率。含 CD19/CD22 双靶点案例经验（串色、FMO、事件数、保存时间、Fc 受体、WRM）。",
    "changelog": [
        "1.1：预置 CAR 双靶点案例的试剂/材料/仪器/初始条件、12 条 FMEA、11 个实验种子（含稀释线性与精密度预试验、SST 挑战）、8 条 ATP 判据、8 条 SST、验证矩阵",
        "1.1：新增检查项 fx10–fx18（事件数依据、正交读数、对照清单、滴定与交叉、门控规则、每个荧光标记、与效力测定接口）",
    ],
    "matrix": {"options": ["流式细胞术", "qPCR/ddPCR", "ELISA/WB"],
               "criteria": [("单细胞层面的阳性比例", 5), ("满足同一性（转基因+细胞组成）", 5), ("区分多靶点单阳与双阳", 5),
                            ("验证成熟度", 3), ("通量与周转", 3), ("每次成本", 2)]},
    "atp_rows": [
        ["准确度", "各水平（约 5%/20%/50%/80% 混合期望值）回收率或相对偏倚的 95% CI 与 ±15% 相容", "示例值，须按规格宽度与产品风险确认；准确度同时作为联合评价的组成", "ICH Q2(R2) §3.3.1"],
        ["精密度-重复性", "20%–80%：运行内 RSD ≤ 10%（每可报告结果 2 管均值）", "示例值，须按规格确认", "ICH Q2(R2) §3.3.2.1"],
        ["精密度-中间精密度", "20%–80%：RSD ≤ 15%；5%–20%：RSD ≤ 25%（95% CI 上限）", "低比例受计数统计限制（CV=√[(1−p)/(p·N)]）；示例值，须按规格确认", "ICH Q2(R2) §3.3.2.2；CAR 流式方案 V2.0 附录 B"],
        ["联合评价(总误差)", "各水平 90% β-期望容忍区间的相对误差全部落在 ±20% 内", "与规格宽度相容；联合评价比单独偏倚/精密度更严格；示例值", "ICH Q2(R2) §3.3.3"],
        ["线性/响应", "稀释系列（CAR+ 参比与 NTD 混合）测得值对期望值：斜率 95% CI 0.90–1.10，截距 95% CI 含 0，残差无趋势", "示例值", "ICH Q2(R2) §3.2.2.1"],
        ["专属性", "NTD 各 CAR 通道阳性 ≤ 1%；单靶参比在非目标通道 ≤ 背景+1 个百分点；过量游离抗原竞争抑制至背景；FMO 阈值与全染一致；Fc 封闭后背景不增加", "FDA 对照与滴定要求；示例值", "FDA 2024 CAR-T §IV.C.2.a；ICH Q2(R2) §3.1"],
        ["定量下限", "准确度谱仍满足 ±20% 的最低水平（初定 ≥ 5%，待数据确认）", "未通过的最低水平不被支持为 QL；示例值", "ICH Q2(R2) §3.2.3.4"],
        ["稳健性/稳定性", "PAR 边界及最长保存时限（染色前、染色至采集）处，相对中心点/0 h 变化 ≤ 10%（相对）", "示例值；保存时间是流式稳健性核心", "ICH Q14 §5.1；FDA 2024 CAR-T §IV.C.2.a.v"],
    ],
    "extra_checklist": {
        "atp": [
            ck("fx1", "分母已定义（活 CD3+ 等），并说明改变分母/门序/门位置视为方法变更", "", "FDA 2024 CAR-T §IV.C.2.a.i"),
            ck("fx2", "多通道/多靶点分别设判据与 LLOQ（不假设灵敏度相同）", "Spiegel 2021：双靶点 CAR 对不同靶点的效力可不同。", "Spiegel 等 Nat Med 2021", False),
            ck("fx10", "每管事件数与可报告结果重复数的依据已写（计数统计 CV 与低比例限制）", "N=10,000、p=5% 时纯计数 CV 已达 4.4%。", "二项分布计数误差（CAR 流式方案 V2.0 附录 B）"),
        ],
        "tech": [
            ck("fx3", "CAR 检测采用直接检测；若用 Protein L/代用标志，已规划相关性、灵敏度与特异性研究", "", "FDA 2024 CAR-T §IV.C.2.a.iv"),
            ck("fx4", "多个抗原不共用同一标签体系（如都生物素化再配不同链霉亲和素会串色）", "用直接荧光偶联的抗原，或互不相干的标签，并做单抗原单染与交叉实验。", "经验教训：V1 方案缺陷（项目内部）"),
            ck("fx5", "已评估 Fc 受体问题（人 IgG 类试剂的假阳性）与 Fc 封闭", "", "Sinapius 等 J Immunol Methods 2025", False),
            ck("fx11", "已规划用于准确度的正交/总 CAR 读数（抗独特型、抗 linker、分选后 PCR 校正等）", "混合研究只证明比例回收，不证明参比批赋值为真。", "ICH Q2(R2) §3.3.1.3", False),
        ],
        "risk": [ck("fx12", "已评估靶点密度差异、串色/溢出与补偿造成的假双阳风险", "", "CAR 流式方案 V2.0 §4、§5；FDA 2024 CAR-T §IV.C.2.a.i", False)],
        "plan": [
            ck("fx6", "已规划：抗原滴定、NTD/单靶交叉、竞争抑制、FMO、补偿、保存时间、事件数", "", "FDA 2024 CAR-T §IV.C.2.a"),
            ck("fx13", "对照清单（单染补偿、FMO、NTD/同型）与门控策略已写入方案；面板含活/死染料", "", "FDA 2024 CAR-T §IV.C.2.a.i"),
        ],
        "explore": [
            ck("fx14", "抗原滴定（染色指数）已完成，NTD 背景满足预设", "", "FDA 2024 CAR-T §IV.C.2.a.iii"),
            ck("fx15", "NTD、单靶参比交叉、竞争抑制、Fc 封闭对比已完成并满足判据", "", "ICH Q2(R2) §3.1；FDA 2024 CAR-T §IV.C.2.a.i", False),
        ],
        "robust": [
            ck("fx7", "已界定染色前与染色至采集间的最长保存时间", "", "FDA 2024 CAR-T §IV.C.2.a.v"),
            ck("fx16", "门控规则（阈值=NTD/FMO 百分位）已固定，自动门控与人工一致性已评价（如使用）", "", "CAR 流式方案 V2.0 §4.6、§6.5", False),
        ],
        "control": [
            ck("fx8", "工作参比品（WRM）≥20 次独立运行定值；控制图与 Westgard 规则已设定", "", "Cai 等 J Transl Med 2021；FDA 2023 效力草案 V.C.2"),
            ck("fx9", "仪器协调方案（标准微球、WRM 并排）已规划（多站点）", "", "FDA 2024 CAR-T §IV.E.3", False),
            ck("fx17", "面板中每个荧光标记（CD3/CD4/CD8/活死染料/各 CAR 通道）均有对应的 SST 与验证安排", "", "FDA 2024 CAR-T §IV.C.2.a.v"),
        ],
        "report": [ck("fx18", "已写明与各靶点特异效力测定的接口（多靶点须分别评估活性）", "本方法只证明结合域存在，不替代功能。", "FDA 2024 CAR-T §IV.C.2.d", False)],
    },
    "fmea": [
        F("两通道灵敏度不等", "抗原亲和力/荧光亮度不同", "CD22 与 CD19 信号不可比", 7, 5, 5, "各通道独立滴定与独立验证；SI 与 LLOQ 分通道设定；WRM 与单靶参比监控两通道比值"),
        F("双阳性误判", "补偿/门控/FMO 阈值", "错误的双阳比例", 8, 4, 5, "阈值由 NTD/FMO 统一规则；补偿矩阵版本控制；固定门控模板；双人复核；自动门控需验证"),
        F("检测试剂批次效价变化", "抗原/偶联物批间差", "系统性偏倚", 7, 5, 4, "批放行：并排滴定与 WRM 比较；双批过渡；数据表与寿命管理"),
        F("操作者差异", "加样/洗涤手法", "精密度变差", 5, 5, 5, "培训与资格评估；SOP 图示；分析员因子纳入验证；控制图按分析员分层"),
        F("Fc 受体结合致假阳性", "人 IgG 类试剂与 FcR 结合", "背景升高、假阳性", 7, 4, 4, "Fc 封闭；优选无 Fc 抗原；NTD 加/不加封闭对比"),
        F("数据计算/模板错误", "手工统计或模板错误", "错误结果", 7, 3, 5, "模板与计算验证；独立复核；版本控制"),
        F("背景升高", "洗涤不足/非特异结合", "NTD 假阳性升高、LLOQ 上移", 6, 4, 4, "洗涤次数与缓冲液规定；NTD 背景纳入 SST"),
        F("样品放置过久", "活率下降/表位丢失", "CAR+ 比例偏低", 6, 5, 3, "稳定性研究规定染色前/后最长时限；SOP 与记录核对"),
        F("仪器漂移", "激光/检测器性能变化", "灵敏度变化", 6, 3, 4, "每日质控微球；趋势；维护与校准计划"),
        F("WRM 复苏后质量下降", "冻融/运输/操作", "控制图误报警或漏报", 6, 3, 4, "复苏程序与活率判据；多批库存；定期稳定性"),
        F("双抗原同管竞争或位阻", "两种抗原结合域空间位阻", "双阳比例被低估", 6, 3, 4, "同管 vs 单染对比；差异 ≤ 判据"),
        F("事件数不足", "活率低或每管细胞数不足", "低比例结果精密度差", 6, 4, 3, "每管 ≥ 设定事件数写入 SST；样品适用性判据；增加采集或判“不可评价”"),
    ],
    "experiments": [
        X("P0", "材料与可行性", "确认材料可用、仪器合格，方法在最简单对比（NTD vs 单靶参比）上可行",
          "NTD ≥ 3 个供者；单靶参比（CD19-only、CD22-only）；产品样品 ≥ 3 批；抗原试剂 ≥ 2 批；仪器 IQ/OQ/PQ 与每日 QC；每条件 2 管",
          S_("NTD 各 CAR 通道阳性 ≤ 2%；单靶参比阳性/阴性群 SI ≥ 5；双靶点样品出现预期双阳群。未达标则回到试剂选择（技术选择阶段）。"), "explore", 1),
        X("P1", "抗原滴定", "为每个抗原试剂确定工作浓度",
          "8 点 3 倍稀释（10 → 0.0046 µg/mL），NTD 与对应单靶参比各 2 管；SI=(MFI+ − MFI−)/(2×SD−)；饱和结合模型拟合；每通道独立",
          S_("选用 SI ≥ 最大值 90% 且阳性信号 ≥ 80% Bmax 的最低浓度；NTD 背景 ≤ 1%。"), "explore", 2),
        X("P1b", "专属性初筛：交叉/竞争/Fc/同管", "证明各通道特异且互不干扰",
          "CD19-only × CD22 抗原、CD22-only × CD19 抗原、NTD × 双抗原；染色前加 10–100 倍未标记抗原；Fc 封闭 ±；同管 vs 单染；抗原 2 批并排；每条件 2 管 × 3 次独立运行",
          S_("非目标通道阳性 ≤ NTD 背景 + 1 个百分点；竞争抑制至 NTD 背景；同管与单染 CAR+ % 差 ≤ 3 个百分点；两批抗原差 ≤ 3 个百分点。"), "explore", 1),
        X("P2", "面板优化与补偿", "确定电压、溢出扩展矩阵（SSM）、补偿与 FMO 阈值规则",
          "电压滴定；单染（微球/细胞）；每个 CAR 通道的 FMO；全面板 vs 仅 CAR 通道单染；n=3 次独立运行",
          S_("全面板与单染 CAR+ % 差 ≤ 3 个百分点；FMO 阈值与 NTD 全染一致。"), "explore", 1),
        X("P3", "样品条件与保存稳定性", "确定染色条件及染色前/染色后最长保存时间",
          "染色前（4 ℃/室温）0、2、4、8、24 h；染色后未固定 0、1、2、4、6、24 h；固定 0、4、24、48 h；复苏后静置 0–120 min；3 批样品 × 2 管",
          S_("相对 0 h 变化 ≤ 10%（相对）；时限取满足判据的最长时间的 75%。"), "robust", 2),
        X("P4", "门控规则与事件数", "固定门序与阈值规则；确定每管采集事件数",
          "NTD/FMO 99.9 百分位阈值，≥ 3 个供者；自动 vs 人工门控一致性：≥ 30 个样品（含不同 CAR+ 水平），Bland-Altman；5,000/10,000/20,000 事件对精密度的影响",
          S_("Bland-Altman 平均差与一致性界限在预设内；选定事件数使 5% 水平纯计数 CV 与 ATP 精密度判据相容。"), "explore", 1),
        X("P4b", "稀释线性与范围预试验", "初步评价响应线性与范围",
          "已赋值参比批（CAR+ ≥ 65%）与 NTD 按 5%、10%、25%、50%、75%、90%、100% 混合；每水平 3 次独立制备 × 2 管；分通道回归",
          S_("斜率 95% CI 0.90–1.10；截距 95% CI 含 0；残差无趋势。"), "explore", 1),
        X("P4c", "精密度与准确度预试验", "初步评价重复性、中间精密度与准确度谱",
          "4 个水平（≈5%、20%、50%、80%）× 3 个运行（≥ 2 天、2 名分析员）× 2 管；ANOVA 方差分量；90% β-期望容忍区间",
          S_("20%–80% 中间精密度 RSD ≤ 15%，5%–20% ≤ 25%；各水平相对误差在 ±20% 内。未通过的最低水平不作 QL，上移报告范围下限或增加事件数/重复后复验。"), "robust", 2),
        X("P5", "DoE 稳健性与参数范围", "找出关键参数，确定 PAR/MODR",
          "2^(5−2) 部分因子 8 次 + 3 个中心点（因子：CD19 抗原浓度、CD22 抗原浓度、孵育时间、温度、每管细胞数）；运行随机化并分块到不同天/分析员；Lenth 分析与曲率检验",
          S_("关键因子确定；PAR 内 CAR+ % 相对中心点变化 ≤ 3 个百分点、SI ≥ 5、NTD 背景 ≤ 1%。"), "robust", 2),
        X("P6", "工作参比品（WRM）建立与定值", "建立并定值内部参比品",
          "代表性成品批冻存分装；随机 6 瓶分装均一性；≥ 20 次独立运行 / ≥ 5 天 / ≥ 2 名分析员定值；复苏后室温 0–6 h；0/3/6/12 个月稳定性",
          S_("分装 RSD ≤ 5%；复苏 6 h 变化 ≤ 10%；给出均值、SD 与 ±2SD/±3SD 控制限；替换批并行 ≥ 6 次独立运行，均值落在预设等效范围内。"), "control", 4),
        X("P7", "SST 判据与挑战", "由开发数据定 SST 判据，并检验 SST 能拦截人为失败",
          "故意制造 4 类失败：抗原剂量减半、抗原降解/过期、电压偏离 ±15%、染色后超时；各 3 次运行；与正常运行比较",
          S_("4 类故意失败均被 SST 拦截或使运行无效；未被拦截者调整 SST 项目与判据后重做。"), "control", 1),
        X("P8", "预验证演练", "两名分析员按 SOP 草案全流程运行",
          "各 3 次独立运行，使用 WRM、NTD、单靶参比、3 个样品；评估 SOP 清晰度、时间与资源",
          S_("SOP 可执行；SST 拦截全部故意失败；偏差清单闭合；形成 G5 决策。"), "report", 1),
    ],
    "sst": [
        ["质控微球 CV / MFI", "在内部限度内", "仪器漂移", "校准；不得采集"],
        ["补偿矩阵版本与溢出", "与基线一致；FMO 无异常溢出", "补偿错误致双阳性误判", "重做补偿"],
        ["NTD 背景（各 CAR 通道）", "≤ 1.0%", "背景、污染、非特异", "调查；重做"],
        ["单靶参比交叉检查", "非目标通道 ≤ NTD 背景 + 1 个百分点", "交叉反应、串染", "调查试剂"],
        ["WRM 各指标", "均值 ±2SD 内；Westgard 规则不触发", "试剂批次/操作/仪器", "调查；必要时重做"],
        ["各通道阳性对照 SI", "≥ 预设值（如 5）", "试剂效价、灵敏度", "调查抗原/偶联物"],
        ["活 CD3+ 事件数", "≥ 10,000 / 管", "计数统计精度", "增加采集；否则报告不可评价"],
        ["染色前/后保存时间", "在验证的最长时限内", "保存导致的偏倚", "超时则无效"],
    ],
    "ph": {
        "atp.use": "测定自体 CAR-T 成品（冻存复苏后或新鲜）活 CD3+ T 细胞中 CD19-CAR+、CD22-CAR+、双阳性与总 CAR+ 的百分比；用于放行、稳定性与过程控制；可在多个站点执行；适用阶段：XX。",
        "atp.attribute": "属性：活 CD3+ T 细胞中 CAR 结合域阳性百分比（CD19-CAR、CD22-CAR、双阳、总 CAR+）。规格（预期）：总 CAR+ ≥ 20%（由工艺能力与临床数据确定）。关联：CAR 结合域存在是同一性与靶向能力的前提；本属性不替代各靶点效力测定（FDA 2024 §IV.C.2.d）。",
        "atp.specificity": "需排除：NTD 背景、单靶 CAR 参比在非目标通道的交叉、Fc 受体非特异结合、补偿/溢出造成的假双阳。对照：NTD、单靶参比、FMO、竞争抑制。",
        "atp.sampling": "冻存成品复苏后 ≤ XX min 内染色；新鲜成品 4 ℃ 保存 ≤ XX h；染色前与染色至采集的最长保存时间由稳定性研究确定（FDA 2024 §IV.C.2.a.v）；冻融仅 1 次。",
        "tech.principle": "CAR-T 细胞经 Fc 封闭后，与直接荧光偶联的靶抗原胞外域（CD19-ECD–PE、CD22-ECD–APC）孵育，抗原通过 CAR 的相应 scFv 结合于细胞表面；再加入 CD3/CD4/CD8 抗体与固定型活/死染料，洗涤后采集。分析时先排除碎片、双联体与死细胞，在活 CD3+ T 细胞中以 NTD/FMO 确定的阈值划分象限，得到单阳、双阳与总 CAR+ 比例。",
        "plan.strategy": "先在 NTD 与单靶参比上验证可行性（P0），再滴定两种抗原并做交叉/竞争/Fc 封闭（P1、P1b）；随后优化电压、补偿与 FMO（P2）、确定门控规则与事件数（P4）；条件固定后做稀释线性与精密度预试验（P4b、P4c）、保存稳定性（P3）和 DoE（P5）；WRM 定值（P6）与 SST 挑战（P7）后做预验证（P8）。",
        "plan.statistics": "滴定：饱和结合模型 MFI+ = Bmax·c/(Kd+c)+b；线性：最小二乘，斜率/截距 95% CI；精密度：ANOVA 方差分量；联合评价：90% β-期望容忍区间（统计人员核对）；稳定性：相对 0 h 的 TOST 或回归斜率 CI；DoE：Lenth 伪标准误+曲率；门控一致性：Bland-Altman。软件及版本：XX。",
        "plan.sample_size": "NTD ≥ 3 个供者；产品样品 ≥ 3 批；稀释线性 7 水平 × 3 制备；精密度预试验 4 水平 × 3 运行 × 2 管；WRM 定值 ≥ 20 次独立运行 / ≥ 5 天 / ≥ 2 名分析员；事件数依据 CV=√[(1−p)/(p·N)]（N=10,000、p=5% 时纯计数 CV≈4.4%）。",
        "plan.decision_rules": "滴定：选 SI 达最大值 90% 以上且信号近平台的最低浓度，同时 NTD 背景 ≤ 1%；任一通道交叉 > 背景+1 个百分点则回到试剂选择；阈值只由 NTD/FMO 百分位规则决定，不得用肉眼调整。",
        "report.sop_sample": "冻存成品：37 ℃ 水浴快速复苏，洗涤去除冻存液，计数并记录活率；调整至 1×10^6 活细胞/100 µL；复苏后 ≤ XX min 内染色；新鲜样品 4 ℃ 保存 ≤ XX h。",
        "report.sop_settings": "仪器：XX 色流式细胞仪；电压按电压滴定确定并用质控微球目标 MFI 每日复现；补偿：每次运行用单染计算并保存矩阵（版本 XX）；阈值：NTD/FMO 99.9 百分位；采集：每管 ≥ 10,000 活 CD3+ 事件。",
        "report.sop_procedure": "1. 运行质控微球并记录；2. 复苏样品并计数（记录活率）；3. Fc 封闭 10 min（4 ℃）；4. 加 CD19/CD22 荧光偶联抗原与 CD3/CD4/CD8 抗体，4 ℃ 避光 30 min；5. 洗涤 2 次（PBS+2% FBS）；6. 加固定型活/死染料；7. 在染色后时限内上机采集；8. 套用门控模板，NTD/FMO 设阈值；9. 导出结果并记录模板/软件版本。",
        "report.sop_calc": "分母为活 CD3+ T 细胞。CD19-CAR+ % = [CD19+ 事件数（含单阳与双阳）÷ 活 CD3+ 事件数]×100；CD22-CAR+ % 同理；双阳 % = [CD19+ 且 CD22+ ÷ 活 CD3+]×100；总 CAR+ % = [CD19+ 或 CD22+ ÷ 活 CD3+]×100。可报告结果 = 2 个独立染色管的算术平均；两管差 > XX 个百分点判无效，复测一次。",
        "report.sop_sst": "SST 项目见 15.1：质控微球、补偿版本、NTD 背景、单靶参比交叉、WRM（均值±2SD；Westgard）、阳性对照 SI、活 CD3+ 事件数 ≥ XX、保存时间。样品适用性：活率 ≥ XX%，两管差 ≤ XX。任一失败则运行无效。",
    },
    "seeds": {
        "charter.glossary": [
            ["CAR", "Chimeric Antigen Receptor 嵌合抗原受体", "由胞外抗原结合域（scFv）、铰链/跨膜区与胞内信号域构成。"],
            ["NTD", "Non-Transduced 非转导 T 细胞", "同供者/同工艺、未转导 CAR 的 T 细胞，用于设定背景与阈值。"],
            ["FMO", "Fluorescence Minus One", "缺少某一荧光抗体、其余全染的对照，用于确定荧光溢出与门控边界。"],
            ["MFI / SI", "中位荧光强度 / 染色指数", "SI=(MFI+ − MFI−)/(2×SD−)，衡量阳性群与阴性群的分离。"],
            ["WRM", "Working Reference Material 工作参比品", "冻存的代表性 CAR-T 成品或类似材料，用于定值、SST、趋势与桥接。"],
            ["SSM", "Spillover Spreading Matrix 溢出扩展矩阵", "评价各检测器因其他染料溢出而增加的扩展，用于面板设计。"],
            ["scFv / ECD", "单链可变片段 / 胞外域", "CAR 的抗原结合域；重组靶抗原的胞外域。"],
            ["门控 / 分母", "Gating / Denominator", "按固定门序界定细胞群；本方法分母为活 CD3+ T 细胞，修改分母/门序/门位置视为方法变更。"],
            ["PBMC", "外周血单个核细胞", "NTD 与对照细胞的常见来源。"],
        ],
        "charter.refdocs": [
            ["法规/指南", "FDA Considerations for the Development of Chimeric Antigen Receptor (CAR) T Cell Products", "FDA CBER，最终版，2024-01", "§IV.C.2.a 流式；§IV.C.2.b VCN；§IV.C.2.d 效力；§IV.E.3 多站点检测"],
            ["法规/指南", "FDA Potency Assurance for Cellular and Gene Therapy Products", "FDA CBER，草案，2023-12（是否已定稿待核对）", "V.C 检测控制、参比物质与变更；V.D 验收标准"],
            ["法规/指南", "FDA Chemistry, Manufacturing, and Control (CMC) Information for Human Gene Therapy Investigational New Drug Applications (INDs)", "FDA CBER，2020-01", "分析方法在 IND 阶段的资料要求"],
            ["药典", "Ph.Eur. 2.7.24 Flow cytometry", "现行版（版本待核对）", "流式细胞术通则"],
            ["行业标准", "CLSI H62 Validation of Assays Performed by Flow Cytometry", "（版本待核对；原文未取得）", "流式检测验证的行业做法"],
            ["文献", "O'Hara DM 等. Recommendations for the validation of flow cytometric testing during drug development: II assays", "J Immunol Methods 2011", "流式检测验证建议"],
            ["文献", "Selliah N 等. Flow Cytometry Method Validation Protocols", "Curr Protoc 2018", "验证方案示例"],
            ["文献", "Brown L 等. Recommendations for the evaluation of specimen stability for flow cytometric testing during drug development", "J Immunol Methods 2015", "样品稳定性评价路线"],
            ["文献", "Cossarizza A 等. Guidelines for the use of flow cytometry and cell sorting in immunological studies (third edition)", "Eur J Immunol 2021", "对照、门控、面板设计"],
            ["文献", "Schanda N 等. Sensitivity and Specificity of CD19.CAR-T Cell Detection by Flow Cytometry and PCR", "Cells 2021", "CAR 检测试剂背景比较"],
            ["文献", "Sinapius R 等. CAR binding efficacy and off-target interactions for common CAR detection reagents", "J Immunol Methods 2025", "Protein L 与 Fc 受体问题"],
            ["文献", "Cai Y-H 等. Establishment and validation of in-house cryopreserved CAR/TCR-T cell flow cytometry quality control", "J Transl Med 2021", "工作参比品（WRM）建立"],
            ["文献", "Spiegel JY 等. CAR T cells with dual targeting of CD19 and CD22 in adult patients with recurrent or refractory B cell malignancies: a phase 1 trial", "Nat Med 2021", "双靶点 CAR 对不同靶点效力不等"],
        ],
        "tech.conditions": [
            ["样品", "样品类型", "冻存成品复苏后 / 新鲜成品", "两者分别评价", "FDA 对放行样品形态的要求；两种形态分别验证"],
            ["样品", "每管细胞数", "1×10^6 活细胞 / 100 µL", "0.5、1、2×10^6", "CAR 案例起始值；DoE 因子"],
            ["样品", "复苏后静置", "立即染色", "0–120 min", "对活率与 CAR+ % 的影响待评价"],
            ["反应/染色/孵育", "Fc 封闭", "10 min，4 ℃，不洗涤直接加抗原", "有/无；封闭试剂浓度", "Sinapius 2025：人 IgG 类试剂与 FcR 结合致假阳性"],
            ["试剂/溶液", "靶抗原浓度（CD19 / CD22）", "由滴定确定（初值示例：1–2 µg/mL）", "8 点 3 倍稀释", "FDA 要求抗体滴定；分通道独立"],
            ["反应/染色/孵育", "抗原孵育", "30 min，4 ℃，避光", "15–45 min；2–6 ℃ / 室温", "DoE 因子"],
            ["反应/染色/孵育", "表型抗体（CD3/CD4/CD8）", "与抗原同管孵育", "同管 / 分步", "对 CAR 信号的影响待评价"],
            ["反应/染色/孵育", "洗涤", "2 次，PBS + 2% FBS", "次数；缓冲液", "背景控制"],
            ["试剂/溶液", "活/死染料", "固定型，按说明", "染色顺序", "FDA：面板须含活/死染料"],
            ["反应/染色/孵育", "固定", "不固定（待比较）", "固定 / 不固定", "影响 CAR 信号与染色后保存时限"],
            ["仪器/检测", "激光与通道", "405/488/561/640 nm；CAR 用 PE、APC 类亮染料", "—", "亮染料给低密度靶点"],
            ["仪器/检测", "电压", "电压滴定法确定", "—", "阴性群与电子噪声分离的最低电压"],
            ["仪器/检测", "补偿/光谱展开", "每次运行单染对照", "—", "矩阵版本化"],
            ["仪器/检测", "采集事件数", "≥ 10,000 活 CD3+ / 管", "5,000–50,000", "计数统计：CV=√[(1−p)/(p·N)]"],
            ["数据处理", "分母与阈值规则", "活 CD3+；NTD/FMO 99.9 百分位", "—", "FDA：改变分母/门序/门位置视为方法变更"],
            ["保存/稳定性", "最长保存时间", "待 P3 确定", "染色前 0–24 h；染色后 0–48 h", "FDA 2024 §IV.C.2.a.v"],
        ],
        "tech.reagents": [
            ["CD19 胞外域抗原（荧光偶联，如 PE）", "检测 CD19 结合域", "自制/定制或商品化", "关键", "批间效价与标记比变化；Fc 融合型致 FcR 结合", "数据表+批放行（并排滴定、WRM 比较）；优选无 Fc"],
            ["CD22 胞外域抗原（荧光偶联，如 APC）", "检测 CD22 结合域", "自制/定制或商品化", "关键", "同上；亲和力不同致灵敏度不等", "分通道滴定与放行"],
            ["CD3 / CD4 / CD8 抗体", "T 细胞门控、表型", "商品化", "重要", "克隆/荧光染料批间差", "滴定；批号记录；验证每个荧光标记"],
            ["固定型活/死染料", "排除死细胞", "商品化", "重要", "染色时间/浓度影响", "按说明；纳入 SST（活率）"],
            ["Fc 封闭试剂", "抑制 FcR 结合", "商品化", "重要", "封闭不足致假阳性", "NTD 加/不加封闭对比"],
            ["质控微球 / 补偿微球", "仪器质控、补偿", "商品化", "重要", "批间 MFI 变化", "批放行；趋势"],
            ["NTD（非转导 T 细胞）", "背景与阈值", "同供者/同工艺", "关键", "供者间差异", "≥ 3 供者；统一阈值规则"],
            ["单靶 CAR 参比（CD19-only、CD22-only）", "交叉反应、SST", "工程细胞系/分选原代细胞", "关键", "表达漂移", "冻存分装；定期复测"],
            ["工作参比品（WRM）", "SST、趋势、桥接", "代表性成品冻存", "关键", "复苏后质量下降", "多批库存；稳定性监测"],
            ["染色缓冲液（PBS + 2% FBS）", "洗涤/稀释", "自配或商品化", "一般", "血清批次", "批验收"],
        ],
        "plan.materials": [
            ["CD19-ECD 抗原（荧光偶联）", "试剂", "", "", "", "关键", "批放行并排滴定；每 6 个月复测效价", "待采购"],
            ["CD22-ECD 抗原（荧光偶联）", "试剂", "", "", "", "关键", "同上", "待采购"],
            ["CD3 / CD4 / CD8 抗体", "试剂", "", "", "", "重要", "新批并排滴定", "待采购"],
            ["固定型活/死染料", "试剂", "", "", "", "重要", "开封后有效期按说明", "待采购"],
            ["Fc 封闭试剂", "试剂", "", "", "", "重要", "新批对比 NTD 背景", "待采购"],
            ["NTD（≥ 3 供者）", "对照", "", "", "", "关键", "每批复苏后活率 ≥ 判据", "待采购"],
            ["单靶 CAR 参比（CD19-only、CD22-only）", "参比品/标准品", "", "", "", "关键", "每次使用前核对阳性比例", "待采购"],
            ["工作参比品（WRM）", "参比品/标准品", "", "", "", "关键", "按稳定性方案与控制图", "待采购"],
            ["质控微球 / 补偿微球", "耗材", "", "", "", "重要", "批验收", "待采购"],
            ["染色缓冲液（PBS + 2% FBS）", "溶液/缓冲液", "", "", "", "一般", "每批配制记录", "待采购"],
            ["流式管/板、移液器吸头", "耗材", "", "", "", "一般", "—", "待采购"],
        ],
        "plan.instruments": [
            ["多激光流式细胞仪", "≥ 4 激光（405/488/561/640 nm），≥ 8 色；放行拟用型号", "染色样品采集", "待确认", "IQ/OQ/PQ；每日质控微球；年度校准与预防性维护", ""],
            ["自动细胞计数仪", "荧光/台盼蓝双模式", "细胞计数与活率", "待确认", "每日/每次使用前校准核对", ""],
            ["气相液氮罐与干式运输罐", "—", "WRM、参比、样品储存与运输", "待确认", "液位与温度监测；运输温度记录", ""],
            ["生物安全柜", "II 级", "细胞处理", "待确认", "年度检定", ""],
            ["离心机、移液器、水浴", "—", "样品处理", "校准有效", "按设备校准计划", ""],
        ],
        "plan.software": [
            ["流式采集软件", "（填写）", "数据采集与应用设置", "待验证", "开启"],
            ["流式分析软件", "（填写）", "门控与导出（模板受控）", "待验证", "开启"],
            ["统计软件", "（填写）", "线性/方差分量/容忍区间/TOST", "待验证", "不适用"],
            ["受控计算模板（Excel/脚本）", "（填写）", "可报告结果计算", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["冻存成品（复苏后）", "CAR-T 成品，≥ 3 批，覆盖低/中/高 CAR+ %", "气相液氮；复苏后立即处理", "复苏后 ≤ XX min 内染色", "放行样品形态；稳定性、精密度、准确度"],
            ["新鲜成品", "新鲜 CAR-T 成品", "4 ℃", "≤ XX h", "新鲜放行样品形态"],
            ["NTD", "同供者/同工艺非转导 T 细胞，≥ 3 供者", "冻存或新鲜，同产品", "同产品", "背景、阈值、稀释线性基质"],
            ["单靶 CAR 参比", "CD19-only、CD22-only", "冻存分装", "复苏后 ≤ XX min", "交叉、SST"],
            ["混合样品（稀释系列）", "已赋值参比批与 NTD 按比例混合", "新鲜配制", "配制后立即染色", "线性、范围、准确度谱"],
            ["WRM", "工作参比品", "气相液氮", "复苏后室温 ≤ 6 h（待确认）", "SST、控制图、桥接"],
        ],
        "risk.ishikawa": [
            ["样品", "供者间差异；冻存/复苏损失；活率低；细胞数不足", "准确度；精密度；LLOQ", "活率判据；复苏程序；样品适用性"],
            ["试剂与材料", "抗原效价与标记比批间差；荧光衰减；Fc 融合致 FcR 结合；抗体克隆批差", "灵敏度；专属性；偏倚", "批放行并排滴定；Fc 封闭；数据表与寿命管理"],
            ["仪器", "激光/检测器漂移；电压设置；补偿矩阵；流速", "灵敏度；精密度", "每日质控微球；电压滴定；矩阵版本控制"],
            ["方法", "孵育时间/温度；洗涤；固定；门控序列与阈值；事件数", "精密度；专属性；双阳性误判", "DoE 确定 PAR；固定门控规则；NTD/FMO 阈值"],
            ["人员与分析", "加样/洗涤手法；门控主观性；数据转录", "精密度；准确度", "培训与资格；模板固定；双人复核"],
            ["环境与流程", "染色前/后保存时间；避光；温度；批内运行顺序", "稳定性；偏倚", "最长时限写入 SOP；随机化运行顺序"],
        ],
        "robust.factors": [
            ["A  CD19 抗原浓度", "−20%", "滴定最佳浓度", "+20%", "滴定结果设定；FMEA 两通道灵敏度风险"],
            ["B  CD22 抗原浓度", "−20%", "滴定最佳浓度", "+20%", "同上"],
            ["C  抗原孵育时间", "25 min", "30 min", "35 min", "实际操作时间波动范围"],
            ["D  孵育温度", "2 ℃", "4 ℃", "6 ℃", "冰浴/冰箱波动范围"],
            ["E  每管细胞数", "0.8×10^6", "1.0×10^6", "1.2×10^6", "须明确同时改变体积或固定体积"],
        ],
        "robust.par": [
            ["CD19 / CD22 抗原浓度", "滴定最佳浓度", "待 DoE 确定", "实验编号 P5"],
            ["抗原孵育时间", "30 min", "待 DoE 确定", "实验编号 P5"],
            ["每管细胞数", "1×10^6", "待 DoE 确定", "实验编号 P5"],
        ],
        "robust.stability": [
            ["染色前保存（样品）", "4 ℃ 与室温", "0、2、4、8、24 h", "", ""],
            ["染色后保存（未固定）", "4 ℃ 避光", "0、1、2、4、6、24 h", "", ""],
            ["染色后保存（固定）", "4 ℃ 避光", "0、4、24、48 h", "", ""],
            ["冻存样品复苏后静置", "室温", "0、30、60、120 min", "", ""],
            ["抗原工作液/原液", "4 ℃ / −20 或 −80 ℃", "0、1、4、12 周", "", ""],
            ["WRM 复苏后", "室温", "0–6 h", "", ""],
        ],
        "control.references": [
            ["NTD", "背景、阈值、阴性对照", "≥ 3 供者；同工艺；活率 ≥ 判据", "每批复苏后核对", "新供者批并行评价背景"],
            ["单靶 CAR 参比（CD19-only / CD22-only）", "交叉反应、各通道 SST", "阳性比例已赋值；表达稳定性监测", "冻存分装；定期复测", "新批与现行批并行 ≥ 6 次运行"],
            ["工作参比品（WRM）", "SST、控制图、桥接", "≥ 20 次独立运行 / ≥ 5 天 / ≥ 2 分析员定值", "复苏后 6 h；储存 0/3/6/12 个月", "新批与现行批并行 ≥ 6 次运行，预设等效范围"],
            ["质控微球", "仪器日常质控", "目标 MFI 与 CV 来自基线运行", "按批效期", "新批对比旧批"],
        ],
        "control.reagent_mgmt": [
            ["CD19 / CD22 抗原", "身份、来源、批号、纯度、Fc 有无、标签、荧光染料及标记比、浓度、稳定性", "并排滴定 + WRM 比较；各通道 CAR+ % 差 ≤ 3 个百分点（示例）", "每 6 个月复测效价", "同类换供应商做桥接；类型变更按较大变更评估"],
            ["CD3 / CD4 / CD8 抗体", "克隆、荧光染料、浓度", "新批并排滴定", "每批", "克隆变更须重新验证该标记"],
            ["固定型活/死染料", "货号、批号、有效期", "活率对照", "每批", "—"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据会影响对 CQA 的控制"],
            ["技术原理（流式，直接结合域检测）", "高", "PA", "换为 Protein L/其他试剂属原理变更，需桥接与相关性证明"],
            ["检测试剂种类（抗原类型）", "中", "NM", "同类换供应商做桥接"],
            ["门控分母与阈值规则", "高", "PA", "直接决定结果；FDA：分母/门序/门位置修改视为方法变更"],
            ["SST 与样品适用性判据", "中", "NM", "由控制策略证明性能"],
            ["关键参数设定点与 PAR（细胞数、孵育时间等）", "中", "NM", "DoE 证明；PAR 内变动不通知"],
            ["最长保存时限", "中", "NM", "直接影响结果"],
            ["洗涤体积、管型号等次要参数", "低", "NL", "开发数据显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性/选择性", "NTD（≥ 3 供者）、单靶参比、交叉、竞争抑制、FMO、Fc 封闭、杂细胞干扰、同管 vs 单染", "3 个供者 NTD；2 个单靶参比；1–2 个样品", "ICH Q2(R2) §3.1；FDA 2024 §IV.C.2.a" + SAMPLE_TAG],
            ["响应与范围", "稀释系列（参比与 NTD 混合）7 水平 × 3 重复，分通道", "5%–100%", "ICH Q2(R2) §3.2" + SAMPLE_TAG],
            ["准确度 / 精密度 / 联合评价", "核心实验：4 水平 × 6 运行（3 天 × 2 分析员）× 2 管；方差分量；90% β-期望容忍区间", "≈5%、20%、50%、80%", "ICH Q2(R2) §3.3.1–3.3.3" + SAMPLE_TAG],
            ["定量下限", "核心实验最低水平准确度谱；近 QL 水平", "≈5%", "ICH Q2(R2) §3.2.3.4" + SAMPLE_TAG],
            ["正交比较", "不同原理读数（抗独特型/抗 linker/PCR 校正）对 ≥ 20 样品，Bland-Altman + Deming 回归", "≥ 20 个不同批次/水平", "ICH Q2(R2) §3.3.1.3" + SAMPLE_TAG],
            ["稳健性/保存时限", "PAR 边界与最长保存时限处 WRM + 2 个样品各 ≥ 6 次", "WRM + 2 样品", "ICH Q14 §5.1；FDA 2024 §IV.C.2.a.v" + SAMPLE_TAG],
            ["SST 有效性", "4 类故意失败应被拦截", "WRM", "ICH Q14 §6" + SAMPLE_TAG],
            ["每个荧光标记", "CD3、CD4、CD8、活/死、CD19 通道、CD22 通道各自的精密度与专属性", "同核心实验", "FDA 2024 §IV.C.2.a.v" + SAMPLE_TAG],
            ["仪器间/站点间（如适用）", "同批样品在各台仪器检测；转移用 TOST 等效性", "3 批 × 各仪器 ≥ 6 重复", "FDA 2024 §IV.E.3" + SAMPLE_TAG],
        ],
    },
}


# ---------------------------------------------------------------------- hplc
TECHNIQUES["hplc"] = {
    "label": "色谱方法（HPLC/CE/GC：含量、纯度、杂质）",
    "desc": "分离方法：专属性、强制降解、稳定性指示、峰纯度、杂质定量、积分规则、SST。",
    "changelog": [
        "1.1：预置色谱条件表、对照品/杂质对照品/色谱柱等关键材料、12 条 FMEA、11 个实验种子（强降解、峰纯度、RRF、回收率、LOQ、溶液稳定性、DoE）、SST 与验证矩阵",
        "1.1：新增检查项 hx5–hx12（积分规则、RRF、对照品赋值、溶液稳定性、质量平衡、柱批次、仪器间延迟体积、报告阈值依据）",
    ],
    "matrix": {"options": ["RP-HPLC-UV/PDA", "HPLC-CAD/MS", "CE", "GC"],
               "criteria": [("专属性/分离度", 5), ("灵敏度/QL", 4), ("稳健性", 4), ("稳定性指示能力", 5), ("验证成熟度", 3), ("通量", 2), ("成本", 2)]},
    "atp_rows": [
        ["准确度", "含量：80%/100%/120% 水平回收率均值 98.0%–102.0%；杂质：QL–120% 规格水平回收率 80%–120%", "示例值，须按规格宽度确认", "ICH Q2(R2) §3.3.1；Table 3"],
        ["精密度-重复性", "含量：100% 水平 6 次或 3 水平 × 3 次，RSD ≤ 1.0%；杂质：规格水平 RSD ≤ 5%，QL 水平 ≤ 15%", "示例值，须按规格确认；设计与 Table 3 一致", "ICH Q2(R2) §3.3.2.1；Table 3"],
        ["精密度-中间精密度", "不同日期/分析员/仪器/色谱柱批：含量 RSD ≤ 2.0%；杂质 RSD ≤ 10%", "示例值", "ICH Q2(R2) §3.3.2.2"],
        ["联合评价(总误差)", "含量/杂质各水平准确度与精密度合并的总误差落在规格宽度允许的范围内（β-期望容忍区间）", "示例；规格越窄，判据越严", "ICH Q2(R2) §3.3.3"],
        ["线性/响应", "≥ 5 个水平覆盖报告范围；残差无趋势；含量 r ≥ 0.999（示例）；杂质可用校正模型/RRF", "示例值", "ICH Q2(R2) §3.2.2.1"],
        ["专属性", "空白、安慰剂、已知杂质无干扰；强降解样品主峰纯度合格；关键峰对分离度 Rs ≥ 1.5", "稳定性指示；示例值", "ICH Q2(R2) §3.1；§2.4；Table 3"],
        ["定量下限", "QL ≤ 报告阈值；QL 水平 S/N ≥ 10 且准确度/精密度满足判据", "示例值；QL 须低于报告阈值", "ICH Q2(R2) §3.2.3"],
        ["稳健性/稳定性", "柱批次、pH ±0.2、有机相 ±2%（绝对）、柱温 ±5 ℃、流速 ±10%、波长 ±2 nm 下 SST 通过；样品与标准液在时限内变化 ≤ 2.0%", "示例值；稳健性在开发阶段完成", "ICH Q14 §5.1；ICH Q2(R2) §3.4"],
    ],
    "extra_checklist": {
        "atp": [
            ck("hx1", "杂质：报告阈值与 QL 要求已写明（QL ≤ 报告阈值），阈值依据已记录", "化学药参见 ICH Q3A/Q3B；生物制品纯度/变体参见 ICH Q6B。", "ICH Q2(R2) §3.2.3；ICH Q3A(R2)/Q3B(R2)（条款待核对）"),
            ck("hx12", "含量/杂质规格宽度与方法总误差相容性已评估", "", "ICH Q2(R2) §3.3.3", False),
        ],
        "tech": [
            ck("hx2", "是否需要稳定性指示方法，强降解方案已规划", "", "ICH Q2(R2) §2.4；FDA 2015 §VI"),
            ck("hx5", "对照品/杂质对照品的来源、纯度、含水量与赋值方式已规定", "对照品赋值错误会系统性偏倚。", "FDA 2015 §V（参比标准与材料）"),
        ],
        "risk": [ck("hx7", "已评估杂质共洗脱、RRF、残留、溶剂效应与吸附风险", "", "ICH Q14 §4.2", False)],
        "plan": [
            ck("hx6", "积分规则（基线、阈值、最小峰面积、手动积分限制）已在方案中预先规定", "手动积分须有理由并留痕。", "FDA 数据完整性问答（2018）"),
            ck("hx8", "强降解方案（酸/碱/氧化/热/光、目标降解范围）与峰纯度判定方法已写明", "目标降解范围按产品而定（示例 5%–20%）。", "ICH Q2(R2) §2.4；ICH Q1B（光稳定性，条款待核对）"),
        ],
        "explore": [ck("hx9", "强降解样品的主峰纯度与质量平衡已评价", "", "ICH Q2(R2) §3.1.2；FDA 2015 §VI", False)],
        "robust": [
            ck("hx3", "稳健性参数含：柱批次、流动相组成/pH、柱温、流速、波长、制备物稳定性；相对响应因子偏离 0.8–1.2 时已校正", "", "ICH Q2(R2) Table 3；ICH Q14 §5.1"),
            ck("hx10", "样品溶液与标准溶液稳定性已评价并确定时限", "", "ICH Q14 §5.1"),
        ],
        "control": [
            ck("hx4", "SST：分离度、拖尾、理论塔板、重复进样 RSD、灵敏度（S/N）", "", "ICH Q14 §6"),
            ck("hx11", "多仪器使用时已评估延迟体积差异并规定补偿方式", "", "USP <621> 色谱通则（条款待核对）", False),
        ],
        "report": [],
    },
    "fmea": [
        F("柱批次/品牌差异", "固定相批间差", "分离度与保留时间变化", 6, 5, 4, "柱筛选与 ≥ 2 批柱评价；SST 分离度判据"),
        F("流动相 pH/组成偏差", "配制误差、缓冲盐变化", "保留时间漂移、选择性变化", 5, 5, 3, "配制 SOP；pH 范围纳入稳健性；SST"),
        F("样品制备稳定性不足", "降解/吸附", "含量偏低、杂质偏高", 7, 4, 5, "溶液稳定性研究；规定制备后最长保存时间"),
        F("积分参数主观性", "手动积分/基线选择", "杂质结果变异", 7, 4, 5, "预先规定积分规则；手动积分需理由并留痕；审计追踪审核"),
        F("杂质共洗脱/峰纯度不足", "选择性不足", "杂质低估、专属性不足", 8, 3, 4, "强降解+PDA/MS 峰纯度；关键峰对分离度 SST"),
        F("对照品纯度/含水量/赋值错误", "赋值方法不当、吸湿", "系统性偏倚", 8, 3, 4, "对照品鉴定与赋值方案；干燥/称量规程；双人核对"),
        F("相对响应因子未校正", "杂质与主成分响应不同", "杂质低估", 7, 4, 5, "RRF 测定（0.8–1.2 范围外校正）"),
        F("系统残留", "进样器/柱残留", "基线干扰、假杂质", 6, 3, 3, "空白进样；SST 空白判据；针洗程序"),
        F("样品稀释剂与流动相不匹配", "溶剂强度差", "峰形畸变、分离度下降", 5, 4, 3, "稀释剂筛选；进样量上限"),
        F("检测器饱和/线性范围不足", "高浓度主峰", "含量低估", 6, 3, 4, "线性范围覆盖；稀释方案"),
        F("过滤器/容器吸附", "低浓度杂质吸附", "杂质损失", 6, 3, 5, "滤膜/容器相容性（弃初滤液）研究"),
        F("仪器间延迟体积差异", "梯度延迟体积不同", "转移后选择性变化", 6, 4, 4, "记录延迟体积；梯度补偿说明；转移时比较"),
    ],
    "experiments": [
        X("P0", "方法筛选与可行性", "确定色谱条件雏形（柱、流动相、梯度、检测）",
          "2–3 种固定相 × 2 种流动相/pH；梯度筛选；对照品、杂质对照品、空白、安慰剂各进样 2 针",
          S_("主峰与已知杂质分离（Rs ≥ 1.5）；空白与安慰剂无干扰；主峰拖尾因子 ≤ 2.0。"), "explore", 2),
        X("P1", "强制降解与专属性", "证明方法稳定性指示及峰纯度",
          "酸、碱、氧化、热、光（目标降解 5%–20%）各 1 个条件 + 未处理对照；PDA 峰纯度（必要时 MS）；质量平衡；每条件 2 份",
          S_("降解产物与主峰分离；主峰纯度角 < 纯度阈值；质量平衡 95%–105%；关键峰对 Rs ≥ 1.5。"), "explore", 2),
        X("P2", "条件优化与积分规则", "优化梯度、柱温、pH 并固定积分规则",
          "单因素或小型 DoE 优化；积分参数（斜率、阈值、最小峰面积、基线）在代表性色谱图上评价；2 名分析员独立积分",
          S_("关键峰对 Rs ≥ 1.5；两名分析员积分结果差 ≤ 判据；积分规则书面化。"), "explore", 1),
        X("P3", "线性、范围与相对响应因子", "确定响应模型、范围与杂质 RRF",
          "≥ 5 个水平覆盖报告范围（含量 80%–120%；杂质 QL–120% 规格水平），每水平 3 次独立制备；杂质与主成分斜率比得 RRF",
          S_("含量 r ≥ 0.999，残差无趋势，截距 95% CI 含 0；RRF 在 0.8–1.2 内或已校正。"), "explore", 1),
        X("P4", "准确度（加标回收）", "初步评价含量/杂质准确度",
          "含量：80%/100%/120% 水平 × 3 次独立制备；杂质：QL、规格、120% 规格水平加标 × 3；与正交方法（如 LC-MS 或另一色谱条件）比较（适用时）",
          S_("含量回收率均值 98.0%–102.0%；杂质回收率 80%–120%。"), "robust", 1),
        X("P5", "精密度（重复性与中间精密度）", "估计重复性与中间精密度",
          "重复性：100% 水平 6 次或 3 水平 × 3 次；中间精密度：2 天 × 2 分析员 × 2 仪器/柱批，ANOVA 方差分量",
          S_("含量重复性 RSD ≤ 1.0%、中间精密度 RSD ≤ 2.0%；杂质规格水平 RSD ≤ 5% / 10%。"), "robust", 2),
        X("P6", "定量下限与检测限", "确定 QL/LOD",
          "逐级稀释；QL 水平 n=6 评价准确度与精密度；S/N 辅助",
          S_("QL ≤ 报告阈值；QL 水平 S/N ≥ 10，回收率 80%–120%，RSD ≤ 15%。"), "robust", 1),
        X("P7", "溶液稳定性", "确定样品溶液与标准溶液的保存时限",
          "室温与自动进样器（5 ℃）0、8、24、48、72 h；与新鲜配制比较；n=3",
          S_("含量变化 ≤ 2.0%；杂质增加 ≤ 判据；时限取实测可接受最长时间的 75%。"), "robust", 1),
        X("P8", "DoE 稳健性", "确定关键参数及 PAR",
          "因子：缓冲液 pH、有机相比例/梯度斜率、柱温、流速、波长、柱批次；Plackett-Burman 或部分因子 + 中心点；响应：Rs、拖尾、保留时间、含量/杂质",
          S_("关键参数确定；PAR 内 SST 全部通过且含量变化 ≤ 判据。"), "robust", 3),
        X("P9", "SST 判据与挑战", "由开发数据定 SST，并检验其拦截能力",
          "故意制造：柱老化/更换低效柱、流动相 pH 偏离 0.3、有机相偏离 3%、对照品降解；各 3 次",
          S_("SST（分离度、拖尾、重复进样 RSD、S/N）能拦截全部故意失败。"), "control", 1),
        X("P10", "对照品鉴定与赋值", "建立工作对照品及杂质对照品赋值",
          "对照品含量赋值（质量平衡或 qNMR 等）；与参比对照品比较；稳定性监测方案",
          S_("工作对照品赋值不确定度已评估；与参比差异在判据内。"), "control", 2),
        X("P11", "预验证演练", "两名分析员按 SOP 草案运行",
          "各 3 次独立运行，覆盖含量/杂质/SST；评估 SOP 清晰度",
          S_("SOP 可执行；SST 拦截全部故意失败；偏差闭合。"), "report", 1),
    ],
    "sst": [
        ["分离度（关键峰对）", "Rs ≥ 判据（示例 1.5）", "选择性", "停止；调查柱/流动相"],
        ["拖尾因子 / 理论塔板数", "Tf ≤ 判据；N ≥ 判据", "柱状态", "更换柱"],
        ["重复进样 RSD（对照品 n=5/6）", "≤ 判据（示例 1.0%）", "系统精密度", "排查进样器/泵"],
        ["灵敏度（QL 溶液 S/N）", "S/N ≥ 10（示例）", "灵敏度", "调查检测器/溶液"],
        ["空白进样", "关键位置无干扰峰（< QL）", "残留/污染", "清洗；重做"],
        ["对照品回收/标准溶液核对", "与前次核对差 ≤ 2.0%（示例）", "对照品赋值/配制", "重配"],
    ],
    "ph": {
        "atp.use": "测定 XX 原料药/制剂中 XX 的含量及相关物质（杂质）；用于放行与稳定性；要求具稳定性指示能力；适用阶段 XX。",
        "atp.attribute": "含量规格 XX%–XX%；杂质：单个未知杂质 ≤ XX%、总杂质 ≤ XX%，报告阈值 XX%（依据 ICH Q3A/Q3B 或产品规格）。关联：含量决定剂量；杂质关乎安全性。",
        "atp.specificity": "空白溶剂、安慰剂、已知杂质、强降解样品（酸/碱/氧化/热/光）中主峰与杂质峰须分离，无共洗脱；用 PDA 峰纯度和/或 MS 证明。",
        "atp.sampling": "样品称取量/取样代表性：XX；溶液配制后室温/自动进样器保存不超过 XX h；避光要求：XX。",
        "tech.principle": "样品经稀释剂溶解后，在 XX 色谱柱上以 XX 流动相梯度洗脱，XX nm 检测。含量用外标法（工作对照品）定量；杂质按面积归一并以相对响应因子校正；分离度与峰纯度保证稳定性指示能力。",
        "plan.strategy": "先筛选固定相/流动相获得雏形（P0），再强制降解证明专属性（P1），固定积分规则（P2）；随后线性/RRF（P3）、LOQ（P6）、溶液稳定性（P7）；条件固定后做回收率与精密度预试验（P4、P5）和 DoE（P8）；对照品赋值（P10）与 SST 挑战（P9）后预验证（P11）。",
        "plan.statistics": "线性：最小二乘，残差；RRF：斜率比及 CI；回收率：均值与 95% CI；精密度：ANOVA 方差分量，RSD 及 95% CI；稳健性：DoE 主效应/交互 + 响应；稳定性：相对初始值的变化与 TOST。软件及版本：XX（色谱数据系统版本 XX）。",
        "plan.sample_size": "线性每水平 3 次独立制备 ≥ 5 水平；回收率 3 水平 × 3 次；精密度 6 次或 3×3，中间精密度 2 天 × 2 分析员 × 2 仪器/柱批；强降解每条件 2 份。设计与 ICH Q2(R2) Table 3 对应。",
        "plan.decision_rules": "关键峰对 Rs < 1.5 回到条件优化；强降解主峰纯度不合格则更换选择性（柱/流动相/检测）；积分规则在看数据前书面化，不得为改善结果而改变。",
        "report.sop_sample": "称取 XX mg，加稀释剂 XX 溶解并定容至 XX mL，超声 XX min；经 0.45 µm 滤膜（弃初滤液 XX mL）；制备后 ≤ XX h 内进样，自动进样器 5 ℃。",
        "report.sop_settings": "色谱柱：XX；流动相 A/B：XX；梯度：XX；流速 XX mL/min；柱温 XX ℃；检测 XX nm；进样 XX µL；运行时间 XX min；积分：斜率 XX，最小峰面积 XX，基线按 XX 规则。",
        "report.sop_procedure": "1. 配制流动相并平衡系统；2. 配制对照品溶液、系统适用性溶液、样品溶液；3. 运行空白、SST 溶液（n=XX）；4. 通过 SST 后依序进样样品与括号标准；5. 积分（按规定规则）；6. 记录色谱图、积分参数与审计追踪。",
        "report.sop_calc": "含量 % = (A样 / A标) × (W标 / W样) × (稀释倍数) × P标 ×100（外标法）；杂质 % = (A杂 / ΣA) × (1/RRF) × 100；报告至 XX 位小数，规格比较前不修约。",
        "report.sop_sst": "系统适用性：关键峰对 Rs ≥ XX；拖尾 ≤ XX；N ≥ XX；对照品重复进样 RSD ≤ XX%（n=XX）；QL 溶液 S/N ≥ 10；空白无干扰。任一不合格则本次运行无效。",
    },
    "seeds": {
        "charter.glossary": [
            ["Rs / Tf / N", "分离度 / 拖尾因子 / 理论塔板数", "色谱系统适用性参数。"],
            ["RRT / RRF", "相对保留时间 / 相对响应因子", "RRF=杂质斜率/主成分斜率；偏离 0.8–1.2 时需校正（ICH Q2(R2) Table 3）。"],
            ["PDA / 峰纯度", "二极管阵列检测 / Peak purity", "判断主峰是否含共洗脱物。"],
            ["强制降解", "Forced degradation", "在应力条件（酸/碱/氧化/热/光）下产生降解物，用于证明稳定性指示能力。"],
            ["质量平衡", "Mass balance", "主成分损失与降解产物增加之和相对初始量的平衡程度。"],
            ["报告/鉴定/确认阈值", "Reporting / Identification / Qualification threshold", "杂质管理阈值（化学药见 ICH Q3A/Q3B）。"],
            ["S/N", "信噪比", "用于 QL/LOD 辅助评价。"],
            ["稳定性指示", "Stability-indicating", "能区分主成分与降解产物，并随降解检出含量/杂质变化。"],
        ],
        "charter.refdocs": [
            ["药典", "USP <621> Chromatography", "USP–NF 现行版（条款待核对）", "色谱系统适用性、允许调整范围"],
            ["药典", "Ph.Eur. 2.2.46 Chromatographic separation techniques", "现行版（版本待核对）", "色谱 SST 与调整"],
            ["药典", "《中国药典》通则 0512 高效液相色谱法", "现行版（章节号待核对）", "高效液相色谱通则"],
            ["法规/指南", "ICH Q3A(R2) Impurities in New Drug Substances；ICH Q3B(R2) Impurities in New Drug Products", "ICH（条款待核对）", "杂质报告/鉴定/确认阈值"],
            ["法规/指南", "ICH Q1B Photostability Testing of New Drug Substances and Products", "ICH（条款待核对）", "光降解条件"],
            ["法规/指南", "ICH Q6B Specifications: Test Procedures and Acceptance Criteria for Biotechnological/Biological Products", "ICH（适用于蛋白质 CE/SEC 等，条款待核对）", "生物制品纯度与变体"],
        ],
        "tech.conditions": [
            ["仪器/检测", "色谱柱", "C18，150×4.6 mm，3.5 µm（示例）", "2–3 种固定相；≥ 2 批", "文献/平台方法"],
            ["试剂/溶液", "流动相 A", "XX mM 缓冲盐，pH XX", "pH ±0.2", "pKa 与保留行为"],
            ["试剂/溶液", "流动相 B", "乙腈或甲醇", "有机相 ±2%（绝对）", "选择性与背压"],
            ["仪器/检测", "梯度", "初始 5% B → 60% B / 20 min（示例）", "斜率；起始 %B", "筛选结果"],
            ["仪器/检测", "流速", "1.0 mL/min", "±10%", "柱规格与背压"],
            ["仪器/检测", "柱温", "30 ℃", "±5 ℃", "保留重现性"],
            ["仪器/检测", "检测波长", "XX nm（UV/PDA）", "±2 nm", "最大吸收；杂质响应"],
            ["样品", "进样量", "10 µL", "5–20 µL", "峰形与灵敏度"],
            ["样品", "样品浓度与稀释剂", "XX mg/mL；稀释剂 XX", "溶剂强度", "溶解性与峰形"],
            ["样品", "自动进样器温度", "5 ℃", "—", "溶液稳定性"],
            ["数据处理", "积分参数", "斜率 XX；最小峰面积 XX；基线规则 XX", "—", "P2 评价；预先书面化"],
            ["保存/稳定性", "溶液稳定性时限", "待 P7 确定", "0–72 h", "ICH Q14 §5.1"],
        ],
        "tech.reagents": [
            ["工作对照品（主成分）", "外标定量", "官方/自制并赋值", "关键", "纯度/含水量赋值错误", "鉴定与赋值方案；干燥/称量规程；稳定性监测"],
            ["杂质对照品", "杂质鉴定与 RRF", "供应商/自制", "关键", "稳定性差、纯度不明", "鉴定与保存条件；复验期"],
            ["色谱柱（≥ 2 批）", "分离", "供应商", "关键", "批间选择性差异", "柱筛选与批间评估；SST 分离度"],
            ["缓冲盐与有机溶剂（HPLC 级）", "流动相", "试剂供应商", "重要", "杂质/批间差", "供应商/批号记录；空白检查"],
            ["稀释剂/样品溶剂", "溶解", "自配", "重要", "溶剂强度、稳定性", "稀释剂筛选；配制 SOP"],
            ["滤膜/样品瓶", "样品前处理", "供应商", "重要", "吸附", "相容性研究"],
        ],
        "plan.materials": [
            ["工作对照品（主成分）", "参比品/标准品", "", "", "", "关键", "按赋值方案；稳定性监测", "待采购"],
            ["杂质对照品", "参比品/标准品", "", "", "", "关键", "复验期内使用", "待采购"],
            ["色谱柱（批 1、批 2）", "耗材", "", "", "", "关键", "每批柱登记并跟踪使用次数", "待采购"],
            ["缓冲盐、乙腈/甲醇（HPLC 级）", "试剂", "", "", "", "重要", "每批记录批号", "待采购"],
            ["稀释剂/流动相溶液", "溶液/缓冲液", "", "", "", "重要", "按配制有效期", "待采购"],
            ["滤膜、样品瓶、针头滤器", "耗材", "", "", "", "一般", "—", "待采购"],
            ["强降解试剂（酸/碱/氧化剂）", "试剂", "", "", "", "一般", "新配制", "待采购"],
        ],
        "plan.instruments": [
            ["HPLC/UHPLC 系统（含 PDA/UV 检测器）", "泵、自动进样器、柱温箱、PDA", "含量/杂质分析", "待确认", "IQ/OQ/PQ；年度校准（流量、柱温、波长、线性）", ""],
            ["质谱检测器（如需）", "—", "峰鉴定/纯度", "待确认", "按仪器计划", ""],
            ["分析天平", "0.01 mg 级", "称量对照品/样品", "校准有效", "每日核对；年度校准", ""],
            ["pH 计、纯水系统、超声仪", "—", "流动相与样品制备", "校准有效", "按设备计划", ""],
            ["光稳定性箱、烘箱", "—", "强制降解", "待确认", "温度/辐照度确认", ""],
        ],
        "plan.software": [
            ["色谱数据系统（CDS）", "（填写）", "采集、积分、结果计算", "待验证", "开启"],
            ["统计软件", "（填写）", "线性/方差分量/DoE", "待验证", "不适用"],
            ["受控计算模板", "（填写）", "含量/杂质/RRF 计算", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["原料药/制剂（≥ 3 批）", "覆盖不同批次与杂质水平", "按产品稳定性条件", "溶液 ≤ XX h", "准确度、精密度、稳定性"],
            ["空白与安慰剂", "稀释剂；制剂辅料混合物", "室温", "—", "专属性（无干扰）"],
            ["已知杂质加标样品", "含杂质对照品", "按杂质稳定性", "—", "准确度、LOQ、RRF"],
            ["强降解样品", "酸/碱/氧化/热/光", "避光冷藏", "按降解后稳定性", "专属性、峰纯度、质量平衡"],
            ["稳定性留样/老化样品", "加速/长期稳定性样品（如有）", "按稳定性条件", "—", "杂质谱代表性"],
        ],
        "risk.ishikawa": [
            ["样品", "溶解度/吸附；制备稳定性；辅料干扰", "准确度；专属性", "稀释剂筛选；溶液稳定性；安慰剂对照"],
            ["试剂与材料", "对照品赋值；杂质对照品稳定性；柱批差异；溶剂/缓冲盐批差", "偏倚；选择性", "对照品鉴定；≥ 2 批柱；批号记录"],
            ["仪器", "延迟体积；泵/混合；柱温稳定性；检测器线性与波长精度；残留", "保留时间；峰形；灵敏度", "校准；延迟体积记录；空白进样"],
            ["方法", "梯度、pH、柱温、流速；积分规则；稀释剂", "分离度；杂质定量", "DoE；积分规则书面化；SST"],
            ["人员与分析", "称量/稀释误差；手动积分；数据转录", "精密度；杂质结果", "培训；积分规则；双人复核；审计追踪"],
            ["环境与流程", "光照/温度（降解）；自动进样器停留时间", "溶液稳定性", "避光；稳定性时限"],
        ],
        "robust.factors": [
            ["A  流动相 pH", "−0.2", "设定值", "+0.2", "pKa 邻近，对保留影响大"],
            ["B  有机相比例/梯度斜率", "−2%（绝对）", "设定值", "+2%（绝对）", "选择性与分离度"],
            ["C  柱温", "−5 ℃", "设定值", "+5 ℃", "保留与选择性"],
            ["D  流速", "−10%", "设定值", "+10%", "保留时间与背压"],
            ["E  检测波长", "−2 nm", "设定值", "+2 nm", "响应因子"],
            ["F  色谱柱批次（类别）", "批 1", "批 2", "批 3", "固定相批间差"],
        ],
        "robust.par": [
            ["流动相 pH", "设定值", "待 DoE 确定", "实验编号 P8"],
            ["柱温", "设定值", "待 DoE 确定", "实验编号 P8"],
            ["梯度/有机相比例", "设定值", "待 DoE 确定", "实验编号 P8"],
        ],
        "robust.stability": [
            ["样品溶液（室温）", "室温，避光/不避光", "0、8、24、48 h", "", ""],
            ["样品溶液（自动进样器）", "5 ℃", "0、24、48、72 h", "", ""],
            ["标准溶液", "室温 / 2–8 ℃", "0、24、48、72 h；1 周", "", ""],
            ["流动相", "室温", "0、24、72 h", "", ""],
            ["工作对照品（固体）", "按储存条件", "复验期", "", ""],
        ],
        "control.references": [
            ["工作对照品（主成分）", "含量定量", "赋值（质量平衡/qNMR/与官方对照品比较）", "按复验期复验", "新批与现行批并行比较"],
            ["杂质对照品", "杂质鉴定、RRF、系统适用性溶液", "鉴定与纯度；RRF 测定", "复验期", "新批并行比较"],
            ["系统适用性溶液", "分离度、拖尾", "含主成分与关键杂质", "按溶液稳定性", "每次新配制"],
        ],
        "control.reagent_mgmt": [
            ["色谱柱", "品牌、型号、填料批号、使用次数", "新柱 SST 与柱效测试", "每批新柱", "更换品牌/型号视为较大变更"],
            ["工作对照品", "来源、含量/水分赋值、复验期", "与前批比较", "复验期", "新批与现行批并行"],
            ["缓冲盐/有机溶剂", "级别、批号", "空白检查", "每批", "更换供应商需空白与 SST 确认"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据影响对质量的控制"],
            ["分离机理/技术（RP-HPLC / 检测原理）", "高", "PA", "原理变更需重新验证"],
            ["色谱柱（固定相类型）", "中", "NM", "同类替换需分离度确认"],
            ["流动相组成/梯度/pH 设定点与 PAR", "中", "NM", "DoE 证明 PAR；PAR 内不通知"],
            ["SST 判据", "中", "NM", "控制策略证明性能"],
            ["积分规则", "高", "NM", "直接决定杂质结果"],
            ["溶液稳定性时限", "中", "NM", "直接影响结果"],
            ["流速、进样量（小幅）", "低", "NL", "稳健性显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性", "空白、安慰剂、杂质加标、强降解样品；PDA 峰纯度/MS；质量平衡", "代表性批 + 强降解样品", "ICH Q2(R2) §3.1，§2.4，Table 3" + SAMPLE_TAG],
            ["响应与范围", "≥ 5 水平覆盖报告范围，每水平 ≥ 3 次独立制备", "含量 80%–120%；杂质 QL–120% 规格", "ICH Q2(R2) §3.2" + SAMPLE_TAG],
            ["准确度", "含量 3 水平 × 3；杂质 3 水平加标 × 3；与正交方法比较（适用时）", "80%/100%/120%", "ICH Q2(R2) §3.3.1，Table 3" + SAMPLE_TAG],
            ["重复性", "100% 水平 6 次或 3 水平 × 3 次", "—", "ICH Q2(R2) §3.3.2.1，Table 3" + SAMPLE_TAG],
            ["中间精密度", "不同日期/分析员/仪器/柱批", "—", "ICH Q2(R2) §3.3.2.2" + SAMPLE_TAG],
            ["定量下限 / 检测限", "QL 水平 n=6；S/N 辅助", "QL", "ICH Q2(R2) §3.2.3" + SAMPLE_TAG],
            ["稳健性（确认）", "PAR 边界下 SST 与结果", "代表性批", "ICH Q14 §5.1；ICH Q2(R2) §3.4" + SAMPLE_TAG],
            ["溶液稳定性", "时限处确认", "样品/标准溶液", "ICH Q14 §5.1" + SAMPLE_TAG],
        ],
    },
}

# ---------------------------------------------------------------------- bioassay
TECHNIQUES["bioassay"] = {
    "label": "生物活性测定（相对效力：4PL / 平行线，蛋白药物）",
    "desc": "相对效力测定：参比品、剂量-反应曲线、平行性/相似性、板设计与随机化、PAR。参考 ICH Q14 Annex A 抗 TNF-α 效力示例与 USP <1032–1034>。",
    "changelog": [
        "1.1：预置相对效力 ATP 判据（含平行性）、12 条 FMEA、11 个实验种子（曲线模型、参比品、板设计、强降解、线性、准确度、精密度、DoE、SST/样品适用性挑战）、SST 与样品适用性判据示例",
        "1.1：新增检查项 bx5–bx11（统计模型与权重、平行性检验方式、参比品、板设计、重复与独立制备、效力水平数、统计软件）",
    ],
    "matrix": {"options": ["细胞增殖/中和", "结合法（ELISA/SPR）", "报告基因"],
               "criteria": [("与作用机制的相关性", 5), ("精密度", 4), ("稳定性指示能力", 4), ("验证成熟度", 3), ("通量", 2), ("成本", 2)]},
    "atp_rows": [
        ["准确度", "各效力水平（如 50%/71%/100%/141%/200%）相对偏倚的 90% CI 上下限均不超过 ±20%；理论 vs 测得效力回归斜率 95% CI 在 0.8–1.25；相对偏倚无趋势", "沿用 ICH Q14 Annex A 示例；示例值，须按产品确认", "ICH Q14 Annex A Table 4；ICH Q2(R2) Table 7"],
        ["精密度-重复性", "同一天/短时间内，≥ 5 个效力水平 × ≥ 3 重复，几何 CV ≤ 15%", "示例值；设计与 Q2(R2) Table 7 一致", "ICH Q2(R2) Table 7"],
        ["精密度-中间精密度", "跨水平平均中间精密度（几何 CV）的 95% CI 上限 ≤ 20%", "沿用 Q14 示例；示例值", "ICH Q14 Annex A Table 4"],
        ["联合评价(总误差)", "各水平相对误差的 90% 容忍区间在 ±25% 内", "示例值，须与规格宽度相容", "ICH Q2(R2) §3.3.3"],
        ["线性/响应", "参比与样品剂量-反应曲线呈 S 形，r² ≥ 0.97（示例）；理论 vs 测得相对效力对数线性", "沿用 Q14 SST 示例；示例值", "ICH Q2(R2) §3.2.2.2；ICH Q14 Annex A"],
        ["专属性", "对作用机制特异；基质与过程杂质不干扰；强降解样品能检出效力或曲线形状改变", "稳定性指示", "ICH Q2(R2) Table 7；ICH Q14 Annex A"],
        ["定量下限", "报告范围 = 规格 −20% 至 +20%（例：规格 80%–125% → 64%–150%）且在范围两端满足准确度与精密度", "示例；范围是由规格推导的", "ICH Q2(R2) §2.3；Table 7"],
        ["稳健性/稳定性", "板型、缓冲液、孵育条件、仪器、试剂批次（含对照）、细胞密度、效应/靶细胞比、细胞代数的合理变动下 SST 通过且相对效力变化 ≤ 10%", "示例值", "ICH Q2(R2) Table 7；ICH Q14 §5.1"],
        ["其他", "平行性（样品适用性）：上渐近线比、下渐近线比、斜率比、(D−A) 比均在 0.8–1.2 内，或采用等效性检验", "沿用 Q14 样品适用性示例；示例值，须按产品确认", "ICH Q14 Annex A；USP <1034>（条款待核对）"],
    ],
    "extra_checklist": {
        "atp": [
            ck("bx1", "报告范围 = 规格范围 −20% / +20%（效力）", "例：规格 80–125% → 64–150%。", "ICH Q2(R2) §2.3、Table 2；ICH Q14 Annex A"),
            ck("bx5", "效力水平数与重复数设计满足 Q2(R2) 表 7（≥ 5 水平、≥ 3 重复/独立制备）", "", "ICH Q2(R2) Table 7", False),
        ],
        "tech": [
            ck("bx2", "已确定曲线模型（4PL/5PL 或平行线）与相似性/平行性判据", "", "ICH Q14 Annex A；USP <1034>（条款待核对）"),
            ck("bx6", "平行性判据的统计方式已决定（差异检验 vs 等效性检验）及其理由", "", "USP <1034>（条款待核对）", False),
        ],
        "risk": [ck("bx7", "已评估板边缘效应、细胞状态、参比品、稀释误差的风险", "", "ICH Q14 Annex A 石川图示例", False)],
        "plan": [
            ck("bx8", "板布局（随机化/区组）、稀释方案、重复与独立制备次数已写明", "", "USP <1032>（条款待核对）"),
            ck("bx9", "统计模型、权重、异常值规则、软件与版本已在看数据前写定", "", "USP <1034>；Ph.Eur. 5.3（条款待核对）"),
        ],
        "robust": [ck("bx3", "稳健性含：板、缓冲液、孵育、仪器、试剂批次、细胞密度、效靶比、细胞代数", "", "ICH Q2(R2) Table 7")],
        "control": [
            ck("bx4", "内部参比品、SST 控制材料与替换批协议已建立；定量验收标准不接受“仅报告”", "", "FDA 2023 效力草案 V.C.2、V.D"),
            ck("bx10", "SST 与样品适用性判据来自开发数据（曲线质量、信号窗口、渐近线/斜率比）", "", "ICH Q14 §6；Annex A"),
        ],
        "report": [ck("bx11", "验证设计已按 Q2(R2) 表 7 规划（重复性、中间精密度、准确度、范围）", "", "ICH Q2(R2) Table 7", False)],
    },
    "fmea": [
        F("细胞状态/代数漂移", "传代与培养条件", "信号窗口变化、EC50 漂移", 7, 5, 4, "细胞库；代数限制；SST 信号窗口"),
        F("参比品变质或批变更", "冻融/储存/替换", "相对效力偏倚", 8, 3, 4, "参比品稳定性与替换协议；控制图"),
        F("曲线不平行", "样品基质/降解/异常样品", "效力误判", 7, 4, 4, "样品适用性判据；平行性检验"),
        F("板边缘效应", "温度/蒸发", "变异增大", 5, 5, 3, "板布局随机化；边缘孔不用或加缓冲液；SST"),
        F("稀释误差", "移液/梯度稀释", "斜率/EC50 偏倚", 7, 4, 4, "稀释方案验证；多人复核；独立稀释制备"),
        F("刺激物/配体批间差异", "活性不同", "窗口与 EC50 变化", 7, 4, 4, "批放行并排比较；桥接"),
        F("读数仪器漂移", "光路/检测器", "信号变化", 5, 3, 4, "仪器确认；每次板读数质控"),
        F("曲线拟合模型选择不当", "模型与权重", "效力估计偏倚", 7, 3, 5, "预先规定模型与权重；拟合优度；统计人员审核"),
        F("血清/培养基批次差异", "生长因子差异", "细胞响应变化", 6, 5, 4, "批验收测试；预留批次"),
        F("孵育时间/温度偏差", "培养箱波动", "反应程度变化", 6, 4, 3, "监测与记录；PAR"),
        F("分析员差异", "加样/操作", "中间精密度增大", 5, 5, 4, "培训；分析员因子纳入验证"),
        F("数据处理错误", "模板/软件版本", "错误效力", 7, 3, 5, "模板验证；软件版本控制；双人复核"),
    ],
    "experiments": [
        X("P0", "反应体系与读数筛选", "选择响应细胞/结合体系与读数方式，确认信号窗口",
          "候选体系 2–3 种；参比品 12 点 2 倍/3 倍稀释；n=3 板；比较信号窗口、EC50 重现性与 CV",
          S_("信号窗口（最大/最小）≥ 3.0；EC50 CV ≤ 15%；曲线上下渐近线明确。"), "explore", 3),
        X("P1", "曲线模型与平行性判据", "确定 4PL/5PL（或平行线）与相似性判据",
          "参比与 ≥ 3 批样品多板曲线；比较 4PL/5PL 拟合优度；估算渐近线比、斜率比；评估差异检验 vs 等效性检验",
          S_("渐近线/斜率/(D−A) 比 0.8–1.2；平行性判据对强降解样品敏感。"), "explore", 2),
        X("P2", "参比品建立与稳定性", "建立内部参比品，评价冻融/储存稳定性",
          "参比批分装；≥ 6 次独立运行赋值；冻融 ×1/×3；−80 ℃/−20 ℃ 储存 0/1/3 个月；对照外部参比（如有）",
          S_("赋值均值与 SD 已确定；冻融与储存变化 ≤ 10%；替换批并行 ≥ 6 次，相对效力落在预设范围。"), "explore", 2),
        X("P3", "板布局、稀释方案与随机化", "确定板设计与剂量-反应点位",
          "边缘效应测试（均一板）；随机化/区组板布局；稀释方案（点数、公比、重复孔数）；n=3 板",
          S_("边缘与中心孔 CV 差异 ≤ 判据；稀释方案使曲线覆盖两渐近线。"), "explore", 1),
        X("P4", "专属性与强降解样品响应", "证明方法对作用机制特异，并为稳定性指示",
          "基质/过程杂质加入（干扰评价）；细胞系单独无剂量-反应（细胞法）；热/氧化/光/酸碱降解样品及未降解对照；各 n=3 板；观察效力与曲线形状变化",
          S_("基质与过程杂质对曲线特征无显著影响（相对效力变化 ≤ 10%）；效力下降或形状改变可被检出，平行性判据对降解样品报警。"), "explore", 2),
        X("P5", "线性与范围（相对效力水平）", "评价理论 vs 测得相对效力的线性与范围",
          "样品由参比与降解样品按比例制备，对应 50%、71%、100%、141%、200% 相对效力；每水平 3 次独立制备；对数–对数回归",
          S_("斜率 95% CI 0.8–1.25；无趋势；范围覆盖规格 −20%/+20%。"), "robust", 2),
        X("P6", "准确度", "评价各效力水平相对偏倚",
          "同 P5，≥ 5 水平 × ≥ 3 独立制备；计算相对偏倚的 90% CI",
          S_("各水平相对偏倚 90% CI 上下限均不超过 ±20%。"), "robust", 1),
        X("P7", "精密度（重复性与中间精密度）", "估计重复性与中间精密度",
          "重复性：≥ 5 水平 × ≥ 3 重复；中间精密度：2 分析员 × ≥ 3 天 × 多水平；方差分量（几何 CV）",
          S_("跨水平平均中间精密度几何 CV 的 95% CI 上限 ≤ 20%。"), "robust", 2),
        X("P8", "DoE 稳健性", "确定关键参数及 PAR",
          "因子：细胞密度、刺激物浓度、孵育时间、效靶比（如适用）、细胞代数、读数试剂孵育时间、板类型；部分因子 + 中心点；响应：EC50、窗口、相对效力",
          S_("关键参数确定；PAR 内相对效力变化 ≤ 10%，窗口 ≥ 3.0。"), "robust", 3),
        X("P9", "SST 与样品适用性挑战", "由开发数据定 SST/样品适用性判据，并检验其拦截能力",
          "故意制造：参比品降解、细胞过高代数/过低活率、非平行样品、稀释误差；各 3 次",
          S_("SST（r²、信号窗口、渐近线完整性）与样品适用性（渐近线/斜率比）能拦截全部故意失败。"), "control", 1),
        X("P10", "预验证演练", "两名分析员按 SOP 草案运行",
          "各 3 次独立运行，覆盖参比、3 个样品、SST；评估 SOP 清晰度与周转时间",
          S_("SOP 可执行；SST 拦截全部故意失败；偏差闭合。"), "report", 1),
    ],
    "sst": [
        ["参比品剂量-反应曲线", "呈 S 形，上下渐近线明确；r² ≥ 0.97", "曲线质量", "运行无效"],
        ["信号窗口（最大/最小信号比）", "≥ 3.0", "细胞/试剂状态", "运行无效"],
        ["参比品 EC50（控制图）", "在控制限内", "参比品/试剂漂移", "调查"],
        ["对照孔（细胞对照/空白）", "在预设范围内", "背景/污染", "运行无效"],
        ["样品适用性：渐近线、斜率、(D−A) 比", "0.8–1.2（示例）", "平行性", "样品结果无效/调查"],
        ["重复孔 CV", "≤ 15%（示例）", "移液/板效应", "运行无效"],
    ],
    "ph": {
        "atp.use": "测定 XX（蛋白药物原液/制剂）相对于参比品的相对效力；用于放行与稳定性；要求稳定性指示（可检出效力变化）。",
        "atp.attribute": "属性：相对效力（%，相对参比品）。规格：80%–125%（示例）。关联：作用机制为 XX，效力反映 XX 的生物学活性（CQA）。",
        "atp.specificity": "对作用机制特异；基质与过程杂质不显著影响剂量-反应曲线特征；强降解样品应能检出效力或曲线形状变化；细胞系单独无剂量-反应（细胞法）。",
        "atp.sampling": "样品稀释起点与溶剂：XX；冻融：不超过 XX 次；制备后 ≤ XX h 内上板。",
        "tech.principle": "参比品与样品以相同稀释方案制备剂量系列，加入含 XX 的体系，孵育 XX h 后读取 XX 信号。以 4PL 模型拟合参比与样品曲线，在平行性（相似性）满足时，由两曲线水平位移计算样品相对参比的相对效力。",
        "plan.strategy": "先筛选体系与读数（P0），确定曲线模型与平行性判据（P1）、建立参比品（P2）和板设计（P3）；强降解响应（P4）证明稳定性指示；条件固定后以相对效力水平评价线性/准确度/精密度（P5–P7）；DoE（P8）后做 SST/样品适用性挑战（P9）与预验证（P10）。",
        "plan.statistics": "曲线拟合：4PL（或 5PL），权重 XX；相对效力：平行线/共享渐近线约束模型；平行性：渐近线比/斜率比或等效性检验；线性：对数–对数回归；精密度：几何 CV 方差分量；准确度：相对偏倚 90% CI；软件及版本：XX。",
        "plan.sample_size": "效力水平 ≥ 5，每水平 ≥ 3 次独立制备；精密度 2 分析员 × ≥ 3 天；参比品赋值 ≥ 6 次独立运行；设计与 Q2(R2) Table 7 一致。",
        "plan.decision_rules": "信号窗口 < 3.0 或渐近线未明确则回到体系/读数筛选；平行性判据在看数据前写定；不得为通过而更换拟合模型或权重。",
        "report.sop_sample": "参比品与样品按 XX 稀释至起始浓度，按 XX 倍系列稀释共 XX 点；各点 XX 孔；样品与参比使用相同稀释液；制备后 ≤ XX h 内上板。",
        "report.sop_settings": "细胞：XX（代数 XX–XX，活率 ≥ XX%），接种密度 XX/孔；刺激物浓度 XX；孵育 XX h/XX ℃/XX% CO2；读数：XX（波长/积分时间 XX）；拟合：4PL，权重 XX。",
        "report.sop_procedure": "1. 复苏/收获细胞并计数；2. 制备参比品与样品稀释系列（随机化板布局）；3. 加入细胞与刺激物；4. 孵育；5. 加读数试剂并读板；6. 拟合参比与样品曲线；7. 检查 SST 与平行性；8. 计算相对效力。",
        "report.sop_calc": "4PL：y = D + (A − D)/(1 + (x/C)^B)；相对效力 = 参比 EC50 / 样品 EC50（共享渐近线与斜率约束下的位移）；可报告结果 = N 次独立运行的几何均值。",
        "report.sop_sst": "参比曲线 r² ≥ XX，窗口 ≥ XX；对照孔在范围内；EC50 在控制限内；样品适用性：渐近线/斜率/(D−A) 比 0.8–1.2（示例）。任一失败运行无效。",
    },
    "seeds": {
        "charter.glossary": [
            ["RP", "Relative Potency 相对效力", "样品相对参比品的效力比，在平行性满足时由曲线位移求得。"],
            ["4PL / 5PL", "四/五参数 Logistic", "S 形剂量-反应曲线的数学模型。"],
            ["EC50", "半数有效浓度", "产生 50% 最大响应的浓度。"],
            ["平行性 / 相似性", "Parallelism / Similarity", "样品与参比曲线仅水平位移、形状（渐近线、斜率）一致。"],
            ["渐近线 / Hill 斜率", "Asymptote / Slope", "曲线上下平台与陡峭度参数。"],
            ["信号窗口", "Assay window", "最大信号/最小信号之比，衡量测定动态范围。"],
            ["RS / WRS", "参比标准品 / 工作参比品", "用于定义效力单位或日常比较的材料。"],
            ["GCV", "Geometric Coefficient of Variation 几何变异系数", "对数正态分布数据的变异系数。"],
            ["PLA", "Parallel Line Analysis 平行线分析", "相对效力的统计分析方法之一。"],
        ],
        "charter.refdocs": [
            ["药典", "USP <1032> Design and Development of Biological Assays", "USP–NF 现行版（条款待核对）", "生物测定设计与开发"],
            ["药典", "USP <1033> Biological Assay Validation", "USP–NF 现行版（条款待核对）", "生物测定验证"],
            ["药典", "USP <1034> Analysis of Biological Assays", "USP–NF 现行版（条款待核对）", "统计分析、平行性、相对效力"],
            ["药典", "USP <111> Design and Analysis of Biological Assays", "USP–NF 现行版（条款待核对）", "生物测定设计与分析通则"],
            ["药典", "Ph.Eur. 5.3 Statistical Analysis of Results of Biological Assays and Tests", "现行版（版本待核对）", "生物测定统计分析"],
            ["药典", "《中国药典》通则 9401 生物制品生物活性/效价测定方法验证指导原则", "现行版（章节号待核对）", "生物活性测定验证"],
            ["法规/指南", "ICH Q6B Specifications: Test Procedures and Acceptance Criteria for Biotechnological/Biological Products", "ICH（条款待核对）", "生物制品规格与活性测定"],
            ["法规/指南", "ICH Q14 Annex A：抗 TNF-α 单抗效力测定示例；ICH Q2(R2) Annex 2 Table 7（生物测定示例）", "见上方 ICH 条目", "ATP、SST、样品适用性、EC 示例；验证设计"],
            ["法规/指南", "FDA Potency Tests for Cellular and Gene Therapy Products", "FDA CBER，2011-01", "效力测定总体考虑（细胞与基因治疗产品）"],
        ],
        "tech.conditions": [
            ["样品", "样品起始浓度与稀释", "参比与样品同起点，XX → XX（公比 2 或 3，XX 点）", "公比；点数", "需覆盖上下渐近线"],
            ["试剂/溶液", "细胞系与代数窗口", "XX 细胞，代数 XX–XX", "低/中/高代数", "细胞库与代数限制"],
            ["样品", "细胞接种密度", "XX×10^4 / 孔", "±20%", "DoE 因子"],
            ["试剂/溶液", "刺激物/配体浓度", "EC80 附近（示例）", "±20%", "窗口与灵敏度"],
            ["反应/染色/孵育", "孵育时间/温度/CO2", "XX h，37 ℃，5% CO2", "±1 h；±1 ℃", "DoE 因子"],
            ["反应/染色/孵育", "读数试剂与孵育", "XX（如 WST-8 / 荧光素酶底物），XX min", "±10 min", "信号线性范围"],
            ["仪器/检测", "读数方式与波长/积分时间", "XX nm / XX s", "—", "读板仪确认"],
            ["仪器/检测", "板类型与布局", "96 孔，随机化区组；边缘孔 XX", "板类型", "边缘效应控制"],
            ["数据处理", "曲线拟合模型与权重", "4PL，权重 XX", "4PL / 5PL", "拟合优度；预先规定"],
            ["数据处理", "平行性判据", "渐近线/斜率比 0.8–1.2（示例）", "差异检验 vs 等效性", "ICH Q14 Annex A；USP <1034>"],
            ["保存/稳定性", "参比品冻融/储存", "单次使用分装；−80 ℃", "冻融 ×1–3", "稳定性研究"],
        ],
        "tech.reagents": [
            ["参比品（RS / WRS）", "定义效力单位；相对效力计算", "官方或内部赋值", "关键", "变质、批间差", "稳定性监测；替换协议；控制图"],
            ["响应细胞（含库）", "生物反应系统", "细胞库（MCB/WCB）", "关键", "代数漂移、污染", "细胞库管理；代数限制；支原体检测"],
            ["刺激物/配体", "诱导反应", "供应商/自制", "关键", "活性批间差", "批放行并排比较；桥接"],
            ["血清/培养基/生长因子", "细胞维持与测定", "供应商", "重要", "批间差异", "批验收测试；预留批次"],
            ["读数试剂（如 WST-8 / 荧光素酶底物）", "信号产生", "供应商", "重要", "批间/稳定性", "验收；开封后有效期"],
            ["细胞培养板/耗材", "测定载体", "供应商", "一般", "板型批间差", "板类型纳入稳健性"],
        ],
        "plan.materials": [
            ["参比品（RS / WRS）", "参比品/标准品", "", "", "", "关键", "按稳定性方案；替换批并行评价", "待采购"],
            ["响应细胞（MCB / WCB）", "细胞/生物材料", "", "", "", "关键", "每批建库后检测支原体/活率", "待采购"],
            ["刺激物/配体", "试剂", "", "", "", "关键", "新批并排比较", "待采购"],
            ["血清 / 培养基 / 生长因子", "试剂", "", "", "", "重要", "批验收测试", "待采购"],
            ["读数试剂", "试剂", "", "", "", "重要", "新批验收", "待采购"],
            ["细胞培养板（96 孔）", "耗材", "", "", "", "一般", "—", "待采购"],
            ["稀释液/缓冲液", "溶液/缓冲液", "", "", "", "一般", "配制记录", "待采购"],
        ],
        "plan.instruments": [
            ["CO2 培养箱", "—", "细胞培养与孵育", "待确认", "温度/CO2 监测与校准", ""],
            ["生物安全柜", "II 级", "无菌操作", "待确认", "年度检定", ""],
            ["酶标仪/发光/荧光读板仪", "—", "读数", "待确认", "IQ/OQ/PQ；波长/线性核对", ""],
            ["细胞计数仪", "—", "细胞计数与活率", "待确认", "日常核对", ""],
            ["液体处理设备/多通道移液器", "—", "稀释与加样", "校准有效", "校准；稀释精度验证", ""],
        ],
        "plan.software": [
            ["读板仪软件", "（填写）", "采集原始读数", "待验证", "开启"],
            ["曲线拟合/相对效力软件", "（填写）", "4PL/平行线拟合、平行性检验", "待验证", "开启"],
            ["统计软件", "（填写）", "方差分量、容忍区间、DoE", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["参比品", "RS / WRS", "−80 ℃ 分装", "单次使用；复融后 ≤ XX h", "曲线定位、SST"],
            ["样品（原液/制剂，≥ 3 批）", "覆盖不同批次", "2–8 ℃ 或按稳定性条件", "稀释后 ≤ XX h", "准确度、精密度"],
            ["强降解样品", "热/氧化/光/酸碱", "避光冷藏", "按降解后稳定性", "稳定性指示、平行性"],
            ["不同效力水平样品", "参比与降解样品按比例制备（50%–200%）", "新鲜配制", "—", "线性、范围、准确度"],
            ["基质/空白", "样品缓冲液", "按样品", "—", "专属性（无干扰）"],
        ],
        "risk.ishikawa": [
            ["样品", "稀释误差；基质效应；降解；聚集", "准确度；平行性", "稀释验证；样品适用性"],
            ["试剂与材料", "参比品变质；刺激物批差；血清批差；读数试剂稳定性", "窗口；EC50；相对效力", "参比品管理；批验收；预留批"],
            ["仪器", "读板仪线性/波长；培养箱温度/CO2；移液设备", "信号；变异", "确认与校准；监测"],
            ["方法", "细胞密度；孵育时间；板布局；拟合模型/权重；平行性判据", "精密度；偏倚", "DoE；随机化；预先规定模型"],
            ["人员与分析", "加样；细胞操作；模型选择主观性", "中间精密度", "培训；SOP；统计人员审核"],
            ["环境与流程", "细胞代数；边缘效应；运行顺序；孵育环境", "窗口；变异", "代数限制；板布局；记录环境"],
        ],
        "robust.factors": [
            ["A  细胞接种密度", "−20%", "设定值", "+20%", "窗口与 EC50 的主要影响因素"],
            ["B  刺激物/配体浓度", "−20%", "设定值", "+20%", "EC80 附近敏感"],
            ["C  孵育时间", "−1 h", "设定值", "+1 h", "反应程度"],
            ["D  读数试剂孵育时间", "−10 min", "设定值", "+10 min", "信号线性"],
            ["E  细胞代数（类别）", "低", "中", "高", "细胞库代数窗口"],
            ["F  板类型/批次（类别）", "板 1", "板 2", "板 3", "板间差"],
        ],
        "robust.par": [
            ["细胞接种密度", "设定值", "待 DoE 确定", "实验编号 P8"],
            ["孵育时间", "设定值", "待 DoE 确定", "实验编号 P8"],
            ["刺激物浓度", "设定值", "待 DoE 确定", "实验编号 P8"],
        ],
        "robust.stability": [
            ["参比品（冻融）", "−80 ℃，冻融 ×1/×3", "0、1、3 个月", "", ""],
            ["样品稀释系列", "室温/2–8 ℃", "0、2、4、8 h", "", ""],
            ["刺激物/试剂工作液", "按储存条件", "0、1、4、12 周", "", ""],
            ["冻存细胞（即用型，如适用）", "气相液氮", "复苏后活率与响应", "", ""],
        ],
        "control.references": [
            ["内部参比品（WRS）", "效力基准、SST", "≥ 6 次独立运行赋值；对照外部参比（如有）", "冻融、储存 0/1/3/6/12 个月", "新批与现行批并行 ≥ 6 次，等效性判定"],
            ["细胞库（MCB / WCB）", "响应细胞来源", "鉴定、支原体、无菌；STR（人源）", "冻存稳定性", "新库与旧库并行比较"],
            ["质控样品（高/中/低效力，如使用）", "SST/趋势", "赋值", "同参比", "同参比"],
        ],
        "control.reagent_mgmt": [
            ["刺激物/配体", "来源、批号、活性、储存", "并排比较 EC50/窗口", "每批", "更换供应商需桥接"],
            ["血清/培养基", "批号、来源", "细胞生长与窗口验收测试", "每批", "更换血清批需验收"],
            ["读数试剂", "批号、有效期", "标准曲线/窗口检查", "每批", "—"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据影响对 CQA 的控制（ICH Q14 Annex A Table 6 的做法）"],
            ["技术原理（细胞法 / 结合法）", "高", "PA", "原理变更需桥接与新 ATP 评估"],
            ["SST 与样品适用性判据", "中", "NM", "由控制策略证明性能"],
            ["曲线模型、权重与平行性判据", "高", "NM", "直接决定相对效力计算"],
            ["细胞代数窗口与接种密度", "中", "NM", "DoE 证明；PAR 内变动不通知"],
            ["板类型/读板仪型号", "低", "NL", "稳健性显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性", "基质/过程杂质不干扰；强降解样品响应；细胞系单独无剂量-反应（细胞法）", "降解样品 + 基质", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["重复性", "单日/短时间，≥ 5 效力水平 × ≥ 3 重复", "50%–200%", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["中间精密度", "不同分析员、多个独立制备、多天、多个效力水平", "—", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["准确度", "≥ 3 次独立制备 × ≥ 5 效力水平，回收率 vs 理论效力", "—", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["范围", "≥ 5 效力水平，满足准确度、精密度、响应判据的最低到最高", "64%–150%（例）", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["稳健性（确认）", "板类型、缓冲液成分、孵育、仪器、试剂批（含对照）；细胞密度、效靶比、细胞代数", "PAR 边界", "ICH Q2(R2) Table 7；ICH Q14 §5.1" + SAMPLE_TAG],
            ["联合评价", "各水平相对误差 90% 容忍区间", "—", "ICH Q2(R2) §3.3.3" + SAMPLE_TAG],
            ["SST 有效性", "故意失败应被拦截", "—", "ICH Q14 §6" + SAMPLE_TAG],
        ],
    },
}


# ---------------------------------------------------------------------- cell_based
TECHNIQUES["cell_based"] = {
    "label": "细胞法功能/效力测定（报告基因、杀伤、细胞因子释放）",
    "desc": "以细胞为反应体系的功能/效力测定：细胞库与传代控制、信号窗口、参比品、4PL/平行线相对效力、平行性、PAR。适用于细胞治疗产品与细胞法生物活性。",
    "changelog": [
        "1.1：新增模板。预置细胞库/传代窗口、靶细胞与效应细胞管理、信号窗口与 Z′、剂量-反应与相对效力、平行性、PAR；12 条 FMEA、13 个实验种子、SST、验证矩阵",
        "1.1：检查项 cx1–cx12（细胞库、鉴定与支原体、代数窗口、抗原依赖性、E:T 比、参比品、信号窗口、冻存即用细胞、多靶点分别评估等）",
    ],
    "matrix": {"options": ["报告基因", "靶细胞杀伤（LDH / 荧光素酶 / 实时阻抗）", "细胞因子释放（IFN-γ 等）", "活化标志（CD69 / CD25 等）"],
               "criteria": [("与作用机制的相关性", 5), ("精密度", 4), ("信号窗口/灵敏度", 4), ("稳定性指示能力", 4),
                            ("验证成熟度", 3), ("通量", 2), ("成本", 2)]},
    "atp_rows": [
        ["准确度", "各相对效力水平（如 50%/71%/100%/141%/200%）相对偏倚的 90% CI 上下限不超过 ±25%（细胞法变异较大）；理论 vs 测得效力斜率 95% CI 在 0.8–1.25", "示例值，须按产品规格与工艺能力确认", "ICH Q14 Annex A Table 4；ICH Q2(R2) Table 7"],
        ["精密度-重复性", "同日 ≥ 5 个水平 × ≥ 3 重复，几何 CV ≤ 20%", "示例值", "ICH Q2(R2) Table 7"],
        ["精密度-中间精密度", "跨水平平均中间精密度（几何 CV）95% CI 上限 ≤ 25%", "示例值；多分析员、多天、多批细胞/试剂", "ICH Q2(R2) Table 7；ICH Q14 Annex A"],
        ["联合评价(总误差)", "各水平相对误差 90% 容忍区间在 ±30% 内", "示例值，须与规格宽度及放行风险相容", "ICH Q2(R2) §3.3.3"],
        ["线性/响应", "参比与样品曲线 S 形，r² ≥ 0.97；理论 vs 测得相对效力无趋势", "示例值", "ICH Q2(R2) §3.2.2.2"],
        ["专属性", "抗原依赖：抗原阴性靶细胞/无关效应细胞/无靶细胞对照无响应或 ≤ 背景+X；多靶点产品对每个靶抗原分别评估", "FDA：多靶点分别评估", "FDA 2024 CAR-T §IV.C.2.d；ICH Q2(R2) Table 7"],
        ["定量下限", "报告范围覆盖规格 −20%/+20%，并在范围两端满足准确度/精密度", "示例；范围由规格推导", "ICH Q2(R2) §2.3"],
        ["稳健性/稳定性", "细胞代数窗口、接种密度、E:T 比、孵育时间、血清批、读数时间点的合理变动下 SST 通过且相对效力变化 ≤ 15%", "示例值", "ICH Q2(R2) Table 7；ICH Q14 §5.1"],
        ["其他", "信号窗口（最大/最小）≥ 3.0；Z′ ≥ 0.5；平行性（渐近线/斜率比）0.8–1.2 或等效性检验", "示例值，须按体系确认", "ICH Q14 Annex A；USP <1034>（条款待核对）"],
    ],
    "extra_checklist": {
        "atp": [
            ck("cx1", "多靶点/多转基因产品：每个靶点或转基因元件的活性均有评估计划", "靶点特异的效应细胞活化是产品功能前提。", "FDA 2024 CAR-T §IV.C.2.d"),
            ck("cx2", "放行判据拟采用定量验收标准（含定量下限），不是“仅报告”", "", "FDA 2023 效力草案 V.D", False),
        ],
        "tech": [
            ck("cx3", "细胞系/靶细胞来源、细胞库级别（MCB/WCB）、鉴定（STR/表型）与支原体检测方案已确定", "细胞库是细胞法稳定性的基础。", "ICH Q5D 细胞基质（条款待核对）；Ph.Eur. 2.6.7 支原体（版本待核对）"),
            ck("cx4", "读数与产品作用机制相关性已论证；必要时规划正交方法（杀伤+细胞因子等）", "单一读数可能不足以反映多重机制。", "FDA 2024 CAR-T §IV.C.2.d"),
            ck("cx5", "已规划曲线模型（4PL/5PL 或平行线）与平行性/相似性判据", "", "ICH Q14 Annex A；USP <1034>（条款待核对）"),
        ],
        "risk": [ck("cx6", "已评估细胞状态/代数、血清批次、板边缘、E:T 比及参比品风险", "", "ICH Q14 Annex A 石川图示例", False)],
        "plan": [
            ck("cx7", "传代窗口、冻存即用（assay-ready）或连续培养策略、活率与健康度放行标准已规划", "", "USP <1032>（条款待核对）"),
            ck("cx8", "板布局（随机化/区组）、重复与独立制备次数已规定", "", "USP <1032>（条款待核对）"),
        ],
        "explore": [ck("cx9", "信号窗口与剂量-反应在目标体系上已建立（S/B、Z′、两渐近线明确）", "", "ICH Q14 Annex A（SST 示例）", False)],
        "robust": [ck("cx10", "细胞代数、接种密度、E:T 比、孵育时间、血清批次的影响已评价并确定 PAR", "", "ICH Q2(R2) Table 7；ICH Q14 §5.2")],
        "control": [
            ck("cx11", "内部参比品的建立、定值、稳定性与替换协议已完成；SST 判据来自开发数据", "", "FDA 2023 效力草案 V.C.2；ICH Q14 §6"),
            ck("cx12", "细胞库与试剂的放行/再确认规则已建立（代数、鉴定、支原体、血清批验收）", "", "ICH M10 §4.1.2（原则可借用）", False),
        ],
        "report": [],
    },
    "fmea": [
        F("细胞状态/代数漂移", "传代与培养", "信号窗口与 EC50 变化", 7, 5, 4, "细胞库；代数限制；SST 窗口与参比 EC50 控制图"),
        F("细胞库污染或身份错误", "交叉污染/支原体", "结果失真", 9, 2, 4, "STR/表型鉴定；支原体检测；库管理；隔离操作"),
        F("靶抗原表达波动", "培养/传代", "效应读数变化", 7, 4, 4, "靶抗原表达监测（流式）；放行范围"),
        F("效应细胞（产品）活率或健康度差", "冻存复苏/运输", "响应低估", 7, 4, 3, "活率判据；复苏程序；样品适用性"),
        F("参比品变质或批变更", "冻融/储存/替换", "相对效力偏倚", 8, 3, 4, "稳定性监测；替换批并行评价；控制图"),
        F("曲线不平行", "样品基质/降解/异常样品", "效力误判", 7, 4, 4, "样品适用性判据；平行性检验"),
        F("板边缘效应与蒸发", "温度/湿度", "变异增大", 5, 5, 3, "随机化板布局；边缘孔处理；SST"),
        F("血清/培养基批次差异", "生长因子差异", "窗口和响应变化", 6, 5, 4, "批验收；预留批次；桥接"),
        F("E:T 比与接种密度误差", "计数/稀释误差", "响应偏移", 7, 4, 3, "计数仪核对；双人复核；PAR"),
        F("读数时间点与孵育偏差", "操作/设备", "信号变化", 6, 4, 3, "计时记录；PAR；读数窗口"),
        F("曲线拟合模型选择不当", "模型与权重", "效力估计偏倚", 7, 3, 5, "预先规定模型；统计人员审核"),
        F("分析员差异", "细胞操作与加样", "中间精密度增大", 5, 5, 4, "培训与资格；分析员因子纳入验证"),
    ],
    "experiments": [
        X("P0", "细胞库建立与鉴定", "建立并表征响应/靶细胞库",
          "MCB / WCB 冻存；STR 或表型鉴定；支原体与无菌检测；靶抗原表达（流式）；复苏后活率与生长曲线",
          S_("身份与来源一致；支原体阴性；靶抗原阳性率稳定在预设范围；复苏活率 ≥ 判据。"), "explore", 3),
        X("P1", "传代窗口", "确定可用代数范围",
          "低/中/高代数细胞各 3 次独立运行；比较 EC50、信号窗口、参比相对效力",
          S_("各代数相对效力差异 ≤ 15%，窗口 ≥ 3.0；据此规定可用代数范围。"), "explore", 2),
        X("P2", "剂量-反应与信号窗口", "建立剂量-反应并确定窗口",
          "产品/参比 12 点稀释；E:T 比 3 个水平；读数时间点 2–3 个；n=3 板；计算 S/B、Z′、EC50 CV",
          S_("信号窗口 ≥ 3.0；Z′ ≥ 0.5；两渐近线明确；EC50 CV ≤ 15%。"), "explore", 2),
        X("P3", "抗原依赖性与专属性", "证明响应由靶抗原驱动",
          "抗原阳性靶 vs 抗原阴性靶；无靶细胞；无关效应细胞；阻断抗体（适用时）；多靶点产品逐靶点评估；n=3",
          S_("阴性靶/无靶对照响应 ≤ 背景+X；阻断后响应下降 ≥ 判据；每个靶点分别有剂量-反应。"), "explore", 2),
        X("P4", "培养基、血清与试剂批次", "评价批间差异并确定验收标准",
          "≥ 3 个血清/培养基批次 × 参比与样品；刺激物/读数试剂 2 批",
          S_("批间相对效力变化 ≤ 10%；窗口 ≥ 3.0；据此规定批验收测试。"), "explore", 1),
        X("P5", "参比品建立与稳定性", "建立内部参比品",
          "产品/细胞代表性批分装；≥ 6 次独立运行赋值；冻融 ×1/×3；−80 ℃/气相液氮储存 0/1/3/6 个月",
          S_("赋值均值与 SD 已确定；冻融与储存变化 ≤ 10%；替换批并行 ≥ 6 次独立运行，相对效力落在预设范围。"), "robust", 3),
        X("P6", "曲线模型与平行性判据", "确定 4PL/5PL 与平行性判据",
          "参比与 ≥ 3 批样品及降解样品曲线；渐近线比/斜率比分布；差异检验 vs 等效性检验",
          S_("正常批判据通过率 ≥ 95%；降解/异常样品被识别。"), "robust", 1),
        X("P7", "线性、范围与准确度", "评价相对效力线性与准确度",
          "50%、71%、100%、141%、200% 相对效力水平 × 每水平 3 次独立制备；对数–对数回归；相对偏倚 90% CI",
          S_("斜率 95% CI 0.8–1.25；各水平相对偏倚 90% CI 不超过 ±25%。"), "robust", 2),
        X("P8", "精密度（重复性与中间精密度）", "估计重复性与中间精密度",
          "重复性：≥ 5 水平 × ≥ 3 重复；中间精密度：2 分析员 × ≥ 3 天 × 不同细胞批；几何 CV 方差分量",
          S_("中间精密度几何 CV 95% CI 上限 ≤ 25%。"), "robust", 2),
        X("P9", "DoE 稳健性与 PAR", "确定关键参数及 PAR",
          "因子：接种密度、E:T 比、孵育时间、读数时间点、细胞代数、活率；部分因子 + 中心点；响应：EC50、窗口、相对效力",
          S_("关键参数确定；PAR 内相对效力变化 ≤ 15%，窗口 ≥ 3.0。"), "robust", 3),
        X("P10", "冻存即用细胞与试剂稳定性", "评价冻存即用（assay-ready）细胞与关键试剂的稳定性（如采用）",
          "冻存即用细胞复苏后立即用 vs 连续培养；试剂工作液 0/1/4/12 周；n=3",
          S_("冻存即用细胞与连续培养相对效力差 ≤ 10%；试剂稳定性限度已确定。"), "robust", 2),
        X("P11", "SST 与 PAR 挑战", "由开发数据定 SST，并检验拦截能力",
          "故意制造：参比降解、高代数细胞、低活率、接种密度偏离 ±30%、非平行样品；各 3 次",
          S_("SST（r²、窗口、Z′、对照孔、EC50 控制图）与样品适用性能拦截全部故意失败。"), "control", 1),
        X("P12", "预验证演练", "两名分析员按 SOP 草案运行",
          "各 3 次独立运行，覆盖参比、3 个样品、SST；评估 SOP 清晰度与周转",
          S_("SOP 可执行；SST 拦截全部故意失败；偏差闭合。"), "report", 1),
    ],
    "sst": [
        ["参比品剂量-反应曲线", "S 形，上下渐近线明确；r² ≥ 0.97（示例）", "曲线质量", "运行无效"],
        ["信号窗口（S/B）与 Z′", "S/B ≥ 3.0；Z′ ≥ 0.5（示例）", "细胞/试剂状态", "运行无效"],
        ["无靶细胞/抗原阴性靶对照", "≤ 背景 + X（示例）", "抗原依赖性、背景", "调查；运行无效"],
        ["参比品 EC50（控制图）", "在控制限内；Westgard 规则不触发", "参比品/细胞漂移", "调查"],
        ["细胞活率与代数", "活率 ≥ 判据；代数在窗口内", "细胞状态", "不使用该批细胞"],
        ["样品适用性：渐近线/斜率比", "0.8–1.2（示例）", "平行性", "样品结果无效/调查"],
    ],
    "ph": {
        "atp.use": "测定 XX 细胞产品/生物药对 XX 靶点的功能活性（相对参比品的相对效力）；用于放行与稳定性；可在多个站点执行；适用阶段 XX。",
        "atp.attribute": "属性：靶抗原依赖的功能活性（相对效力，%，相对内部参比品）。规格：XX%–XX%（预期）。关联：作用机制为 XX；多靶点产品需对每个靶点分别评估活性（FDA 2024 §IV.C.2.d）。",
        "atp.specificity": "响应须由靶抗原驱动：抗原阴性靶细胞、无靶细胞、无关效应细胞对照无响应；多靶点分别评估；基质/过程杂质不改变曲线特征。",
        "atp.sampling": "效应细胞（产品）复苏后 ≤ XX min 内使用，活率 ≥ XX%；冻融仅 1 次；靶细胞使用代数 XX–XX。",
        "tech.principle": "效应细胞（产品）与抗原阳性靶细胞按 XX:1 共培养 XX h，通过 XX（荧光素酶报告/LDH 释放/实时阻抗/IFN-γ ELISA）读取功能响应；产品与参比品系列稀释形成剂量-反应曲线，在平行性满足时计算相对效力。抗原阴性靶细胞/无靶细胞对照证明抗原依赖性。",
        "plan.strategy": "先建库并鉴定（P0）、确定代数窗口（P1）、建立剂量-反应与信号窗口（P2）和抗原依赖性（P3）；批次影响（P4）后建参比品（P5）并确定平行性判据（P6）；条件固定后做线性/准确度/精密度（P7、P8）与 DoE（P9）；SST 挑战（P11）后预验证（P12）。",
        "plan.statistics": "曲线：4PL（或 5PL）+ 权重 XX；相对效力：平行线/共享渐近线约束；平行性：渐近线/斜率比或等效性检验；线性：对数–对数回归；精密度：几何 CV 方差分量；DoE：效应与曲率；软件及版本：XX。",
        "plan.sample_size": "代数窗口 3 个代数 × 3 次运行；效力水平 ≥ 5 × 3 独立制备；精密度 2 分析员 × ≥ 3 天；参比品赋值 ≥ 6 次独立运行；细胞批次 ≥ 2。",
        "plan.decision_rules": "窗口 < 3.0 或 Z′ < 0.5 则回到体系优化；抗原阴性对照出现响应则回到细胞/试剂选择；平行性判据在看数据前写定；细胞代数窗口一旦确定，超出视为偏离。",
        "report.sop_sample": "产品/参比按 XX 稀释至起始浓度，XX 倍系列稀释共 XX 点；各点 XX 孔；靶细胞：代数 XX–XX，活率 ≥ XX%，计数后调整至 XX/孔。",
        "report.sop_settings": "效应细胞：XX/孔；靶细胞：XX/孔；E:T = XX:1；共培养 XX h，37 ℃，5% CO2；读数：XX；板布局：随机化区组；拟合：4PL，权重 XX。",
        "report.sop_procedure": "1. 复苏效应细胞并计数、记录活率；2. 准备靶细胞（代数核对）；3. 制备参比与样品稀释系列；4. 按随机化板布局加样；5. 共培养；6. 加读数试剂并读取；7. 拟合曲线，检查 SST 与平行性；8. 计算相对效力。",
        "report.sop_calc": "4PL：y = D + (A − D)/(1 + (x/C)^B)；相对效力 = 参比 EC50 / 样品 EC50（平行性满足时，共享渐近线与斜率）；可报告结果 = N 次独立运行的几何均值。",
        "report.sop_sst": "参比曲线 r² ≥ XX；S/B ≥ XX；Z′ ≥ XX；无靶/抗原阴性对照 ≤ XX；参比 EC50 在控制限内；细胞活率 ≥ XX%；样品适用性：渐近线/斜率比 0.8–1.2（示例）。任一失败运行无效。",
    },
    "seeds": {
        "charter.glossary": [
            ["MCB / WCB", "主细胞库 / 工作细胞库", "分级冻存的细胞库，保证来源一致与可追溯。"],
            ["代数 / 传代窗口", "Passage number / window", "细胞自复苏起的传代次数及允许使用范围。"],
            ["E:T 比", "效应细胞:靶细胞比", "共培养中效应细胞与靶细胞数量之比。"],
            ["报告基因", "Reporter gene", "响应信号通路激活而表达的易检测基因（如荧光素酶）。"],
            ["S/B、Z′", "信号/背景比；Z′ 因子", "衡量测定窗口与适用性；Z′ = 1 − 3(σ+ + σ−)/|μ+ − μ−|。"],
            ["STR", "短串联重复序列鉴定", "人源细胞系身份鉴定方法。"],
            ["EC50 / 4PL / 相对效力", "—", "半数有效浓度；四参数 Logistic；样品相对参比的效力比。"],
            ["平行性", "Parallelism", "样品与参比曲线形状一致，仅水平位移。"],
            ["冻存即用细胞", "Assay-ready cells", "预先冻存、复苏后直接用于测定的细胞，减少连续培养变异。"],
            ["PAR", "参数范围", "使方法保持适用的参数范围（ICH Q14）。"],
        ],
        "charter.refdocs": [
            ["法规/指南", "FDA Considerations for the Development of Chimeric Antigen Receptor (CAR) T Cell Products", "FDA CBER，最终版，2024-01", "§IV.C.2.d 效力：多靶点分别评估；正交方法"],
            ["法规/指南", "FDA Potency Assurance for Cellular and Gene Therapy Products", "FDA CBER，草案，2023-12（是否已定稿待核对）", "V.B 检测选择；V.C 参比物质/变更；V.D 验收标准"],
            ["法规/指南", "FDA Potency Tests for Cellular and Gene Therapy Products", "FDA CBER，2011-01", "效力测定总体考虑"],
            ["法规/指南", "ICH Q5D Derivation and Characterisation of Cell Substrates Used for Production of Biotechnological/Biological Products", "ICH（条款待核对）", "细胞库建立与表征的原则（可借用于测定用细胞）"],
            ["药典", "USP <1032> / <1033> / <1034> 生物测定设计与开发 / 验证 / 分析", "USP–NF 现行版（条款待核对）", "生物测定统计与验证"],
            ["药典", "Ph.Eur. 2.6.7 Mycoplasmas", "现行版（版本待核对）", "支原体检测"],
            ["行业标准", "ANSI/ATCC ASN-0002 Authentication of Human Cell Lines: Standardization of STR Profiling", "（版本待核对）", "人源细胞系 STR 鉴定"],
            ["法规/指南", "ICH Q14 Annex A 抗 TNF-α 效力示例；ICH Q2(R2) Annex 2 Table 7", "见上方 ICH 条目", "ATP、SST、样品适用性示例；验证设计"],
        ],
        "tech.conditions": [
            ["样品", "效应细胞来源与状态", "产品/细胞系；复苏后活率 ≥ XX%", "复苏后静置 0–120 min", "活率与功能"],
            ["样品", "靶细胞与代数", "XX 抗原阳性靶，代数 XX–XX", "低/中/高代数", "P1 评价"],
            ["反应/染色/孵育", "E:T 比", "XX:1", "3 个水平", "DoE 因子；信号窗口"],
            ["样品", "接种密度（效应/靶）", "XX / XX 个每孔", "±20–30%", "DoE 因子"],
            ["反应/染色/孵育", "共培养时间/条件", "XX h，37 ℃，5% CO2", "±1–2 h", "信号动力学"],
            ["仪器/检测", "读数方式与时间点", "XX（荧光素酶/LDH/阻抗/ELISA）", "时间点 2–3 个", "窗口与重现性"],
            ["样品", "样品稀释方案", "12 点，公比 2 或 3", "起点/公比", "覆盖两渐近线"],
            ["仪器/检测", "板类型与布局", "96 孔，随机化区组；边缘孔 XX", "板类型", "边缘效应"],
            ["试剂/溶液", "培养基/血清", "XX% 血清（预留批）", "3 个批次", "批间影响 P4"],
            ["数据处理", "曲线模型、权重与平行性判据", "4PL；0.8–1.2（示例）", "4PL / 5PL", "预先规定"],
            ["保存/稳定性", "参比品与冻存细胞保存", "−80 ℃ / 气相液氮；单次使用", "冻融 ×1–3", "稳定性研究"],
        ],
        "tech.reagents": [
            ["效应细胞（产品/细胞系）", "功能执行者", "产品批/细胞库", "关键", "活率、状态差异", "活率判据；复苏程序；样品适用性"],
            ["靶细胞（抗原阳性/阴性）", "提供抗原刺激", "细胞库（MCB/WCB）", "关键", "抗原表达漂移、污染", "库管理；表达监测；支原体检测"],
            ["参比品", "效力基准、SST", "内部赋值", "关键", "变质、批变更", "稳定性监测；替换协议；控制图"],
            ["血清/培养基/细胞因子", "细胞维持与测定", "供应商", "重要", "批间差异", "批验收；预留批次"],
            ["读数试剂（荧光素酶底物 / LDH / ELISA 试剂盒）", "信号产生", "供应商", "重要", "批间/稳定性", "验收；开封后有效期"],
            ["阻断抗体 / 对照抗体（适用时）", "证明抗原依赖性", "供应商", "重要", "活性批差", "批验收"],
        ],
        "plan.materials": [
            ["效应细胞 / 产品样品", "细胞/生物材料", "", "", "", "关键", "每次使用前核对活率", "待采购"],
            ["靶细胞（抗原阳性 / 阴性）MCB/WCB", "细胞/生物材料", "", "", "", "关键", "鉴定、支原体、表达监测", "待采购"],
            ["内部参比品", "参比品/标准品", "", "", "", "关键", "稳定性监测；替换协议", "待采购"],
            ["血清 / 培养基 / 细胞因子", "试剂", "", "", "", "重要", "批验收", "待采购"],
            ["读数试剂", "试剂", "", "", "", "重要", "新批验收", "待采购"],
            ["96 孔板（白/黑/透明按读数）", "耗材", "", "", "", "一般", "—", "待采购"],
            ["阻断抗体 / 阴性对照细胞", "对照", "", "", "", "重要", "新批对比", "待采购"],
        ],
        "plan.instruments": [
            ["CO2 培养箱", "—", "细胞培养与共培养", "待确认", "温度/CO2 监测与校准", ""],
            ["生物安全柜", "II 级", "无菌操作", "待确认", "年度检定", ""],
            ["读板仪（发光/荧光/吸光/阻抗）", "—", "读数", "待确认", "IQ/OQ/PQ；线性核对", ""],
            ["细胞计数仪 / 流式细胞仪（表达监测）", "—", "计数、活率、抗原表达", "待确认", "日常核对；每日质控", ""],
            ["气相液氮罐", "—", "细胞库、参比品储存", "待确认", "液位/温度监测", ""],
        ],
        "plan.software": [
            ["读板仪软件", "（填写）", "原始读数采集", "待验证", "开启"],
            ["曲线拟合/相对效力软件", "（填写）", "4PL/平行线拟合与平行性", "待验证", "开启"],
            ["统计软件", "（填写）", "方差分量、容忍区间、DoE", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["产品样品（≥ 3 批）", "细胞产品/生物药，覆盖不同批次与活性", "按产品储存条件", "复苏后 ≤ XX min", "准确度、精密度"],
            ["内部参比品", "同类材料，已赋值", "−80 ℃ / 气相液氮", "单次使用", "SST、相对效力基准"],
            ["降解/应激样品", "热/冻融/储存老化样品", "按条件", "—", "稳定性指示、平行性"],
            ["靶细胞（阳性/阴性）", "细胞库", "气相液氮", "代数窗口内", "专属性、抗原依赖性"],
            ["不同效力水平样品", "参比与降解样品按比例混合（50%–200%）", "新鲜配制", "—", "线性、范围、准确度"],
        ],
        "risk.ishikawa": [
            ["样品", "效应细胞活率/状态；冻融；运输", "响应；窗口", "活率判据；复苏程序"],
            ["试剂与材料", "细胞库代数与污染；血清批差；参比品变质；读数试剂", "窗口；EC50；相对效力", "库管理；批验收；参比品管理"],
            ["仪器", "培养箱温度/CO2；读板仪线性；计数仪准确度", "信号；变异", "确认与校准"],
            ["方法", "E:T 比；接种密度；共培养时间；读数时间点；板布局；拟合模型", "精密度；偏倚", "DoE；随机化；预先规定模型"],
            ["人员与分析", "细胞操作；加样；模型选择", "中间精密度", "培训；SOP；统计审核"],
            ["环境与流程", "蒸发与边缘效应；运行顺序；孵育环境", "变异", "板布局；环境记录"],
        ],
        "robust.factors": [
            ["A  接种密度（效应/靶）", "−30%", "设定值", "+30%", "窗口与 EC50 主要影响因素"],
            ["B  E:T 比", "低", "设定值", "高", "效应读数灵敏度"],
            ["C  共培养时间", "−2 h", "设定值", "+2 h", "信号动力学"],
            ["D  读数时间点/试剂孵育", "−10 min", "设定值", "+10 min", "信号线性"],
            ["E  细胞代数（类别）", "低", "中", "高", "传代窗口"],
            ["F  效应细胞活率", "判据下限", "设定值", "较高", "样品适用性判据来源"],
        ],
        "robust.par": [
            ["接种密度", "设定值", "待 DoE 确定", "实验编号 P9"],
            ["E:T 比", "设定值", "待 DoE 确定", "实验编号 P9"],
            ["共培养时间", "设定值", "待 DoE 确定", "实验编号 P9"],
            ["细胞代数窗口", "—", "待 P1 确定", "实验编号 P1"],
        ],
        "robust.stability": [
            ["参比品", "−80 ℃ / 气相液氮，冻融 ×1/×3", "0、1、3、6 个月", "", ""],
            ["冻存即用细胞", "气相液氮", "复苏后 0–4 h", "", ""],
            ["产品样品（复苏后静置）", "室温/37 ℃", "0、30、60、120 min", "", ""],
            ["稀释系列", "室温", "0、2、4 h", "", ""],
            ["试剂工作液", "按储存条件", "0、1、4、12 周", "", ""],
        ],
        "control.references": [
            ["内部参比品", "效力基准、SST", "≥ 6 次独立运行赋值；与外部参比（如有）比较", "冻融、储存 0/1/3/6/12 个月", "新批与现行批并行 ≥ 6 次，等效性判定"],
            ["靶细胞库（MCB / WCB）", "抗原刺激来源", "STR/表型、支原体、抗原表达", "冻存稳定性", "新库与旧库并行评价"],
            ["阴性对照（抗原阴性靶/无靶）", "背景与抗原依赖性", "鉴定与表达证明", "—", "新批并行"],
        ],
        "control.reagent_mgmt": [
            ["血清/培养基", "批号、来源、测试结果", "细胞生长与窗口验收测试", "每批", "更换血清批需验收"],
            ["读数试剂", "批号、有效期、储存", "标准曲线/窗口检查", "每批", "—"],
            ["细胞库", "代数、鉴定、支原体", "放行与再确认", "每次建库/每年", "新库桥接"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据影响对 CQA 的控制"],
            ["技术原理（读数与细胞体系）", "高", "PA", "更换读数/体系属原理变更，需桥接"],
            ["细胞代数窗口与活率判据", "中", "NM", "P1 证明；窗口外视为偏离"],
            ["SST 与样品适用性判据", "中", "NM", "控制策略证明性能"],
            ["曲线模型、权重与平行性判据", "高", "NM", "直接决定相对效力"],
            ["接种密度、E:T 比、共培养时间设定点与 PAR", "中", "NM", "DoE 证明；PAR 内不通知"],
            ["板类型/读板仪型号", "低", "NL", "稳健性显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性/抗原依赖", "抗原阴性靶/无靶/无关效应细胞对照；阻断；降解样品响应", "—", "ICH Q2(R2) Table 7；FDA 2024 §IV.C.2.d" + SAMPLE_TAG],
            ["重复性", "单日/短时间，≥ 5 效力水平 × ≥ 3 重复", "50%–200%", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["中间精密度", "不同分析员、独立制备、多天、多细胞批、多个效力水平", "—", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["准确度", "≥ 3 次独立制备 × ≥ 5 效力水平", "—", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["范围", "满足准确度/精密度/响应判据的 ≥ 5 个效力水平", "64%–150%（例）", "ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["稳健性（确认）", "细胞密度、E:T 比、细胞代数、板、缓冲液、孵育、试剂批", "PAR 边界", "ICH Q2(R2) Table 7；ICH Q14 §5.1" + SAMPLE_TAG],
            ["联合评价", "各水平相对误差 90% 容忍区间", "—", "ICH Q2(R2) §3.3.3" + SAMPLE_TAG],
            ["SST 有效性与站点间（如适用）", "故意失败拦截；转移用等效性检验", "—", "ICH Q14 §6；FDA 2023 效力草案 V.C.4" + SAMPLE_TAG],
        ],
    },
}

# ---------------------------------------------------------------------- qpcr
TECHNIQUES["qpcr"] = {
    "label": "qPCR / ddPCR（VCN、残留 DNA、载体拷贝等）",
    "desc": "分子生物学定量方法：引物探针特异性、标准曲线与效率、提取效率与抑制、NTC、LOD/LOQ、动态范围。参考 ICH Q2(R2) Annex 2 Table 8 与 MIQE/dMIQE。",
    "changelog": [
        "1.1：预置 qPCR/ddPCR 初始条件、标准品/引物探针/预混液等关键材料、12 条 FMEA、13 个实验种子（特异性、效率、提取与抑制、动态范围、LOD/QL、加标回收、精密度、参照基因、污染控制）、SST 与验证矩阵",
        "1.1：检查项 qx4–qx11（标准品赋值、内部扩增对照、参照基因、ddPCR 阈值与分区、NTC 污染控制、MIQE/dMIQE 报告）",
    ],
    "matrix": {"options": ["qPCR", "ddPCR", "测序/其他"],
               "criteria": [("灵敏度/QL", 4), ("精密度", 4), ("绝对定量能力", 4), ("抑制耐受性", 3), ("验证成熟度", 3), ("通量", 2), ("成本", 2)]},
    "atp_rows": [
        ["准确度", "加标回收（含提取效率）：3–5 个模板水平，n=6，回收率 70%–130%（低拷贝水平可放宽，示例）", "示例值；提取效率须计入", "ICH Q2(R2) Table 8"],
        ["精密度-重复性", "沿标准曲线 5 个水平各 3 重复，CV ≤ 25%（低拷贝）/ ≤ 15%（高拷贝）", "示例值；设计与 Table 8 一致", "ICH Q2(R2) Table 8"],
        ["精密度-中间精密度", "每水平每运行 ≥ 3 重复，≥ 6 个运行，≥ 2 天；CV ≤ 30%（示例）", "示例值；设计与 Table 8 一致", "ICH Q2(R2) Table 8"],
        ["联合评价(总误差)", "各水平相对误差（偏倚+精密度）落入预设容忍区间（示例 ±35%）", "示例值，须与规格宽度相容", "ICH Q2(R2) §3.3.3"],
        ["线性/响应", "工作范围覆盖 ≥ 5–6 个 log10；标准曲线 R² ≥ 0.98；斜率对应扩增效率 90%–110%", "示例值；Table 8：沿全动态范围计算相关系数/SD", "ICH Q2(R2) Table 8"],
        ["专属性", "NTC 无扩增；RT-qPCR 另设无 RT 对照；引物探针 BLAST 核对；产物经熔解曲线/凝胶/测序证实", "Table 8 的专属性方法", "ICH Q2(R2) Table 8"],
        ["定量下限", "QL = 满足回收率与 CV 判据的最低拷贝水平；DL 为满足曲线参数的最低点", "示例；Table 8", "ICH Q2(R2) Table 8；§3.2.3"],
        ["稳健性/稳定性", "预混液成分/批次、反应体积、引物探针浓度、热循环参数、仪器变动下 SST 通过且结果变化 ≤ 判据；标准品冻融稳定", "示例值", "ICH Q2(R2) Table 8；ICH Q14 §5.1"],
        ["其他", "提取效率与抑制：内部扩增对照 ΔCt ≤ 1.0 或提取回收 ≥ 50%（示例）", "Table 8：须计入 RNA/DNA 提取效率", "ICH Q2(R2) Table 8"],
    ],
    "extra_checklist": {
        "atp": [
            ck("qx1", "报告结果单位与分母已定义（拷贝/μg DNA、拷贝/细胞、VCN 每 CAR+ 细胞等）", "CAR-T 产品 VCN 以 CAR 阳性细胞为分母更能反映风险。", "FDA 2024 CAR-T §IV.C.2.b"),
            ck("qx4", "提取效率与基质抑制纳入准确度评价", "", "ICH Q2(R2) Table 8"),
        ],
        "tech": [
            ck("qx2", "引物探针特异性已核对（BLAST），扩增效率评价方案已定", "", "ICH Q2(R2) Table 8"),
            ck("qx5", "标准品来源、赋值（拷贝数）与稳定性方案已规定（质粒/gBlock/合成片段）", "标准品是绝对定量的基准。", "MIQE（Bustin 等 Clin Chem 2009）；dMIQE（Huggett 等 Clin Chem 2013）", False),
            ck("qx6", "已规划内部扩增对照（IPC）/抑制对照/提取对照", "", "ICH Q2(R2) Table 8", False),
        ],
        "risk": [ck("qx7", "已评估污染（产物/质粒）、提取效率、抑制与引物二聚体风险", "", "ICH Q14 §4.2", False)],
        "plan": [
            ck("qx8", "参照基因与归一化策略（如 VCN 的单拷贝参照基因）已规定；ddPCR 阈值与分区数要求已规定", "", "dMIQE（Huggett 等 2013）；FDA 2024 CAR-T §IV.C.2.b"),
            ck("qx9", "实验区域分区（预扩增/后扩增）与污染控制措施已规定", "", "Ph.Eur. 2.6.21 核酸扩增技术（版本待核对）", False),
        ],
        "robust": [ck("qx3", "提取效率与抑制效应已纳入评价", "", "ICH Q2(R2) Table 8")],
        "control": [
            ck("qx10", "SST：NTC、标准曲线斜率/效率/R²、阳性对照、IPC、ddPCR 微滴数", "", "ICH Q14 §6"),
        ],
        "report": [ck("qx11", "方法描述符合 MIQE/dMIQE 要求的关键信息（引物探针序列、效率、仪器、分析软件等）", "", "MIQE（2009）；dMIQE（2013）", False)],
    },
    "fmea": [
        F("提取效率变异", "样品基质/提取方法", "定量偏倚", 7, 5, 4, "提取对照/加标；回收率评价；统一提取 SOP"),
        F("PCR 抑制", "基质中抑制物", "低估", 7, 4, 4, "IPC/抑制对照；稀释线性；纯化步骤"),
        F("产物或质粒污染", "扩增产物/高浓度标准品", "假阳性", 8, 3, 3, "区域分区；NTC；单向流程；UNG（适用时）"),
        F("引物探针非特异或二聚体", "设计不佳", "假阳性/效率偏离", 7, 3, 4, "BLAST；熔解曲线/测序；优化浓度"),
        F("标准品赋值或稳定性不当", "稀释误差/吸附/冻融", "系统性偏倚", 8, 4, 4, "标准品赋值方案；低结合管；分装一次性使用；稳定性研究"),
        F("扩增效率偏离", "预混液/热循环/引物", "拷贝数偏倚", 7, 4, 3, "效率范围纳入 SST；预混液批验收"),
        F("参照基因不适用或拷贝数异常", "基因多态/拷贝变异", "VCN 偏倚", 7, 3, 5, "参照基因选择与验证；多参照"),
        F("ddPCR 阈值设定主观", "手动阈值", "拷贝数偏差", 7, 4, 4, "阈值规则书面化；NTC 与阳性对照设阈值"),
        F("微滴数/分区不足（ddPCR）", "微滴生成失败", "精密度差", 6, 4, 3, "微滴数下限写入 SST"),
        F("基因组 DNA 质量/浓度测量误差", "定量方法差异", "每细胞拷贝数偏差", 7, 4, 4, "DNA 定量方法验证；统一方法"),
        F("仪器热块不均/校准", "仪器性能", "孔间差异", 5, 3, 4, "仪器确认与校准；板布局随机化"),
        F("数据分析阈值/基线设定", "软件设置", "Ct 偏差", 6, 4, 4, "分析设置书面化；双人复核"),
    ],
    "experiments": [
        X("P0", "引物探针设计与特异性", "确认引物探针特异性",
          "BLAST 核对；熔解曲线/凝胶电泳/测序；阴性基质（NTD DNA、人基因组 DNA）、NTC、无 RT 对照（RT-qPCR）",
          S_("NTC 无扩增；产物单一且序列正确；阴性基质无扩增或 ≥ 判据 Ct。"), "explore", 2),
        X("P1", "标准曲线与扩增效率", "评价标准品梯度与效率",
          "标准品 10 倍梯度 ≥ 7 点，每点 3 重复，≥ 3 次独立运行；计算斜率/效率/R²",
          S_("效率 90%–110%；R² ≥ 0.98；沿曲线残差无趋势。"), "explore", 2),
        X("P2", "提取效率与抑制评价", "评估提取效率与基质抑制",
          "基质加标（提取前/提取后）3 个水平 × n=6；IPC；样品稀释线性（1:1–1:10）；不同基质批",
          S_("提取回收 ≥ 50%（或预设范围）；IPC ΔCt ≤ 1.0；稀释线性无抑制迹象。"), "explore", 2),
        X("P3", "动态范围与线性", "确定工作范围",
          "覆盖 5–6 个 log10；每水平 3 重复 × 3 运行；回归与残差",
          S_("线性回归 R² ≥ 0.98；斜率 95% CI 在预设范围；残差无趋势。"), "explore", 1),
        X("P4", "检测限与定量下限", "确定 DL/QL",
          "低拷贝模板梯度（含 1–20 拷贝/反应）每水平 n=12–24；阳性比例（ddPCR/qPCR）；QL 水平回收率与 CV",
          S_("DL：≥ 95% 阳性检出的最低水平；QL：回收率 70%–130% 且 CV ≤ 判据。"), "robust", 2),
        X("P5", "准确度（加标回收）", "评价准确度",
          "3–5 个模板加标水平，每水平 n=6，计入提取效率；与正交方法（ddPCR vs qPCR 或已知参比）比较",
          S_("回收率 70%–130%（低拷贝放宽）；与正交方法一致性在预设内。"), "robust", 2),
        X("P6", "重复性与中间精密度", "估计重复性与中间精密度",
          "重复性：沿标准曲线 5 水平各 3 重复；中间精密度：每水平每运行 ≥ 3 重复，≥ 6 个运行，≥ 2 天，2 分析员",
          S_("重复性 CV ≤ 25%（示例）；中间精密度 CV ≤ 30%（示例）。"), "robust", 2),
        X("P7", "参照基因与归一化", "验证参照基因/DNA 量归一化",
          "多个候选单拷贝参照基因；不同供者 gDNA；参照基因扩增效率；拷贝数一致性",
          S_("参照基因每供者拷贝数一致（CV ≤ 判据），效率与目标基因可比。"), "explore", 1),
        X("P8", "污染控制与 NTC", "验证分区与污染控制措施",
          "模拟污染（高浓度模板邻近 NTC）、擦拭检测；各 n=3 次运行",
          S_("NTC 均无扩增；擦拭检测阴性；污染措施有效。"), "explore", 1),
        X("P9", "DoE 稳健性", "确定关键参数及 PAR",
          "因子：预混液浓度/批次、反应体积、引物探针浓度、退火温度/时间、模板量；部分因子 + 中心点；响应：Cq/浓度、效率、CV",
          S_("关键参数确定；PAR 内结果变化 ≤ 判据，效率 90%–110%。"), "robust", 3),
        X("P10", "标准品与模板稳定性", "确定标准品、稀释液与提取物保存时限",
          "标准品 −20 ℃/−80 ℃ 冻融 ×1/×3/×5；稀释后室温/4 ℃ 0–24 h；提取 DNA 保存 0–4 周",
          S_("变化 ≤ 判据（示例 ≤ 0.3 Cq 或 ≤ 20%）。"), "robust", 2),
        X("P11", "SST 判据与挑战", "由开发数据定 SST，并检验其拦截能力",
          "故意制造：标准品降解、引物探针浓度偏离、抑制物加标、污染 NTC；各 3 次",
          S_("SST（NTC、效率/R²、阳性对照、IPC）能拦截全部故意失败。"), "control", 1),
        X("P12", "预验证演练", "两名分析员按 SOP 草案运行",
          "各 3 次独立运行，含标准曲线、样品、对照、SST；评估 SOP 清晰度与周转",
          S_("SOP 可执行；SST 拦截全部故意失败；偏差闭合。"), "report", 1),
    ],
    "sst": [
        ["NTC（无模板对照）", "无扩增（或 Cq > 判据）", "污染", "运行无效；清洁与调查"],
        ["标准曲线斜率/效率与 R²", "效率 90%–110%；R² ≥ 0.98（示例）", "扩增效率/曲线质量", "运行无效"],
        ["阳性对照（已知拷贝）", "在控制限内", "系统性能", "运行无效"],
        ["内部扩增对照 / 抑制对照", "ΔCt ≤ 1.0（示例）", "抑制", "样品稀释或重提取"],
        ["提取对照（加标回收）", "≥ 判据（示例 50%）", "提取效率", "重提取"],
        ["微滴数（ddPCR）", "≥ 10,000（示例）", "分区质量", "运行无效"],
    ],
    "ph": {
        "atp.use": "测定 XX 样品（细胞产品/原液）中 XX 靶序列的拷贝数（VCN / 载体拷贝 / 残留 DNA）；用于放行与安全性评价；适用阶段 XX。",
        "atp.attribute": "属性：每二倍体细胞（或每 CAR 阳性细胞）的载体拷贝数 VCN（或残留 DNA 量）。规格（预期）：VCN ≤ XX 拷贝/细胞。关联：插入诱变风险；以 CAR 阳性细胞为分母更能反映风险（FDA 2024 §IV.C.2.b）。",
        "atp.specificity": "引物探针对目标序列特异；NTC 无扩增；无 RT 对照（RT-qPCR）；阴性基质（NTD gDNA）无扩增；产物经熔解曲线/测序证实。",
        "atp.sampling": "gDNA 提取：样品细胞数 XX、提取方法 XX、洗脱体积 XX；DNA 保存 −20 ℃ ≤ XX 周；浓度/纯度测定方法 XX。",
        "tech.principle": "从样品提取 gDNA，经 qPCR（或 ddPCR 微滴分区）扩增靶序列与单拷贝参照基因；标准曲线（或泊松统计）将 Cq（或阳性微滴数）换算为拷贝数；VCN = 靶拷贝/参照拷贝 ×（参照基因每细胞拷贝数），必要时除以 CAR 阳性比例。",
        "plan.strategy": "先确认引物探针特异性（P0）与标准曲线/效率（P1），评估提取效率与抑制（P2）、动态范围（P3）与 DL/QL（P4）；条件固定后做加标回收（P5）、精密度（P6）、参照基因（P7）与污染控制（P8）；DoE（P9）、稳定性（P10）与 SST 挑战（P11）后预验证（P12）。",
        "plan.statistics": "标准曲线：线性回归（log10 拷贝 vs Cq），斜率/效率/R² 及 95% CI；DL：阳性比例（Probit/Logit）；精密度：Cq 或对数浓度的方差分量，CV；回收率：均值与 95% CI；ddPCR：泊松校正与 CI；软件及版本：XX。",
        "plan.sample_size": "标准曲线 ≥ 7 点 × 3 重复 × 3 运行；加标 3–5 水平 × n=6；中间精密度每水平每运行 ≥ 3 重复，≥ 6 运行，≥ 2 天；LOD 每水平 n=12–24；设计与 ICH Q2(R2) Table 8 对应。",
        "plan.decision_rules": "NTC 污染则运行无效并调查；效率不在 90%–110% 则回到引物探针/预混液优化；提取回收低于预设则优化提取，不得用校正因子掩盖不稳定提取。",
        "report.sop_sample": "按 XX 提取 gDNA，洗脱 XX µL；NanoDrop/荧光法定量并记录；稀释至 XX ng/µL；提取后 ≤ XX h 内上机或 −20 ℃ 保存 ≤ XX 周。",
        "report.sop_settings": "仪器：XX；反应体系 XX µL（预混液 XX、引物 XX nM、探针 XX nM、模板 XX ng）；热循环：XX；分析：基线/阈值规则 XX；ddPCR：微滴数 ≥ XX，阈值规则 XX。",
        "report.sop_procedure": "1. 提取/稀释 DNA；2. 在预扩增区配制预混液；3. 加入标准品、样品、NTC、阳性对照、IPC（板布局随机化）；4. 封板，转至扩增区运行；5. 分析 Cq/微滴；6. 检查 SST；7. 计算拷贝数/VCN。",
        "report.sop_calc": "拷贝数 = 10^((Cq − b)/m)（m、b 为标准曲线斜率与截距）；ddPCR：λ = −ln(1 − p)；VCN = 靶拷贝 / 参照基因拷贝 × 参照基因每细胞拷贝数；可报告结果 = 独立重复均值。",
        "report.sop_sst": "NTC 无扩增；标准曲线效率 90%–110%、R² ≥ 0.98；阳性对照在控制限内；IPC ΔCt ≤ 1.0；提取对照回收 ≥ XX%；ddPCR 微滴数 ≥ XX。任一失败运行无效。",
    },
    "seeds": {
        "charter.glossary": [
            ["Cq / Ct", "定量循环数", "荧光信号达到阈值时的循环数。"],
            ["NTC", "No Template Control 无模板对照", "检测污染的对照。"],
            ["IPC", "Internal Positive Control 内部扩增对照", "检测抑制与提取失败。"],
            ["VCN", "Vector Copy Number 载体拷贝数", "每细胞（或每 CAR 阳性细胞）整合的载体拷贝数。"],
            ["扩增效率", "Efficiency", "E = 10^(−1/斜率) − 1；理想 100%。"],
            ["ddPCR", "微滴式数字 PCR", "将反应分区并以泊松统计绝对定量。"],
            ["DL / QL", "检测限 / 定量下限", "见 ICH Q2(R2) Table 8 的定义方式。"],
            ["MIQE / dMIQE", "定量 PCR / 数字 PCR 实验发表的最小信息", "实验报告规范。"],
        ],
        "charter.refdocs": [
            ["法规/指南", "ICH Q2(R2) Annex 2 Table 8：Example for quantitative PCR", "见上方 ICH Q2(R2)", "qPCR 验证设计示例"],
            ["法规/指南", "FDA Considerations for the Development of CAR T Cell Products", "FDA，2024-01", "§IV.C.2.b VCN；§IV.C.2.c 同一性"],
            ["法规/指南", "FDA Chemistry, Manufacturing, and Control (CMC) Information for Human Gene Therapy INDs", "FDA，2020-01", "基因治疗产品 CMC 与方法"],
            ["文献", "Bustin SA 等. The MIQE Guidelines", "Clin Chem 2009", "qPCR 实验最小信息"],
            ["文献", "Huggett JF 等. The Digital MIQE Guidelines", "Clin Chem 2013", "dPCR 实验最小信息"],
            ["药典", "Ph.Eur. 2.6.21 Nucleic acid amplification techniques", "现行版（版本待核对）", "核酸扩增技术通则"],
            ["行业标准", "ISO 20395 Biotechnology — Requirements for evaluating the performance of quantification methods for nucleic acid target sequences — qPCR and dPCR", "2019（版本待核对）", "定量方法性能评价"],
        ],
        "tech.conditions": [
            ["样品", "gDNA 提取与洗脱", "XX 试剂盒，XX 细胞，洗脱 XX µL", "提取方法/量", "提取效率评价 P2"],
            ["样品", "模板量/反应", "XX ng gDNA / 反应", "±20%", "DoE 因子"],
            ["试剂/溶液", "预混液与浓度", "XX（含 ROX 等）", "批次；浓度 ±", "ICH Q2(R2) Table 8 稳健性"],
            ["试剂/溶液", "引物/探针浓度", "各 XX nM / XX nM", "±20%", "DoE 因子"],
            ["反应/染色/孵育", "热循环程序", "95 ℃ XX → 40 × (95 ℃/60 ℃)", "退火温度 ±2 ℃", "效率优化"],
            ["仪器/检测", "反应体积与板布局", "XX µL；随机化", "体积 ±", "边缘/孔位效应"],
            ["数据处理", "基线/阈值设定", "自动基线；阈值 XX（指数期）", "—", "书面化规则"],
            ["数据处理", "标准曲线与定量", "10 倍梯度 ≥ 7 点，log10 回归", "—", "标准品赋值方案"],
            ["数据处理", "参照基因与 VCN 计算", "单拷贝基因 XX", "—", "P7 评价"],
            ["仪器/检测", "ddPCR：微滴数与阈值", "≥ 10,000 微滴；阈值规则 XX", "—", "dMIQE"],
            ["保存/稳定性", "标准品与提取物保存", "−20/−80 ℃，分装", "冻融次数", "P10"],
        ],
        "tech.reagents": [
            ["标准品（质粒 / gBlock / 合成片段）", "绝对定量基准", "自制/供应商", "关键", "赋值错误、吸附、稀释误差", "赋值方案；低结合管；一次性分装；稳定性"],
            ["引物与探针", "靶/参照基因扩增", "合成", "关键", "批间纯度/浓度差异", "批验收；效率检查；序列核对"],
            ["预混液（含聚合酶）", "扩增", "供应商", "关键", "批间差异", "批验收；效率检查"],
            ["gDNA 提取试剂盒", "提取", "供应商", "重要", "回收率批间差", "提取对照；批验收"],
            ["NTD gDNA / 阳性对照 gDNA", "阴性/阳性对照", "自制/细胞系", "关键", "污染、拷贝变化", "鉴定；分装"],
            ["IPC 试剂 / 抑制对照", "检测抑制", "供应商", "重要", "批差", "批验收"],
        ],
        "plan.materials": [
            ["标准品（质粒 / gBlock）", "参比品/标准品", "", "", "", "关键", "按赋值方案与稳定性监测", "待采购"],
            ["引物与探针", "试剂", "", "", "", "关键", "新批效率检查", "待采购"],
            ["预混液", "试剂", "", "", "", "关键", "新批验收", "待采购"],
            ["gDNA 提取试剂盒", "试剂", "", "", "", "重要", "提取对照", "待采购"],
            ["NTD gDNA 与阳性对照 gDNA", "对照", "", "", "", "关键", "批鉴定", "待采购"],
            ["低结合管、板、封膜、滤芯吸头", "耗材", "", "", "", "一般", "—", "待采购"],
            ["TE / 无核酸酶水", "溶液/缓冲液", "", "", "", "一般", "批号记录", "待采购"],
        ],
        "plan.instruments": [
            ["实时荧光定量 PCR 仪 / 微滴式数字 PCR 系统", "—", "扩增与读数", "待确认", "IQ/OQ/PQ；热块均一性与光学校准", ""],
            ["核酸定量仪（分光/荧光）", "—", "DNA 定量", "待确认", "校准核对", ""],
            ["生物安全柜 / PCR 洁净工作台", "—", "预扩增操作", "待确认", "年度检定；UV 清洁记录", ""],
            ["离心机、移液器（滤芯吸头）", "—", "样品处理", "校准有效", "按设备校准计划", ""],
            ["冰箱 / −80 ℃ 冰箱", "—", "试剂与标准品储存", "待确认", "温度监测", ""],
        ],
        "plan.software": [
            ["qPCR / ddPCR 分析软件", "（填写）", "Cq/微滴分析、定量", "待验证", "开启"],
            ["统计软件", "（填写）", "回归、方差分量、DL 估计", "待验证", "不适用"],
            ["受控计算模板", "（填写）", "拷贝数、VCN 计算", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["产品样品（≥ 3 批）", "细胞产品/原液，覆盖不同 VCN 水平", "冻存或新鲜 gDNA", "提取后 ≤ XX 周", "准确度、精密度"],
            ["NTD / 阴性基质 gDNA", "非转导对照 gDNA", "−20 ℃", "—", "专属性、背景"],
            ["加标样品", "阴性基质 + 标准品梯度", "新鲜配制", "—", "准确度、LOD/QL、提取与抑制"],
            ["阳性对照 gDNA", "已知拷贝", "−20 ℃ 分装", "—", "SST、趋势"],
            ["标准品梯度", "10 倍梯度 ≥ 7 点", "新鲜稀释", "稀释后 ≤ XX h", "标准曲线"],
        ],
        "risk.ishikawa": [
            ["样品", "gDNA 质量与浓度；基质抑制物；提取效率", "准确度；精密度", "提取对照；IPC；DNA 定量验证"],
            ["试剂与材料", "标准品赋值与稳定性；引物探针批差；预混液批差", "效率；偏倚", "批验收；赋值方案"],
            ["仪器", "热块均一性；光学校准；ddPCR 微滴生成", "孔间差；精密度", "确认与校准；板布局随机化"],
            ["方法", "引物探针浓度；退火温度；阈值/基线；参照基因", "效率；定量偏差", "DoE；规则书面化"],
            ["人员与分析", "稀释与加样；阈值设定；数据转录", "精密度；偏倚", "培训；双人复核；模板验证"],
            ["环境与流程", "污染；分区；冻融", "假阳性；稳定性", "分区；NTC；单向流程"],
        ],
        "robust.factors": [
            ["A  预混液浓度/批次（类别）", "批 1", "批 2", "批 3", "ICH Q2(R2) Table 8 稳健性"],
            ["B  引物探针浓度", "−20%", "设定值", "+20%", "效率与特异性"],
            ["C  退火温度", "−2 ℃", "设定值", "+2 ℃", "特异性/效率"],
            ["D  反应体积", "−10%", "设定值", "+10%", "孔间体积误差"],
            ["E  模板量", "−20%", "设定值", "+20%", "抑制/线性"],
        ],
        "robust.par": [
            ["退火温度", "设定值", "待 DoE 确定", "实验编号 P9"],
            ["引物探针浓度", "设定值", "待 DoE 确定", "实验编号 P9"],
            ["模板量", "设定值", "待 DoE 确定", "实验编号 P9"],
        ],
        "robust.stability": [
            ["标准品（冻融）", "−20/−80 ℃，冻融 ×1/×3/×5", "每次冻融后", "", ""],
            ["标准品稀释液", "室温/4 ℃", "0–24 h", "", ""],
            ["提取 gDNA", "−20 ℃", "0、1、2、4 周", "", ""],
            ["预混液工作液（配制后）", "4 ℃ / 室温", "0–8 h", "", ""],
        ],
        "control.references": [
            ["标准品", "绝对定量基准", "拷贝数赋值（数字 PCR 或分光法交叉）", "冻融与储存稳定性", "新批与现行批并行"],
            ["阳性对照 gDNA", "SST、趋势", "已知拷贝数；多次运行赋值", "−20 ℃ 稳定性", "新批并行"],
            ["NTD gDNA（阴性）", "背景", "鉴定", "—", "新批并行"],
        ],
        "control.reagent_mgmt": [
            ["引物与探针", "序列、纯度、浓度", "效率与 Cq 与现批比较", "每批", "序列变更视为较大变更"],
            ["预混液", "批号、组成", "标准曲线效率验收", "每批", "更换供应商需桥接"],
            ["提取试剂盒", "批号", "提取对照回收", "每批", "更换试剂盒需重新评价提取效率"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据影响对安全性属性的控制"],
            ["技术原理（qPCR / ddPCR）", "高", "PA", "原理变更需桥接"],
            ["引物探针序列与靶区", "高", "PA", "决定专属性"],
            ["参照基因与归一化方式", "高", "NM", "直接决定 VCN"],
            ["SST 判据", "中", "NM", "控制策略证明性能"],
            ["提取方法", "中", "NM", "影响回收；变更需评价"],
            ["热循环微调/板类型", "低", "NL", "稳健性显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性", "NTC、无 RT、阴性基质；BLAST；熔解曲线/测序", "—", "ICH Q2(R2) Table 8" + SAMPLE_TAG],
            ["重复性", "沿标准曲线 5 个水平各 3 重复", "5 水平", "ICH Q2(R2) Table 8" + SAMPLE_TAG],
            ["中间精密度", "每水平每运行 ≥ 3 重复，≥ 6 运行，≥ 2 天", "—", "ICH Q2(R2) Table 8" + SAMPLE_TAG],
            ["准确度（加标）", "3–5 个模板加标水平，n=6，计入提取效率", "—", "ICH Q2(R2) Table 8" + SAMPLE_TAG],
            ["范围与线性", "工作范围覆盖 ≥ 5–6 log10；全范围相关系数/SD", "—", "ICH Q2(R2) Table 8" + SAMPLE_TAG],
            ["DL / QL", "由加标或标准曲线确定；QL 显示足够回收与 CV", "—", "ICH Q2(R2) Table 8" + SAMPLE_TAG],
            ["稳健性（确认）", "仪器、预混液成分/批次、反应体积、引物探针浓度、热循环参数", "PAR 边界", "ICH Q2(R2) Table 8；ICH Q14 §5.1" + SAMPLE_TAG],
            ["SST 有效性", "故意失败应被拦截", "—", "ICH Q14 §6" + SAMPLE_TAG],
        ],
    },
}


# ---------------------------------------------------------------------- elisa
TECHNIQUES["elisa"] = {
    "label": "免疫化学/结合法（ELISA、SPR、MSD）：浓度或相对结合活性",
    "desc": "结合法定量/相对结合活性：包被/封闭/曲线拟合、基质干扰与最小要求稀释、稀释线性、钩状效应、平行性、关键试剂管理。",
    "changelog": [
        "1.1：预置 ELISA 初始条件（包被/封闭/孵育/洗涤/显色）、关键试剂（捕获/检测抗体、标准品、QC）、12 条 FMEA、13 个实验种子（棋盘滴定、曲线模型、基质/MRD、稀释线性与钩状效应、平行性、交叉反应、LLOQ/ULOQ、关键试剂桥接等）、SST/QC、验证矩阵",
        "1.1：检查项 ex3–ex11（曲线模型与权重、回算准确度、MRD、平行性、关键试剂批放行、板内位置效应、冻融稳定性等）",
    ],
    "matrix": {"options": ["夹心 ELISA", "竞争 ELISA", "SPR", "电化学发光（MSD）"],
               "criteria": [("专属性", 5), ("灵敏度/LLOQ", 4), ("动态范围", 3), ("精密度", 4), ("基质耐受性", 3), ("通量", 3), ("成本", 2)]},
    "atp_rows": [
        ["准确度", "稀释线性/加标回收：回收率 80%–120%（LLOQ/ULOQ 75%–125%）；相对偏倚无趋势", "示例值，参照 ICH M10 对 LBA 的要求原则；质量控制检测须按产品规格确认", "ICH M10 §4.2.4（原则借用）；ICH Q2(R2) Table 7"],
        ["精密度-重复性", "板内 ≥ 3 重复，CV ≤ 15%（LLOQ/ULOQ ≤ 20%）", "示例值", "ICH M10 §4.2.4（原则借用）"],
        ["精密度-中间精密度", "不同分析员/天/板/试剂批，CV ≤ 20%（LLOQ/ULOQ ≤ 25%）", "示例值", "ICH Q2(R2) Table 7"],
        ["联合评价(总误差)", "总误差（|偏倚|+CV）≤ 30%（LLOQ/ULOQ ≤ 40%）", "示例值，参照 M10 对 LBA 的总误差；须按规格确认", "ICH M10 §4.2.4（原则借用）；ICH Q2(R2) §3.3.3"],
        ["线性/响应", "校准曲线 4PL/5PL 拟合：回算浓度偏差 ≤ 20%（LLOQ/ULOQ ≤ 25%）；不要求浓度-信号线性", "示例值", "ICH Q2(R2) §3.2.2.2；ICH M10 §4.2.3（原则借用）"],
        ["专属性", "基质干扰（≥ 6 个来源）回收在判据内；交叉反应物（相关分析物/代谢物）交叉反应率 < XX%", "示例值", "ICH Q2(R2) Table 7；ICH M10 §4.2.1–4.2.2（原则借用）"],
        ["定量下限", "LLOQ：信号 ≥ 空白 +（示例 5×SD），且准确度与精密度满足判据；ULOQ 同理", "示例值", "ICH Q2(R2) §3.2.3；ICH M10 §4.2.3（原则借用）"],
        ["稳健性/稳定性", "孵育时间/温度、洗涤次数、板型、关键试剂批次变动下 QC 回收在判据内；样品冻融/室温稳定性已确定", "示例值", "ICH Q2(R2) Table 7；ICH M10 §4.2.7（原则借用）"],
        ["其他", "稀释线性与钩状效应：高于 ULOQ 的样品经稀释后线性，最高预期浓度 ×X 不出现信号下降；相对结合活性需平行性", "示例值", "ICH M10 §4.2.6、§7.2（原则借用）"],
    ],
    "extra_checklist": {
        "atp": [
            ck("ex3", "报告结果类型已区分：绝对浓度 vs 相对结合活性（相对效力）", "类型决定校准、参比与判据设计。", "ICH Q2(R2) Table 7", False),
            ck("ex4", "基质、最小要求稀释（MRD）与样品稀释范围的要求已写明", "", "ICH M10 §7.4（原则借用）", False),
        ],
        "tech": [
            ck("ex1", "关键试剂（包被/捕获/检测抗体）数据表与寿命管理已规划", "", "ICH M10 §4.1.2（原则借用）"),
            ck("ex5", "标准品/参比品来源、赋值与替换方案已定", "", "ICH M10 §4.1.1（原则借用）"),
        ],
        "risk": [ck("ex6", "已评估基质效应、钩状效应、板内位置效应与交叉反应风险", "", "ICH Q14 §4.2", False)],
        "plan": [ck("ex7", "曲线模型（4PL/5PL）与权重、回算准确度判据与异常值规则已预先规定", "", "ICH M10 §4.2.3（原则借用）；USP <1034>（条款待核对）")],
        "explore": [ck("ex8", "棋盘滴定与试剂配对已完成，信号窗口与背景满足预设", "", "USP <1103>（ELISA，条款待核对）", False)],
        "robust": [
            ck("ex2", "稀释线性与钩状效应已评价", "", "ICH M10 §4.2.6（原则借用）"),
            ck("ex9", "样品冻融/室温稳定性与包被板/试剂稳定性已评价", "", "ICH M10 §4.2.7（原则借用）"),
        ],
        "control": [
            ck("ex10", "SST/QC 水平（低/中/高）与运行接受标准已定义；关键试剂批放行与桥接规则已建立", "", "ICH M10 §4.3.2（原则借用）；ICH Q14 §6"),
        ],
        "report": [ck("ex11", "验证设计覆盖：特异性、选择性、校准范围、准确度与精密度、稀释线性、稳定性", "", "ICH Q2(R2) Table 7；ICH M10 §4.2（原则借用）", False)],
    },
    "fmea": [
        F("关键试剂批间差", "抗体/标准品批次", "曲线与灵敏度变化", 7, 5, 4, "批放行与桥接；数据表；预留批次"),
        F("基质干扰", "样品基质成分", "偏倚/假阳性", 7, 4, 4, "基质加标；MRD；稀释线性"),
        F("钩状效应", "极高浓度", "低估", 8, 3, 4, "稀释线性评价；高浓度样品多点稀释"),
        F("交叉反应", "相关分子", "假阳性/偏倚", 7, 3, 4, "交叉反应物评价；特异性证明"),
        F("板内位置效应", "温度/蒸发/洗板不均", "孔间变异", 5, 5, 3, "板布局随机化；洗板器确认；QC 分布于板内"),
        F("洗涤不充分", "洗板器/残留", "背景升高", 6, 4, 3, "洗板次数与残留体积规定；背景 SST"),
        F("标准品赋值或稳定性不当", "赋值/冻融", "系统性偏倚", 8, 3, 4, "标准品赋值方案；分装；稳定性"),
        F("曲线拟合模型/权重不当", "模型选择", "低浓度/高浓度偏倚", 7, 3, 5, "预先规定模型与权重；回算准确度"),
        F("包被不均/封闭不足", "包被条件", "孔间差异与背景", 6, 4, 4, "包被条件优化；板内 CV SST"),
        F("底物/显色时间偏差", "时间/温度", "信号偏差", 5, 4, 3, "计时；终止；PAR"),
        F("样品稀释误差", "移液/梯度", "回收偏差", 7, 4, 4, "稀释方案验证；独立稀释"),
        F("样品冻融/保存不当", "冻融次数", "分析物降解", 7, 4, 4, "冻融稳定性研究；规定次数"),
    ],
    "experiments": [
        X("P0", "试剂配对与棋盘滴定", "选择抗体配对与最佳包被/检测浓度",
          "包被/检测抗体棋盘滴定；标准品高/低；空白与基质；n=2 板",
          S_("信号窗口（高/空白）≥ 10；空白 OD ≤ XX；选取使窗口最大且背景低的组合。"), "explore", 2),
        X("P1", "曲线模型与拟合", "确定校准曲线模型与权重",
          "8 点 2–3 倍梯度，每点双/三孔，≥ 6 次独立运行；比较 4PL/5PL、权重",
          S_("回算浓度偏差 ≤ 20%（LLOQ/ULOQ ≤ 25%）；至少 75% 标准点达标；选定模型与权重。"), "explore", 1),
        X("P2", "基质效应与 MRD", "评价基质干扰并确定最小要求稀释",
          "≥ 6 个个体/批基质；低/高加标；稀释 1:1–1:20；回收率",
          S_("至少 80% 个体回收在 80%–120%；确定 MRD。"), "explore", 2),
        X("P3", "稀释线性与钩状效应", "评价稀释线性与钩状效应",
          "高于 ULOQ 的样品/加标样品系列稀释至曲线内；最高预期浓度 ×X；n=3",
          S_("稀释校正后回收 80%–120%、CV ≤ 20%；无钩状效应。"), "explore", 1),
        X("P4", "平行性（相对结合活性，如适用）", "评价样品与参比曲线平行性",
          "参比与 ≥ 3 批样品曲线；渐近线比/斜率比；降解样品",
          S_("渐近线/斜率比 0.8–1.2（或等效性检验通过）；降解样品被识别。"), "explore", 1),
        X("P5", "特异性与交叉反应", "评价对相关分子的交叉反应",
          "相关分析物/代谢物/同源蛋白高浓度加入；n=3",
          S_("交叉反应率 < XX%；对 QC 回收影响 ≤ 20%。"), "explore", 1),
        X("P6", "LLOQ / ULOQ", "确定定量下限与上限",
          "低/高浓度 5 个水平 × n=5–6 × 3 运行；回算准确度与 CV；信号/空白",
          S_("LLOQ/ULOQ 处准确度 ±25%、CV ≤ 25%；信号 ≥ 空白+5SD（示例）。"), "robust", 2),
        X("P7", "准确度与精密度", "评价准确度、重复性、中间精密度",
          "QC 低/中/高 + LLOQ/ULOQ，每运行 n=5–6，≥ 6 个运行、≥ 2 分析员；总误差",
          S_("准确度 ±20%（LLOQ/ULOQ ±25%）；CV ≤ 20%（≤ 25%）；总误差 ≤ 30%（≤ 40%）。"), "robust", 2),
        X("P8", "DoE 稳健性", "确定关键参数及 PAR",
          "因子：包被浓度/时间、封闭时间、样品孵育时间/温度、洗涤次数、检测抗体浓度、底物显色时间、板类型；部分因子 + 中心点；响应：窗口、QC 回收、CV",
          S_("关键参数确定；PAR 内 QC 回收在判据内。"), "robust", 3),
        X("P9", "稳定性", "确定样品冻融/室温、包被板与试剂稳定性",
          "样品冻融 ×1/×3/×5，室温 0–24 h，2–8 ℃ 0–7 d；包被板 0–4 周；试剂工作液",
          S_("变化 ≤ 20%；确定允许冻融次数与保存时限。"), "robust", 2),
        X("P10", "关键试剂批次桥接", "建立关键试剂批放行与桥接规则",
          "2 批捕获/检测抗体与 2 批标准品并排；QC 与样品比较",
          S_("QC 回收差 ≤ 15%；曲线参数差在预设内。"), "control", 1),
        X("P11", "SST / QC 挑战", "检验 SST/QC 的拦截能力",
          "故意制造：标准品降解、检测抗体减量、洗涤不足、孵育偏离；各 3 次",
          S_("SST/QC 接受标准能拦截全部故意失败。"), "control", 1),
        X("P12", "预验证演练", "两名分析员按 SOP 草案运行",
          "各 3 次独立运行，含曲线、QC、样品；评估 SOP 清晰度与周转",
          S_("SOP 可执行；SST/QC 拦截全部故意失败；偏差闭合。"), "report", 1),
    ],
    "sst": [
        ["校准曲线拟合与回算", "≥ 75% 标准点回算偏差 ≤ 20%（LLOQ/ULOQ ≤ 25%）（示例）", "曲线质量", "运行无效"],
        ["QC 水平回收（低/中/高）", "≥ 2/3 QC 且每水平 ≥ 50% 在 ±20% 内（示例）", "准确度", "运行无效"],
        ["空白/零标准信号", "≤ 判据", "背景/洗涤", "调查；重做"],
        ["最大/最小信号比", "≥ 判据（示例 10）", "试剂活性", "运行无效"],
        ["重复孔 CV", "≤ 15%（示例）", "移液/板效应", "该点剔除或重做（预先规则）"],
        ["相对结合活性：平行性", "渐近线/斜率比 0.8–1.2（示例）", "相似性", "样品结果无效"],
    ],
    "ph": {
        "atp.use": "测定 XX 样品（血清/细胞培养上清/原液/制剂）中 XX 的浓度（或相对结合活性）；用于放行/稳定性/过程控制；适用阶段 XX。",
        "atp.attribute": "属性：XX 的含量（浓度，单位 XX）或相对结合活性（%，相对参比品）。规格（预期）：XX。关联：XX。",
        "atp.specificity": "基质（≥ 6 个来源）无干扰；相关分子/代谢物交叉反应率 < XX%；稀释线性良好；无钩状效应。",
        "atp.sampling": "样品稀释：MRD = 1:XX；允许冻融 ≤ XX 次；2–8 ℃ ≤ XX d；室温 ≤ XX h。",
        "tech.principle": "夹心 ELISA：捕获抗体包被于微孔板，样品中分析物被捕获，经酶标记检测抗体结合并显色，信号与分析物量成比例；以标准品梯度建立 4PL/5PL 校准曲线，回算样品浓度。相对结合活性测定则以样品与参比曲线的水平位移计算。",
        "plan.strategy": "先棋盘滴定选配对（P0）并确定曲线模型（P1）；基质/MRD（P2）、稀释线性与钩状效应（P3）、平行性（P4）与特异性（P5）；LLOQ/ULOQ（P6）、准确度与精密度（P7）；DoE（P8）与稳定性（P9）；关键试剂桥接（P10）与 SST/QC 挑战（P11）后预验证（P12）。",
        "plan.statistics": "校准曲线：4PL/5PL，权重 1/y² 或 XX；回算准确度；准确度/精密度：方差分量与总误差；稀释线性：回收率与 CV；平行性：渐近线/斜率比或等效性检验；稳定性：相对基线变化；软件及版本：XX。",
        "plan.sample_size": "基质 ≥ 6 个来源；LLOQ/ULOQ 每水平 n=5–6 × 3 运行；QC 每运行 n=5–6，≥ 6 运行、≥ 2 分析员；曲线 ≥ 6 次独立运行。",
        "plan.decision_rules": "窗口 < 判据或背景高则回到试剂配对；基质回收不达标则增加 MRD 或更换基质稀释液；曲线模型与权重在看数据前确定，不得为通过而更换。",
        "report.sop_sample": "样品按 MRD 1:XX 用 XX 稀释液稀释，双/三孔上板；超出 ULOQ 者按 XX 倍稀释重测；样品冻融不超过 XX 次。",
        "report.sop_settings": "包被：XX µg/mL，XX ℃ XX h；封闭：XX，XX min；样品孵育：XX ℃ XX min；检测抗体：XX；洗涤：XX 次 × XX µL；底物显色 XX min，终止后读 XX nm。",
        "report.sop_procedure": "1. 包被并封闭；2. 加标准品、QC、样品；3. 孵育并洗涤；4. 加检测抗体；5. 洗涤；6. 加底物显色并终止；7. 读数；8. 曲线拟合与回算；9. SST/QC 判定。",
        "report.sop_calc": "4PL：y = D + (A − D)/(1 + (x/C)^B)；回算浓度 = C·((A − D)/(y − D) − 1)^(1/B)；乘稀释倍数得样品浓度；报告平均值与 CV；相对结合活性 = 参比 EC50 / 样品 EC50。",
        "report.sop_sst": "曲线回算达标；QC 低/中/高回收在 ±20% 内；空白 ≤ XX；重复孔 CV ≤ XX%；相对结合活性：平行性 0.8–1.2（示例）。任一失败运行无效。",
    },
    "seeds": {
        "charter.glossary": [
            ["LBA", "Ligand-Binding Assay 配体结合分析", "ELISA/SPR/MSD 等基于抗原-抗体结合的方法。"],
            ["MRD", "Minimum Required Dilution 最小要求稀释", "使基质干扰降至可接受水平的最低稀释倍数。"],
            ["钩状效应", "Hook / prozone effect", "极高浓度下信号下降导致低估。"],
            ["稀释线性", "Dilution linearity", "超出 ULOQ 的样品经稀释后回算仍与稀释倍数成比例。"],
            ["LLOQ / ULOQ", "定量下限 / 上限", "满足准确度与精密度的最低/最高浓度。"],
            ["QC 样品", "Quality control sample", "已知浓度、用于判定运行有效性的样品（低/中/高）。"],
            ["4PL / 5PL", "四/五参数 Logistic", "非线性校准曲线模型。"],
            ["关键试剂", "Critical reagent", "对测定性能有重要影响的试剂（抗体、标准品等）。"],
        ],
        "charter.refdocs": [
            ["法规/指南", "ICH M10 Bioanalytical Method Validation and Study Sample Analysis（LBA 部分）", "ICH Step 4，2022-05", "§4 配体结合分析：关键试剂、校准曲线、准确度与精密度、稀释线性与钩状效应、稳定性（原则借用）"],
            ["法规/指南", "ICH Q2(R2) Annex 2 Table 7：Example for biological assays（binding assay）", "见上方 ICH Q2(R2)", "结合法验证设计示例"],
            ["药典", "USP <1103> Immunological Test Methods—ELISA", "USP–NF 现行版（条款待核对）", "ELISA 通则"],
            ["药典", "USP <1105> Immunological Test Methods—Surface Plasmon Resonance", "USP–NF 现行版（条款待核对）", "SPR 通则"],
            ["药典", "USP <1034> Analysis of Biological Assays", "USP–NF 现行版（条款待核对）", "曲线拟合、平行性、相对效力"],
        ],
        "tech.conditions": [
            ["试剂/溶液", "包被抗体浓度与条件", "XX µg/mL，XX ℃，XX h（或过夜）", "0.5×–2× 浓度；时间", "棋盘滴定 P0"],
            ["试剂/溶液", "封闭液与时间", "XX% BSA / 酪蛋白，XX min", "封闭剂种类/时间", "背景控制"],
            ["样品", "样品稀释液与 MRD", "XX 稀释液，MRD 1:XX", "1:1–1:20", "基质效应 P2"],
            ["反应/染色/孵育", "样品孵育", "XX min，室温/37 ℃", "±15 min；±", "DoE 因子"],
            ["试剂/溶液", "检测抗体浓度", "XX ng/mL", "±20%", "棋盘滴定"],
            ["反应/染色/孵育", "洗涤", "XX 次 × XX µL；洗板器程序 XX", "次数 ±1", "背景与位置效应"],
            ["反应/染色/孵育", "底物显色与终止", "XX min；终止液 XX", "±2 min", "信号动力学"],
            ["仪器/检测", "读数", "XX nm（参考 XX nm）", "—", "读板仪确认"],
            ["数据处理", "校准曲线", "8 点 2–3 倍梯度，双/三孔，4PL，权重 XX", "4PL/5PL", "P1"],
            ["数据处理", "QC 样品", "低/中/高各 ≥ 2 孔", "—", "SST/运行接受标准"],
            ["保存/稳定性", "样品/试剂保存", "−20/−80 ℃ 分装；冻融 ≤ XX 次", "冻融次数", "P9"],
        ],
        "tech.reagents": [
            ["捕获抗体", "包被", "供应商/自制", "关键", "批间亲和力/特异性差异", "数据表；批放行与桥接；预留批次"],
            ["检测抗体（酶标记）", "检测", "供应商/自制", "关键", "标记比/活性批差", "数据表；批放行并排比较"],
            ["标准品 / 参比品", "校准", "官方或内部赋值", "关键", "赋值/稳定性", "赋值方案；分装；稳定性；替换协议"],
            ["QC 样品（低/中/高）", "运行有效性判定", "自制", "关键", "稳定性、批变更", "分装；稳定性；新批并行"],
            ["封闭剂 / 洗涤缓冲液 / 稀释液", "背景控制", "自配/供应商", "重要", "批间差异", "批验收；配制记录"],
            ["底物与终止液", "显色", "供应商", "重要", "批差/稳定性", "批验收；有效期"],
        ],
        "plan.materials": [
            ["捕获抗体", "试剂", "", "", "", "关键", "新批并排比较", "待采购"],
            ["检测抗体（酶标记）", "试剂", "", "", "", "关键", "新批并排比较", "待采购"],
            ["标准品 / 参比品", "参比品/标准品", "", "", "", "关键", "赋值与稳定性监测", "待采购"],
            ["QC 样品（低/中/高）", "对照", "", "", "", "关键", "新批并行", "待采购"],
            ["封闭剂、洗涤缓冲液、稀释液", "溶液/缓冲液", "", "", "", "重要", "配制记录；批验收", "待采购"],
            ["底物、终止液", "试剂", "", "", "", "重要", "批验收", "待采购"],
            ["酶标板、封板膜", "耗材", "", "", "", "一般", "批验收（背景）", "待采购"],
        ],
        "plan.instruments": [
            ["酶标仪 / 读板仪", "—", "吸光/发光读数", "待确认", "IQ/OQ/PQ；波长与线性核对", ""],
            ["洗板机", "—", "洗涤", "待确认", "残留体积与均匀性检查", ""],
            ["恒温孵育器/摇床", "—", "孵育", "待确认", "温度验证", ""],
            ["移液器 / 多通道移液器", "—", "加样", "校准有效", "校准；移液精度检查", ""],
            ["冰箱 / −80 ℃ 冰箱", "—", "试剂与样品储存", "待确认", "温度监测", ""],
        ],
        "plan.software": [
            ["读板仪软件", "（填写）", "原始读数采集", "待验证", "开启"],
            ["曲线拟合软件", "（填写）", "4PL/5PL 拟合与回算", "待验证", "开启"],
            ["统计软件", "（填写）", "方差分量、DoE、稳定性", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["产品样品 / 目标基质（≥ 3 批）", "覆盖低/中/高浓度", "按稳定性条件", "冻融 ≤ XX 次；2–8 ℃ ≤ XX d", "准确度、精密度"],
            ["基质（≥ 6 个来源）", "空白基质", "−20/−80 ℃", "—", "基质效应、选择性"],
            ["加标样品", "基质 + 标准品（低/中/高、LLOQ/ULOQ）", "新鲜配制", "—", "准确度、LLOQ/ULOQ"],
            ["高浓度样品", "高于 ULOQ", "按稳定性条件", "—", "稀释线性、钩状效应"],
            ["降解/应激样品（相对结合活性）", "热/冻融", "按条件", "—", "稳定性指示、平行性"],
        ],
        "risk.ishikawa": [
            ["样品", "基质成分；分析物降解；冻融；聚集", "准确度；选择性", "基质评价；冻融稳定性；MRD"],
            ["试剂与材料", "抗体批差；标准品赋值；QC 稳定性；板批差", "曲线；灵敏度", "批放行与桥接；赋值"],
            ["仪器", "洗板器均匀性；读板仪波长/线性；孵育温度", "位置效应；精密度", "确认；QC 分布"],
            ["方法", "包被/封闭/孵育/洗涤；曲线模型与权重", "背景；精度", "DoE；预先规定模型"],
            ["人员与分析", "加样；稀释；数据剔除规则", "中间精密度", "培训；规则书面化"],
            ["环境与流程", "室温；孵育时间波动；板放置顺序", "孔间变异", "板布局随机化；计时"],
        ],
        "robust.factors": [
            ["A  包被浓度", "−20%", "设定值", "+20%", "P0 选取的中心点"],
            ["B  样品孵育时间", "−15 min", "设定值", "+15 min", "结合平衡"],
            ["C  洗涤次数", "−1 次", "设定值", "+1 次", "背景与信号"],
            ["D  检测抗体浓度", "−20%", "设定值", "+20%", "信号窗口"],
            ["E  底物显色时间", "−2 min", "设定值", "+2 min", "信号动力学"],
            ["F  板类型/批次（类别）", "板 1", "板 2", "板 3", "板间差"],
        ],
        "robust.par": [
            ["样品孵育时间/温度", "设定值", "待 DoE 确定", "实验编号 P8"],
            ["检测抗体浓度", "设定值", "待 DoE 确定", "实验编号 P8"],
            ["洗涤次数", "设定值", "待 DoE 确定", "实验编号 P8"],
        ],
        "robust.stability": [
            ["样品（冻融）", "−20/−80 ℃，冻融 ×1/×3/×5", "每次冻融后", "", ""],
            ["样品（室温/2–8 ℃）", "室温；2–8 ℃", "0–24 h；0–7 d", "", ""],
            ["包被板", "2–8 ℃", "0–4 周", "", ""],
            ["标准品/QC 稀释液", "室温/2–8 ℃", "0–8 h", "", ""],
            ["酶标抗体工作液", "2–8 ℃", "0–1 周", "", ""],
        ],
        "control.references": [
            ["标准品 / 参比品", "校准、效力基准", "赋值（质量/活性）；多批并行", "冻融、储存稳定性", "新批与现行批并行 ≥ 6 次"],
            ["QC 样品（低/中/高）", "运行有效性、趋势", "赋值；分装；多次运行确定接受范围", "稳定性监测", "新批并行 ≥ 6 次"],
            ["阴性/空白基质", "背景", "鉴定", "—", "新批并行"],
        ],
        "control.reagent_mgmt": [
            ["捕获抗体", "克隆、来源、批号、浓度、纯度、储存", "并排比较（曲线参数、QC 回收）", "每批", "更换克隆/供应商需重新验证特异性"],
            ["检测抗体", "标记比、活性、批号", "并排滴定", "每批", "同上"],
            ["标准品", "来源、赋值、批号、稳定性", "与现批比较", "每批", "赋值方式变更需桥接"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据影响对属性的控制"],
            ["技术原理（夹心 ELISA / 竞争 / SPR）", "高", "PA", "原理变更需桥接"],
            ["捕获/检测抗体克隆", "高", "NM", "决定专属性"],
            ["曲线模型与权重", "中", "NM", "影响回算"],
            ["SST/QC 接受标准", "中", "NM", "控制策略证明性能"],
            ["MRD", "中", "NM", "影响基质效应"],
            ["洗涤/孵育微调", "低", "NL", "稳健性显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性/选择性", "≥ 6 个基质来源加标；交叉反应物；降解样品（相对结合活性）", "低/高加标", "ICH Q2(R2) Table 7；ICH M10 §4.2.1–4.2.2（原则借用）" + SAMPLE_TAG],
            ["校准曲线与范围", "≥ 6 次独立运行；回算准确度；LLOQ/ULOQ", "—", "ICH M10 §4.2.3（原则借用）" + SAMPLE_TAG],
            ["准确度与精密度", "QC 低/中/高 + LLOQ/ULOQ，每运行 n=5–6，≥ 6 运行，≥ 2 分析员", "—", "ICH M10 §4.2.4（原则借用）；ICH Q2(R2) Table 7" + SAMPLE_TAG],
            ["稀释线性与钩状效应", "高于 ULOQ 样品系列稀释；最高预期浓度", "—", "ICH M10 §4.2.6（原则借用）" + SAMPLE_TAG],
            ["平行性（相对结合活性）", "参比与样品曲线", "—", "ICH M10 §7.2（原则借用）；USP <1034>（条款待核对）" + SAMPLE_TAG],
            ["稳定性", "冻融、室温、2–8 ℃、长期；包被板与试剂", "—", "ICH M10 §4.2.7（原则借用）" + SAMPLE_TAG],
            ["稳健性（确认）", "孵育、洗涤、板型、试剂批次", "PAR 边界", "ICH Q2(R2) Table 7；ICH Q14 §5.1" + SAMPLE_TAG],
            ["SST/QC 有效性", "故意失败应被拦截", "—", "ICH Q14 §6" + SAMPLE_TAG],
        ],
    },
}

# ---------------------------------------------------------------------- generic
TECHNIQUES["generic"] = {
    "label": "通用分析方法",
    "desc": "未归入以上类型的方法：通用阶段与检查清单，附通用的 FMEA、实验设计（专属性、线性、准确度、精密度、稳健性、稳定性、参比品、SST）与验证矩阵，须按具体技术改写。",
    "changelog": [
        "1.1：通用模板补充 12 条通用 FMEA、12 个通用实验种子（专属性、线性与范围、准确度、重复性、中间精密度、QL、DoE 稳健性、稳定性、参比品、SST 挑战、预验证）、ATP 判据行、SST 与验证矩阵；所有占位值均为示例",
    ],
    "matrix": {"options": ["候选方法 A", "候选方法 B"],
               "criteria": [("满足 ATP 的能力", 5), ("专属性", 4), ("精密度", 4), ("成熟度", 3), ("通量", 2), ("成本", 2)]},
    "atp_rows": [
        ["准确度", "各水平相对偏倚的 90% CI 在 ±X% 内（X 依据规格宽度）", "示例；须按规格宽度与产品风险确认", "ICH Q2(R2) §3.3.1"],
        ["精密度-重复性", "同条件下 n≥6 或 3 水平 × 3，RSD ≤ X%", "示例", "ICH Q2(R2) §3.3.2.1"],
        ["精密度-中间精密度", "不同日期/分析员/仪器：RSD（95% CI 上限）≤ X%", "示例", "ICH Q2(R2) §3.3.2.2"],
        ["联合评价(总误差)", "各水平容忍区间相对误差在 ±X% 内", "示例；联合评价比单项更严格", "ICH Q2(R2) §3.3.3"],
        ["线性/响应", "≥ 5 水平覆盖报告范围；残差无趋势；斜率/截距 95% CI 在判据内", "示例", "ICH Q2(R2) §3.2.2"],
        ["专属性", "空白/基质/相关物质不干扰；必要时强降解证明稳定性指示", "示例", "ICH Q2(R2) §3.1；§2.4"],
        ["定量下限", "满足准确度与精密度的最低水平；≤ 报告限", "示例", "ICH Q2(R2) §3.2.3"],
        ["稳健性/稳定性", "关键参数合理变动下结果变化 ≤ X%；样品/试剂稳定性时限已确定", "示例", "ICH Q14 §5.1"],
    ],
    "extra_checklist": {
        "atp": [ck("gx1", "已确认通用模板是否适用，或应改用更具体的技术模板（flow/hplc/bioassay/qpcr/elisa/cell_based）", "通用模板的示例判据需要全部改写。", "", False)],
        "tech": [ck("gx2", "方法原理与关键假设已用文字描述", "", "ICH Q14 §6.1")],
        "plan": [ck("gx3", "各验证性能特性的开发预试验已在方案中登记", "", "ICH Q2(R2) §3")],
        "control": [ck("gx4", "SST 项目对应 FMEA 高风险项", "", "ICH Q14 §6")],
    },
    "fmea": [
        F("样品代表性或制备变异", "取样/前处理", "准确度与精密度变差", 7, 4, 4, "取样与制备 SOP；样品适用性；制备稳定性研究"),
        F("试剂/材料批间差异", "供应商批次", "系统性偏倚", 7, 5, 4, "关键试剂数据表；批放行与桥接"),
        F("参比品或对照品变质、赋值错误", "储存/赋值", "偏倚", 8, 3, 4, "参比品鉴定与稳定性；替换协议"),
        F("仪器漂移或性能下降", "老化/环境", "灵敏度变化", 6, 3, 4, "日常质控；预防性维护；SST"),
        F("操作者差异", "手法/理解", "精密度变差", 5, 5, 4, "培训与资格；SOP 图示；分析员因子纳入验证"),
        F("数据处理或计算错误", "模板/手工转录", "错误结果", 7, 3, 5, "受控模板与验证；独立复核"),
        F("样品/溶液稳定性不足", "降解/吸附", "结果偏低或变异", 7, 4, 5, "稳定性研究；规定最长保存时间"),
        F("专属性不足/干扰", "基质或相关物质", "假阳性/偏倚", 8, 3, 4, "专属性实验；强降解；正交方法"),
        F("环境条件影响", "温湿度/光照", "变异", 5, 4, 3, "环境监控；PAR"),
        F("判据设置不当（过松或过严）", "缺乏数据依据", "漏检或频繁无效运行", 7, 3, 4, "判据来自 ATP 与开发数据；预先书面化"),
        F("方法转移后性能不一致", "站点/仪器差异", "结果不可比", 7, 4, 4, "仪器协调；转移方案；等效性检验"),
        F("审计追踪/数据完整性缺口", "系统配置", "记录不可信", 8, 3, 4, "审计追踪开启并定期审核；权限管理"),
    ],
    "experiments": [
        X("P0", "可行性与方法雏形", "确认方法能区分阴性与阳性/空白与标准",
          "空白、标准/参比、代表性样品各 n=3；初始条件见第 7 章",
          S_("信号/分离满足可行性判据（如信噪比 ≥ X）；背景 ≤ X。"), "explore", 2),
        X("P1", "专属性/选择性", "证明方法对目标属性特异",
          "空白、基质、相关物质/干扰物、降解样品（必要时）；n=3",
          S_("无显著干扰（≤ X%）；降解样品中可检出变化（稳定性指示）。"), "explore", 2),
        X("P2", "线性、响应与范围", "确定响应模型与报告范围",
          "≥ 5 水平覆盖报告范围，每水平 ≥ 3 次独立制备",
          S_("残差无趋势；斜率/截距 95% CI 在判据内；范围两端满足准确度/精密度。"), "explore", 1),
        X("P3", "条件优化", "优化关键参数并固定初始条件",
          "单因素或小型 DoE；响应：灵敏度、精密度、背景",
          S_("优化后的条件使全部响应满足 P0–P2 判据。"), "explore", 2),
        X("P4", "准确度预试验", "初步评价准确度",
          "≥ 3 水平 × 3 独立制备（参比品比较或加标）；必要时与正交方法比较",
          S_("相对偏倚 90% CI 在 ±X% 内。"), "robust", 1),
        X("P5", "重复性", "估计重复性",
          "n≥6 同条件或 3 水平 × 3",
          S_("RSD ≤ X%。"), "robust", 1),
        X("P6", "中间精密度", "估计中间精密度与方差分量",
          "≥ 2 分析员 × ≥ 3 天 × （≥ 2 仪器/试剂批）；ANOVA 方差分量",
          S_("中间精密度 RSD 95% CI 上限 ≤ X%。"), "robust", 2),
        X("P7", "定量下限", "确定 QL",
          "低水平 n=6–10；准确度与精密度",
          S_("QL 水平回收与 RSD 满足判据，且 ≤ 报告限。"), "robust", 1),
        X("P8", "DoE 稳健性", "确定关键参数及 PAR",
          "按 FMEA 选 4–6 个因子；部分因子 + 中心点；随机化",
          S_("关键参数确定；PAR 内结果变化 ≤ X%。"), "robust", 3),
        X("P9", "稳定性", "确定样品/溶液/试剂保存时限",
          "样品与处理后溶液：室温/2–8 ℃，多个时间点；试剂工作液；n=3",
          S_("相对 0 h 变化 ≤ X%；时限留有余量。"), "robust", 2),
        X("P10", "参比品/对照建立", "建立内部参比品/对照并定值",
          "≥ 6 次独立运行赋值；稳定性监测方案；替换协议",
          S_("均值与 SD 已确定；稳定性在判据内。"), "control", 3),
        X("P11", "SST 判据与挑战", "由开发数据定 SST，并检验其拦截能力",
          "故意制造：试剂减量、参比降解、条件偏离；各 3 次",
          S_("SST 能拦截全部故意失败。"), "control", 1),
        X("P12", "预验证演练", "两名分析员按 SOP 草案运行",
          "各 3 次独立运行；评估 SOP 清晰度与周转",
          S_("SOP 可执行；SST 拦截故意失败；偏差闭合。"), "report", 1),
    ],
    "sst": [
        ["空白/阴性对照", "≤ 判据（如 < QL）", "背景/污染", "调查；重做"],
        ["参比品/对照结果", "在控制限内", "系统性能", "运行无效"],
        ["系统精密度（重复测量）", "RSD ≤ 判据", "精密度", "排查"],
        ["灵敏度检查（低水平）", "满足判据", "灵敏度", "调查"],
    ],
    "ph": {},
    "seeds": {
        "tech.conditions": [
            ["样品", "样品类型与前处理", "XX", "XX", "初始条件来源：XX"],
            ["试剂/溶液", "关键试剂浓度", "XX", "±20%", "文献/平台"],
            ["反应/染色/孵育", "反应条件（时间/温度）", "XX", "±", "预实验"],
            ["仪器/检测", "仪器设置与检测参数", "XX", "XX", "仪器手册/平台"],
            ["数据处理", "数据处理与拟合规则", "XX", "—", "预先规定"],
            ["保存/稳定性", "样品/试剂保存", "XX", "XX", "稳定性研究"],
        ],
        "tech.reagents": [
            ["关键试剂 1", "XX", "XX", "关键", "批间差异", "数据表；批放行"],
            ["参比品/标准品", "校准/基准", "XX", "关键", "变质/赋值", "鉴定；稳定性；替换协议"],
            ["对照（阴/阳性）", "运行有效性", "XX", "重要", "稳定性", "分装；趋势"],
        ],
        "plan.materials": [
            ["关键试剂 1", "试剂", "", "", "", "关键", "批放行", "待采购"],
            ["参比品/标准品", "参比品/标准品", "", "", "", "关键", "稳定性监测", "待采购"],
            ["对照（阴/阳性）", "对照", "", "", "", "重要", "批放行", "待采购"],
            ["耗材", "耗材", "", "", "", "一般", "—", "待采购"],
        ],
        "plan.instruments": [
            ["主要分析仪器", "XX", "XX", "待确认", "IQ/OQ/PQ；校准计划", ""],
            ["辅助设备", "XX", "XX", "待确认", "按设备计划", ""],
        ],
        "plan.software": [
            ["采集与分析软件", "（填写）", "数据采集与处理", "待验证", "开启"],
            ["统计软件", "（填写）", "统计分析", "待验证", "不适用"],
            ["MethodFlow（本程序）", "（填写）", "方案、实验、复核记录与文档生成", "待验证", "开启"],
        ],
        "atp.samples": [
            ["代表性样品（≥ 3 批）", "覆盖报告范围的低/中/高", "XX", "XX", "准确度、精密度"],
            ["空白/基质", "XX", "XX", "—", "专属性"],
            ["加标/降解样品", "XX", "XX", "—", "专属性、稳定性指示"],
        ],
        "risk.ishikawa": [
            ["样品", "代表性；制备；稳定性", "准确度；精密度", "取样与制备 SOP"],
            ["试剂与材料", "批间差；参比品", "偏倚", "批放行；参比品管理"],
            ["仪器", "漂移；校准", "灵敏度", "日常质控"],
            ["方法", "关键参数；判据", "精密度；稳健性", "DoE；SST"],
            ["人员与分析", "操作差异；计算", "精密度；错误结果", "培训；复核"],
            ["环境与流程", "温湿度；保存时间", "稳定性", "环境监控；时限"],
        ],
        "robust.factors": [
            ["A  关键参数 1", "−X%", "设定值", "+X%", "来自 FMEA 高风险项"],
            ["B  关键参数 2", "−X%", "设定值", "+X%", "同上"],
            ["C  试剂批次（类别）", "批 1", "批 2", "批 3", "批间差"],
            ["D  分析员（类别）", "分析员 1", "分析员 2", "—", "操作差异"],
        ],
        "robust.par": [["关键参数 1", "设定值", "待 DoE 确定", "实验编号 P8"]],
        "robust.stability": [
            ["样品", "室温 / 2–8 ℃", "0–24 h（示例）", "", ""],
            ["处理后溶液", "按条件", "0–48 h（示例）", "", ""],
            ["试剂工作液", "按条件", "0–4 周（示例）", "", ""],
        ],
        "control.references": [
            ["内部参比品/对照", "基准、SST", "≥ 6 次独立运行赋值", "稳定性监测", "新批并行比较"],
        ],
        "control.reagent_mgmt": [
            ["关键试剂 1", "来源、批号、规格、储存", "批放行（并排比较）", "每批", "更换供应商需桥接"],
        ],
        "control.ecs": [
            ["ATP 的性能特性与判据", "高", "PA", "放宽判据影响对质量属性的控制"],
            ["技术原理", "高", "PA", "原理变更需桥接"],
            ["SST 判据", "中", "NM", "控制策略证明性能"],
            ["关键参数设定点与 PAR", "中", "NM", "DoE 证明；PAR 内不通知"],
            ["次要参数", "低", "NL", "稳健性显示影响小"],
        ],
        "report.validation_matrix": [
            ["专属性", "空白、基质、相关物质、降解样品", "—", "ICH Q2(R2) §3.1" + SAMPLE_TAG],
            ["响应与范围", "≥ 5 水平，每水平 ≥ 3 重复", "覆盖报告范围", "ICH Q2(R2) §3.2" + SAMPLE_TAG],
            ["准确度", "≥ 3 水平 × 3 独立制备", "—", "ICH Q2(R2) §3.3.1" + SAMPLE_TAG],
            ["精密度", "重复性 + 中间精密度", "—", "ICH Q2(R2) §3.3.2" + SAMPLE_TAG],
            ["联合评价", "准确度谱/容忍区间", "—", "ICH Q2(R2) §3.3.3" + SAMPLE_TAG],
            ["稳健性（确认）", "PAR 边界", "—", "ICH Q14 §5.1；ICH Q2(R2) §3.4" + SAMPLE_TAG],
            ["稳定性", "样品/溶液/试剂时限确认", "—", "ICH Q14 §5.1" + SAMPLE_TAG],
        ],
    },
}


# ====================================================================== public API
TECHNIQUE_ORDER = ["flow", "hplc", "bioassay", "qpcr", "elisa", "cell_based", "generic"]


def _rows(cols, rows, where=""):
    """list-of-lists -> list-of-dicts keyed by column key."""
    keys = [c["key"] for c in cols]
    out = []
    for r in rows:
        if len(r) != len(keys):
            raise ValueError("seed row width %d != %d columns in %s: %r" % (len(r), len(keys), where, r[:2]))
        out.append(dict(zip(keys, r)))
    return out


def list_templates():
    out = []
    for k in TECHNIQUE_ORDER:
        t = TECHNIQUES[k]
        out.append({"key": k, "label": t["label"], "desc": t["desc"], "version": TEMPLATE_VERSION,
                    "changelog": _changelog(t),
                    "stats": {"fmea": len(t["fmea"]), "experiments": len(t["experiments"]), "sst": len(t["sst"]),
                              "atp_rows": len(t["atp_rows"])}})
    return out


def _changelog(tech):
    return [{"version": TEMPLATE_VERSION, "date": CHANGELOG[0]["date"], "scope": "通用", "changes": list(CHANGELOG[0]["changes"])},
            {"version": TEMPLATE_VERSION, "date": CHANGELOG[0]["date"], "scope": tech["label"], "changes": list(tech.get("changelog", []))},
            {"version": CHANGELOG[1]["version"], "date": CHANGELOG[1]["date"], "scope": "通用", "changes": list(CHANGELOG[1]["changes"])}]


def build_template(key):
    """Full template dict for a technique key (deep copy, safe to mutate)."""
    if key not in TECHNIQUES:
        raise KeyError(key)
    tech = TECHNIQUES[key]
    seeds = tech.get("seeds", {})
    ph = tech.get("ph", {})
    stages = common_stages()
    atp_rows = tech["atp_rows"]
    for st in stages:
        extra = tech.get("extra_checklist", {}).get(st["key"], [])
        st["checklist"] = st["checklist"] + copy.deepcopy(extra)
        for sec in st["sections"]:
            fq = st["key"] + "." + sec["key"]
            if sec["type"] == "text":
                if fq in ph:
                    sec["placeholder"] = ph[fq]
            elif sec["type"] == "table":
                base = COMMON_SEEDS.get(fq, [])
                if fq in seeds:
                    rows = (base + seeds[fq]) if fq in APPEND_SEEDS else seeds[fq]
                else:
                    rows = base
                if fq == "report.vs_atp":
                    rows = [[r[0], r[1], "", "", "待验证"] for r in atp_rows]
                if rows:
                    sec["seed_rows"] = _rows(sec["columns"], rows, key + ":" + fq)
        st["sections"] = copy.deepcopy(st["sections"])
    return {"key": key, "label": tech["label"], "version": TEMPLATE_VERSION, "stages": stages,
            "changelog": _changelog(tech), "doc_structure": doc_structure(),
            "seed": {"matrix": copy.deepcopy(tech["matrix"]), "atp_rows": copy.deepcopy(atp_rows), "fmea": copy.deepcopy(tech["fmea"]),
                     "experiments": copy.deepcopy(tech["experiments"]), "sst": copy.deepcopy(tech["sst"])}}
