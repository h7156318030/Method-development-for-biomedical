/* MethodFlow 新手指引模块（guide.js）
 * 提供：
 *   MF.guide.stagePanel(stageKey, opts)   阶段页顶部的“这一步怎么做”面板
 *   MF.guide.nextStepCard(method)         方法总览顶部的“下一步该做什么”卡片
 *   路由 /guide                            方法开发指南（流程图、新手 12 步、角色、规则、术语、FAQ）
 * 依赖 core.js 的 MF.h / MF.api / MF.route / MF.setCrumbs。内容均为静态中文文本，经 MF.h 以文本节点写入（不使用 innerHTML）。 */
(function () {
  'use strict';
  var MF = window.MF;
  var h = MF.h;

  /* ------------------------------------------------------------------ 内容 */
  var ORDER = ['charter', 'atp', 'tech', 'risk', 'plan', 'explore', 'robust', 'control', 'report'];

  var STAGES = {
    charter: {
      n: 1, name: '立项与背景', time: '约 1 周', who: '开发人员起草，无评审门（填完提交即完成）',
      goal: '把“为什么做、做到什么算完成、谁负责”写清楚，并建立文件的基础信息。',
      why: '没有可衡量的“完成标准”，开发会无限延长；没有职责和参考文件，后面的复核和审计都站不住。',
      steps: [
        '写“目的与成功标准”：一句话说清——用什么方法、测什么、用于什么、达到什么指标算开发完成。',
        '写“适用范围与不在范围”：例如只做 CAR 表达率，不含效力和拷贝数。不在范围的内容同样要写。',
        '选“监管阶段与区域”：早期临床、确证性、BLA 的要求强度不同，它决定后面验证做多深。',
        '填“职责分配（RACI）”：谁起草、谁复核、谁批准；复核人/批准人不得是本阶段内容的编辑者。',
        '核对“缩略语与术语”“参考文件”：系统已预置常用项，删掉用不到的，补上公司 SOP 编号。',
        '写“背景”和“已有方法与先验知识”：有没有平台方法、旧方法、文献、内部教训，可直接复用什么。',
        '写“研发目标（可度量）”：例如单次运行 ≤1 个工作日、开发周期 ≤26 周、可在第二实验室执行。',
        '勾选检查清单，保存，提交（无评审门的阶段提交后直接“已完成”）。'
      ],
      outputs: '方案文档第 1–5 章（目的与范围、职责、术语、参考文件、背景与目标）。',
      pitfalls: ['目的写成“开发一个方法”，没有任何成功标准。', '没写“不在范围”，后面范围不断膨胀。', '监管阶段没选，导致验证强度无依据。'],
      done: '必填章节与必做检查项都已完成。'
    },
    atp: {
      n: 2, name: '分析目标概况（ATP）', time: '约 2 周', who: '开发人员填写 → 复核人签署（评审门 G1）',
      goal: '先定义“这个方法最终要达到什么性能”，再去选技术。ATP 是后面开发和验证的唯一依据。',
      why: '监管指南（ICH Q14）要求先有分析目标再选技术。判据不事先定好，实验做完只能“看结果说话”，审评无法接受。',
      steps: [
        '写“预期用途”：用于放行、稳定性还是过程控制？测什么样品？在哪些场所执行？',
        '写“被测属性与规格”：属性是什么，规格或预期规格是多少，它为什么影响安全性或有效性。',
        '填“可报告结果与范围”：可报告结果取几次重复的均值？报告范围多宽？范围要从规格推导并写依据（如规格 ±20%）。',
        '填“性能特性与判据”表：准确度、精密度、专属性、定量下限、线性等，每条判据都要写成数值区间并说明依据；不要只写“RSD ≤ x%”。系统预置了示例行，请按自己的产品修改。',
        '写“专属性与干扰”：可能的干扰物、阴性/阳性对照、是否要求稳定性指示能力。',
        '写“样品类型与基质”“取样、前处理、保存与稳定性要求”。',
        '勾选检查清单（含“ATP 不预设具体技术”），保存，提交复核（G1）。'
      ],
      outputs: '方案文档第 6、9 章（ATP、样品与基质）。后面的验证接受标准直接来自这里。',
      pitfalls: ['先选好技术再倒推写 ATP。', '判据没有依据，只是“拍脑袋”的数字。', '报告范围与规格对不上（范围比规格窄，或下限无法定量）。', '示例值没有替换就提交（系统会提示“示例值，须按 ATP 确认”）。'],
      done: '复核人签署通过。'
    },
    tech: {
      n: 3, name: '技术选择与试剂策略', time: '约 2 周', who: '开发人员填写 → 复核人签署（评审门 G2）',
      goal: '用评分矩阵比较候选技术，把“为什么选它、为什么不选其他”留痕，并确定初始方法条件和关键试剂。',
      why: '技术选择是可被审评质询的决定；评分矩阵加文字理由，才能证明不是凭习惯选的。',
      steps: [
        '在“技术选择评分矩阵”里至少比较 2 种候选技术（选项可增删改名）。',
        '按 ATP 设定评价标准和权重（灵敏度、专属性、通量、成本、可转移性、平台成熟度等）。',
        '给每个选项逐项打 1–5 分，系统自动计算加权总分；总分只是起点，不是结论。',
        '写“选择结论与理由”：为什么选它、为什么不选其他、已知局限。',
        '写“方法原理描述”和“初始方法条件与参数”（系统按技术预置了典型参数，请改成你的）。',
        '填“关键试剂与参比品策略”：来源、替代方案、批号管理、风险与控制。',
        '写“与既有方法/平台的关系”，勾选检查清单，保存，提交复核（G2）。'
      ],
      outputs: '方案文档第 7、8.1 章（技术选择、原理、初始条件、关键试剂）。',
      pitfalls: ['只列一种“候选”，矩阵形同虚设。', '只有分数没有文字理由。', '关键试剂只有一个来源也没有备选方案。'],
      done: '复核人签署通过。'
    },
    risk: {
      n: 4, name: '风险评估（FMEA）', time: '约 1 周', who: '开发人员填写，无评审门（完成即可；GP 门会一并复核）',
      goal: '在做实验之前，先找出最可能毁掉结果的因素，并决定怎么控制。',
      why: '风险评估决定“哪里要重点做实验”。事后补 FMEA 没有意义，审评一眼就能看出来。',
      steps: [
        '用石川图要点按类别列因素：样品、试剂、仪器、方法、人员与分析、环境与流程。',
        '先看“S/O/D 评分标准”，确认 1–10 分分别代表什么，团队统一口径。',
        '在 FMEA 表逐行填：失效模式 → 原因 → 影响 → 严重度 S、发生度 O、可检出度 D（均为 1–10 的整数）→ 控制措施。',
        '系统自动算 RPN = S×O×D。RPN ≥ 120 或 S ≥ 8 的行必须写控制措施，否则不能提交。',
        '在“风险–实验映射”写清每个高风险项由哪个实验或哪项控制来验证。',
        '“风险再评估（开发后）”留到开发结束后回写，勾选检查清单，保存，提交（完成）。'
      ],
      outputs: '方案文档第 10 章（风险评估）；风险–实验映射会指导第 5 步的实验设计。',
      pitfalls: ['全部打 5 分，看不出优先级。', '高风险没有控制措施。', '风险没有映射到任何实验，等于白做。'],
      done: '必填内容与检查项完成；高风险项均已有控制措施。'
    },
    plan: {
      n: 5, name: '开发方案与实验设计', time: '约 2 周', who: '开发人员填写 → 复核人 → 批准人（QA）两级签署（评审门 GP，覆盖前 4 个阶段）',
      goal: '把前面的决定变成可执行的方案：分阶段实验、判据、统计方法、材料仪器、数据完整性、偏离程序和时间计划。方案批准后才能开始做实验。',
      why: '“先定判据再做实验”是数据可信的前提。方案批准的那一刻，实验设计和接受标准被冻结，之后改动要走偏离。',
      steps: [
        '写“开发总体策略”和“开发阶段计划”表：每个阶段的目的、设计、接受标准、周数。',
        '去“实验”页登记每个实验（系统已按技术预置了一批，可增删改）：每个实验必须有“设计”和“接受标准”。',
        '写“统计分析计划”“样本量与重复数依据”“决策规则与判据变更原则”。',
        '填“材料、试剂、参比品与耗材清单”“仪器与设备”“软件与计算机化系统”。',
        '写“数据处理、原始数据保存与计算规则”和“数据完整性（ALCOA+）落实措施”。',
        '写“偏离处理程序”“变更与偏离分类”，填“里程碑”和时间计划说明。',
        '检查所有“示例值，须按 ATP 确认”都已替换。看右侧“提交条件检查”，全部通过后提交，等待复核人、再由批准人（QA）依次签署。'
      ],
      outputs: '方案文档第 8.2–8.3、11–15 章。此后可以生成《方法开发方案》Word/PDF 用于审批。',
      pitfalls: ['判据留到“实验做完再定”。', '实验没有设计或接受标准（系统会拦截提交）。', '批准后又想改实验设计：会被冻结，需先重新打开本阶段并留下原因。', '提交前没替换模板里的示例数值。'],
      done: '复核人和批准人都已签署，方案阶段变为“已通过”；前 4 个阶段同时锁定。'
    },
    explore: {
      n: 6, name: '可行性与优化实验', time: '约 4 周', who: '开发人员执行 → 复核人签署（评审门 G3）',
      goal: '按已批准的方案做可行性、条件筛选、专属性初筛和优化实验，每个实验都有记录、结果和结论。',
      why: '实验记录是整个开发的证据。结论要对照事先定好的接受标准，而不是事后解释。',
      steps: [
        '到“实验”页，按计划逐个把实验从“计划中”点为“进行中”（方案批准后才允许）。',
        '做完后在实验详情填“结果”表（指标、实测值、判据、符合性），并把原始数据上传为附件。',
        '写“结论”：对照接受标准，达标还是不达标，决定是什么。没有结论的实验不能标为“已完成”。',
        '出现任何与方案不一致的情况，写在“偏离/说明”。不做的实验要点“取消”并写原因。',
        '全部实验完成或取消后，在本阶段写“阶段小结”“本阶段形成的决定”“问题与偏离”。',
        '勾选检查清单，保存，提交复核（G3）。'
      ],
      outputs: '报告文档第 12–13 章（实验清单与结果汇总）。',
      pitfalls: ['先做实验后补设计。', '只记录好结果，坏结果不写。', '原始数据没有上传，只留了结论。', '实验还在“计划中/进行中”就提交（会被拦截）。'],
      done: '本阶段全部实验已完成或取消且有结论；复核人签署通过。'
    },
    robust: {
      n: 7, name: '稳健性、稳定性与参数范围（DoE）', time: '约 3 周', who: '开发人员填写，无评审门（G4 会一并复核）',
      goal: '用实验设计（DoE）找出关键参数，划定可接受的参数范围，并研究各类稳定性，定出最长保存时间。',
      why: '常规使用中参数一定会有波动；稳健性和稳定性数据决定方法在第二实验室、第二台仪器上还能不能用。',
      steps: [
        '在“DoE 因子与水平”里选因子：优先选风险评估里高风险的参数，并写水平范围。',
        '做 DoE 实验（在“实验”页登记和记录），在“DoE 设计与分析结论”写分析结果。',
        '据此写“参数范围（PAR/设定点）”：设定点是多少，允许在什么范围内变动。',
        '写“稳定性研究”：样品、处理后样品、试剂、参比品各自的最长保存时间及依据。',
        '把稳健性结论回写到风险评估（“稳健性结论对风险评估的回写”），保存，提交（完成）。'
      ],
      outputs: '报告文档第 14 章（稳健性、稳定性与参数范围）。',
      pitfalls: ['因子凭感觉选，与风险评估脱节。', '只给设定点，不给允许范围。', '没有定最长保存时间，常规使用时无法执行。'],
      done: '本阶段实验全部完成且有结论；必填内容完成。'
    },
    control: {
      n: 8, name: '参比品与控制策略', time: '约 3 周', who: '开发人员填写 → 复核人 → 批准人（QA）两级签署（评审门 G4，覆盖稳健性阶段）',
      goal: '定义常规使用时怎样保证方法每次都可靠：系统适用性（SST）、样品适用性、参比品与对照、关键试剂管理、已确立条件、持续监控。',
      why: '控制策略要在验证之前定好，验证才有明确的对象和接受标准。',
      steps: [
        '填“系统适用性（SST）”表：检查项、判据、风险、不符合时的处理（系统预置了示例）。',
        '写“样品适用性”：什么样的样品不能报告结果（如活率过低、事件数不足）。',
        '写“参比品与对照”：阳性/阴性对照、参比品来源与再确认计划。',
        '写“关键试剂管理”：批次接受、桥接、效期与再确认。',
        '写“已确立条件（EC）与建议报告类别”，写“持续监控方案”。',
        '勾选检查清单，保存，提交；复核人和批准人依次签署。'
      ],
      outputs: '报告文档第 15 章（参比品与控制策略）。',
      pitfalls: ['SST 判据照抄示例，没有依据。', '没有规定关键试剂换批后的桥接。', '控制策略到验证时才想起来补。'],
      done: '复核人和批准人签署通过；稳健性阶段同时锁定。'
    },
    report: {
      n: 9, name: '预验证与开发报告', time: '约 2 周', who: '开发人员填写 → 复核人 → 批准人（QA）两级签署（评审门 G5，覆盖探索、稳健性、控制策略）',
      goal: '总结开发：对照 ATP 逐项评价是否达成，形成 SOP 草案，列出偏离、遗留问题和验证策略。',
      why: '这一份报告是转入方法验证的“交接文件”，也是审评检查时最先被调阅的文件。',
      steps: [
        '写“开发结论摘要”和“结论性意见”：方法是否满足 ATP，可以进入验证吗。',
        '写“对照 ATP 的达成情况”：每条判据一行，写实测结果和是否达成。',
        '依次写 SOP 草案 1–11：原理、试剂、仪器、设置、样品制备、标准制备、操作步骤、结果计算、可报告结果、SST、注意事项（可照步骤直接转成 SOP）。',
        '填“开发中使用的关键材料批号”“数据完整性评价”“偏离清单”“偏差与遗留问题说明”“遗留问题与后续行动”。',
        '写“验证策略”：验证做哪些项、用什么设计、接受标准如何从 ATP 来。',
        '勾选检查清单，保存，提交；复核人和批准人依次签署，然后生成《方法开发报告》。'
      ],
      outputs: '报告文档第 1、16–21 章。完成后可生成《方法开发报告》Word/PDF 用于审批。',
      pitfalls: ['只写“方法可用”，没有逐项对照 ATP。', 'SOP 草案缺少注意事项和判定规则。', '遗留问题没有负责人和时间。'],
      done: '复核人和批准人签署通过，方法开发完成。'
    }
  };

  var STEPS12 = [
    ['先把团队建好', '在“项目”里建项目、拉入成员；项目负责人再创建“方法”并指定方法团队：至少 1 名复核人和 1 名批准人（QA），他们不能是内容的编辑者。'],
    ['从最接近的模板建方法', '选和你的技术最接近的模板（流式、HPLC、生物活性、qPCR、ELISA、细胞法或通用）。模板里已预置检查清单、风险项、实验和示例判据。'],
    ['立项与背景', '写清目的和“做到什么算完成”。'],
    ['先写 ATP 再选技术', '定义性能要求和判据，并写依据。提交给复核人。'],
    ['技术选择', '评分矩阵加文字理由，定初始条件和关键试剂。提交给复核人。'],
    ['做风险评估', '石川图加 FMEA，高风险项必须有控制措施，并映射到实验。'],
    ['写开发方案，提交 GP 审批', '登记实验及其设计和接受标准；先复核人、后批准人签署。批准后就可以生成《方法开发方案》Word/PDF。'],
    ['做可行性与优化实验', '在“实验”页按计划执行并记录结果、附原始数据、写结论。'],
    ['做稳健性和稳定性（DoE）', '定参数范围和最长保存时间。'],
    ['定控制策略', 'SST、参比品、关键试剂管理、持续监控；提交 G4 审批。'],
    ['写开发报告，提交 G5 审批', '对照 ATP 逐项评价，写 SOP 草案、遗留问题和验证策略。'],
    ['生成文件、归档，转入验证', '生成《方法开发报告》Word/PDF 归档；在方法页“变更生命周期”改为验证阶段。']
  ];

  var RULES = [
    ['先定判据，后做实验', '接受标准在方案批准前写进方案；批准后实验的设计、判据被冻结，要改必须先重新打开方案阶段并留下原因。'],
    ['每一步都要有记录和依据', '结论要对照事先定的接受标准；原始数据作为附件上传，系统会记录文件指纹（SHA-256）。'],
    ['谁写的不能自己批', '同一阶段的编辑者、提交人、实验记录人永远不能成为该阶段的复核人或批准人；复核人与批准人也不能是同一个人。'],
    ['签字就是电子签名', '签署时要重新输入密码，签名绑定到当时的修订号和内容指纹；内容之后被改动，签名会显示“完整性校验失败”。'],
    ['批准后锁定', '已批准的阶段不能直接改。需要改时由方法负责人或批准人“重新打开”（填原因并输入密码），后续依赖它的阶段会被标为“已失效”，需重新确认。'],
    ['被退回不是失败', '复核人退回要写原因，作者修改后再次提交即可，修订号加 1，历史都保留。']
  ];

  var GLOSSARY = [
    ['ATP', '分析目标概况：方法要测什么、用于什么、必须达到什么性能。'],
    ['CQA', '关键质量属性：影响产品安全性/有效性的属性，方法要能测它。'],
    ['FMEA / RPN', '失效模式与影响分析；RPN = 严重度 S × 发生度 O × 可检出度 D，用来排风险优先级。'],
    ['DoE', '实验设计：同时改变多个因素，用较少实验找出关键参数和交互作用。'],
    ['PAR / MODR', '可接受参数范围 / 方法可操作设计空间：参数在其中变动，结果仍满足 ATP。'],
    ['EC', '已确立条件：需要在注册文件中固定、变更须报告的关键方法条件。'],
    ['SST', '系统适用性试验：每次运行时证明方法此刻状态正常的检查。'],
    ['FMO', '荧光减一对照：流式中用来设门和判断串色的对照。'],
    ['LLOQ', '定量下限：能可靠定量的最低水平。'],
    ['TOST', '等效性检验：证明差异落在可接受范围内（常用于准确度、方法比较）。'],
    ['ALCOA+', '数据完整性原则：可归属、清晰、同步、原始、准确，及完整、一致、持久、可用。'],
    ['评审门（G1…G5、GP）', '需要别人复核/批准后才能往下走的节点。']
  ];

  var FAQ = [
    ['为什么“提交”按钮点不了或提交失败？', '看阶段页右侧“提交条件检查”：红色条目是必须解决的，黄色是建议。常见原因：必填章节未填、检查项未完成、前置阶段未通过、FMEA 高风险项缺控制措施、实验未完成或缺结论、没有可用的复核人/批准人。'],
    ['为什么实验“开始”不了？', '开发方案阶段（GP）必须先批准，批准后才能开始做实验。'],
    ['提交后发现写错了怎么办？', '还没人签署时，编辑者可以“撤回”修改再提交；已签署通过后，需要方法负责人或批准人“重新打开”（写原因并输入密码）。'],
    ['看到“已失效”是什么意思？', '它依赖的前置阶段被重新打开过，已有的签署不再有效。核对内容没问题后点“重新确认”，再次提交复核。'],
    ['“示例值，须按 ATP 确认”是什么？', '模板里预置的数字只是示例，不是结论。提交前必须替换成你们产品的真实判据；文档里未替换的示例值会被高亮提示。'],
    ['谁能当复核人、批准人？', '系统管理员给用户赋予“复核人”“批准人”角色后，才能在方法团队里被指定；他们不能是同一阶段的编辑者。'],
    ['怎样得到可以送审的文件？', '在方法页“文档”标签生成《方法开发方案》（完成到 GP 阶段）或《方法开发报告》（全部阶段）。全部已批准才是“已批准版本”，否则是“草稿”，不可作为批准文件。']
  ];

  /* ------------------------------------------------------------------ 小工具 */
  function list(items, cls) { return h('ul', { class: cls || '' }, items.map(function (t) { return h('li', null, t); })); }
  function olist(items) { return h('ol', null, items.map(function (t) { return h('li', null, t); })); }
  function store(k, v) { try { if (v === undefined) return window.localStorage.getItem(k); window.localStorage.setItem(k, v); } catch (e) { /* 忽略 */ } return null; }
  var GSTYLE = '.gd-card{border-left:4px solid var(--c-primary,#1d5fb8)}.gd-flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:10px 0}' +
    '.gd-node{flex:1 1 150px;min-width:140px;border:1px solid var(--c-border,#d0d7de);border-radius:8px;padding:8px 10px;background:var(--c-card,#fff);text-decoration:none;color:inherit}' +
    '.gd-node:hover{border-color:var(--c-primary,#1d5fb8)}.gd-node .n{font-size:12px;color:var(--c-muted,#667)}.gd-node .t{font-weight:600}' +
    '.gd-gate{display:inline-block;font-size:11px;border:1px solid var(--c-warn,#b7791f);color:var(--c-warn,#b7791f);border-radius:10px;padding:0 6px;margin-left:4px}' +
    '.gd-cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:760px){.gd-cols{grid-template-columns:1fr}}' +
    '.gd-sec h4{margin:10px 0 4px}.gd-sec ul,.gd-sec ol{margin:4px 0 4px 20px;padding:0}.gd-sec li{margin:3px 0;line-height:1.55}' +
    '.gd-next{border:2px solid var(--c-primary,#1d5fb8);border-radius:10px;padding:12px 14px;margin-bottom:14px;background:var(--c-card,#fff)}' +
    '.gd-next h3{margin:0 0 6px}.gd-bad li{color:var(--c-err,#c0392b)}.gd-faq summary{cursor:pointer;font-weight:600;margin:6px 0}';
  function injectCss() {
    if (document.getElementById('mf-guide-css')) return;
    var s = document.createElement('style'); s.id = 'mf-guide-css'; s.textContent = GSTYLE; document.head.appendChild(s);
  }

  /* ------------------------------------------------------------------ 阶段指引面板 */
  function stagePanel(stageKey) {
    injectCss();
    var g = STAGES[stageKey];
    if (!g) return h('div');
    var storeKey = 'mf_guide_open_' + stageKey;
    var det = h('details', { class: 'card gd-card gd-sec' });
    var saved = store(storeKey);
    det.open = saved === null ? true : saved === '1';
    det.addEventListener('toggle', function () { store(storeKey, det.open ? '1' : '0'); });
    det.appendChild(h('summary', { style: { cursor: 'pointer', fontWeight: '600' } }, '新手指引：第 ' + g.n + ' 步「' + g.name + '」怎么做（点击展开/收起）'));
    det.appendChild(h('p', null, h('strong', null, '本步目标：'), g.goal));
    det.appendChild(h('p', { class: 'muted small' }, h('strong', null, '为什么要做：'), g.why));
    det.appendChild(h('p', { class: 'small' }, h('strong', null, '谁做：'), g.who, '　', h('strong', null, '预计：'), g.time));
    det.appendChild(h('h4', null, '按这个顺序做'));
    det.appendChild(olist(g.steps));
    det.appendChild(h('div', { class: 'gd-cols' },
      h('div', null, h('h4', null, '做完得到什么'), h('p', null, g.outputs), h('h4', null, '什么时候算完成'), h('p', null, g.done)),
      h('div', null, h('h4', null, '最常见的错误'), list(g.pitfalls))));
    det.appendChild(h('p', { class: 'small muted' }, '更多说明见 ', h('a', { href: '#/guide' }, '方法开发指南'), '；每个章节标题旁和右侧“提交条件检查”会实时提示还缺什么。'));
    return det;
  }

  /* ------------------------------------------------------------------ 下一步卡片 */
  function nextStepCard(method) {
    injectCss();
    var stages = (method && method.stages) || [];
    var roles = (method && method.my_roles) || [];
    var box = h('div', { class: 'gd-next' });
    var locked = function (s) { return s.status === 'approved' || s.status === 'completed'; };
    var cur = stages.filter(function (s) { return s.stale; })[0] || stages.filter(function (s) { return !locked(s); })[0];
    var done = stages.filter(function (s) { return locked(s) && !s.stale; }).length;
    if (!stages.length) return h('div');
    if (!cur) {
      box.appendChild(h('h3', null, '全部 ' + stages.length + ' 个阶段都已完成 🎉'));
      box.appendChild(h('p', null, '现在可以到“文档”标签生成《方法开发报告》Word/PDF 用于归档审批；然后把方法生命周期改为“验证”，进入方法验证。'));
      box.appendChild(h('a', { class: 'btn btn-primary', href: '#/m/' + method.id + '/docs' }, '去生成文档'));
      return box;
    }
    var g = STAGES[cur.key] || {};
    var isEditor = roles.indexOf('owner') >= 0 || roles.indexOf('author') >= 0;
    var gateRoles = cur.gate_roles || [];
    var title = '你现在在第 ' + (g.n || cur.ord || '?') + ' / ' + stages.length + ' 步：' + cur.title + '（已完成 ' + done + ' 步）';
    box.appendChild(h('h3', null, title));
    var body = h('div');
    box.appendChild(body);
    var go = function (label) { return h('a', { class: 'btn btn-primary', href: '#/m/' + method.id + '/stage/' + cur.key }, label); };
    var checksBox = h('div');
    if (cur.stale) {
      body.appendChild(h('p', null, '这一步已“失效”（它依赖的前置阶段被重新打开过）。请核对内容后点“重新确认”，再次提交复核。'));
      body.appendChild(go('去重新确认'));
    } else if (cur.status === 'in_review') {
      var who = gateRoles.map(function (r) { return r === 'approver' ? '批准人（QA）' : '复核人'; }).join(' → ');
      var mine = roles.indexOf('reviewer') >= 0 || roles.indexOf('approver') >= 0;
      body.appendChild(h('p', null, '已提交，等待 ' + (who || '复核人') + ' 签署。' + (mine ? '如果轮到您，请打开本阶段审阅内容并签署（需输入密码）。' : '期间内容已锁定，无需操作；可以提醒复核人。')));
      body.appendChild(go(mine ? '去审阅签署' : '查看进度'));
    } else if (cur.status === 'returned') {
      body.appendChild(h('p', null, '复核人退回了这一步。请先阅读退回意见，修改后再次提交。'));
      body.appendChild(go('去查看退回意见并修改'));
    } else {
      if (isEditor) {
        body.appendChild(h('p', null, h('strong', null, '这一步要做：'), g.goal || cur.desc || ''));
        if (g.steps) body.appendChild(olist(g.steps.slice(0, 3).concat(['……其余步骤见本阶段页面顶部的新手指引。'])));
        body.appendChild(h('p', { class: 'small muted' }, '完成后：' + (gateRoles.length ? '提交给 ' + gateRoles.map(function (r) { return r === 'approver' ? '批准人（QA）' : '复核人'; }).join(' → ') + ' 签署。' : '提交后本阶段直接完成。')));
        body.appendChild(go(cur.status === 'not_started' ? '开始这一步' : '继续填写'));
        body.appendChild(checksBox);
        // 还差什么：读取提交条件检查（失败则不显示）
        MF.api('GET', '/api/methods/' + method.id + '/stages/' + cur.key + '/checks').then(function (c) {
          var blocks = (c && c.blocks) || [];
          if (!blocks.length) { checksBox.appendChild(h('p', { class: 'small' }, '✔ 目前满足提交条件，可以提交。')); return; }
          checksBox.appendChild(h('p', { class: 'small' }, h('strong', null, '提交前还差 ' + blocks.length + ' 项：')));
          checksBox.appendChild(list(blocks.slice(0, 5).concat(blocks.length > 5 ? ['……另有 ' + (blocks.length - 5) + ' 项，见阶段页'] : []), 'gd-bad small'));
        }, function () { /* 忽略 */ });
      } else {
        body.appendChild(h('p', null, '这一步由开发人员填写（' + cur.title + '）。您当前不是本方法的编辑者，可以查看进度。'));
        body.appendChild(go('查看本阶段'));
      }
    }
    box.appendChild(h('p', { class: 'small muted', style: { marginTop: '8px' } }, '不熟悉流程？看 ', h('a', { href: '#/guide' }, '方法开发指南（流程图、新手 12 步、常见问题）'), '。'));
    return box;
  }

  /* ------------------------------------------------------------------ 指南页 /guide */
  function renderGuide(params, container) {
    injectCss();
    MF.setCrumbs([{ label: '方法开发指南' }]);
    MF.clear(container);
    var page = h('div', { class: 'gd-sec' });
    page.appendChild(h('h2', null, '方法开发指南'));
    page.appendChild(h('p', { class: 'muted' }, '给第一次做分析方法开发的人：先看懂整条路，再一步步在系统里做。系统会在每个阶段给出具体的步骤、检查项和提示。'));

    page.appendChild(h('div', { class: 'card gd-card' },
      h('h3', null, '一、什么是方法开发？'),
      h('p', null, '方法开发就是：先说清楚“这个检测要达到什么性能”（ATP），再选技术、评估风险、写方案并批准，然后做实验、做稳健性和稳定性、定控制策略，最后写报告和 SOP 草案，交给方法验证。'),
      h('p', null, '它的核心原则只有三条：①判据先于实验；②每个结论都有记录和依据；③关键节点由别人复核，签字后锁定。')));

    var flow = h('div', { class: 'gd-flow' });
    ORDER.forEach(function (k, i) {
      var g = STAGES[k];
      var gate = { atp: 'G1 复核', tech: 'G2 复核', plan: 'GP 复核+批准', explore: 'G3 复核', control: 'G4 复核+批准', report: 'G5 复核+批准' }[k];
      flow.appendChild(h('div', { class: 'gd-node' }, h('div', { class: 'n' }, '第 ' + g.n + ' 步　' + g.time),
        h('div', { class: 't' }, g.name, gate ? h('span', { class: 'gd-gate' }, gate) : null)));
    });
    page.appendChild(h('div', { class: 'card' }, h('h3', null, '二、整条流程（9 个阶段、6 个评审门）'), flow,
      h('p', { class: 'small muted' }, '合计默认约 20 周，可在方法页调整各阶段计划日期。带标记的是评审门：必须有人复核（或再加 QA 批准）才能进入下一步。')));

    page.appendChild(h('div', { class: 'card' }, h('h3', null, '三、新手 12 步走'), olist(STEPS12.map(function (s) { return s[0] + '：' + s[1]; }))));

    var det = h('div', { class: 'card' }, h('h3', null, '四、每个阶段怎么做'));
    ORDER.forEach(function (k) {
      var g = STAGES[k];
      var d = h('details', null, h('summary', { style: { cursor: 'pointer', fontWeight: '600', margin: '6px 0' } }, '第 ' + g.n + ' 步 ' + g.name + '　（' + g.time + '）'),
        h('p', null, h('strong', null, '目标：'), g.goal), h('p', { class: 'small' }, h('strong', null, '谁做：'), g.who),
        olist(g.steps), h('p', null, h('strong', null, '产出：'), g.outputs), h('p', null, h('strong', null, '常见错误：'), g.pitfalls.join('；')));
      det.appendChild(d);
    });
    page.appendChild(det);

    page.appendChild(h('div', { class: 'card' }, h('h3', null, '五、系统的几条规矩'), h('dl', null, RULES.map(function (r) {
      return h('div', { style: { margin: '6px 0' } }, h('dt', { style: { fontWeight: '600' } }, r[0]), h('dd', { style: { margin: '2px 0 0 0' } }, r[1]));
    }))));

    page.appendChild(h('div', { class: 'card' }, h('h3', null, '六、谁做什么（角色）'), h('table', { class: 'table' },
      h('thead', null, h('tr', null, ['角色', '职责'].map(function (t) { return h('th', null, t); }))),
      h('tbody', null, [
        ['方法负责人', '创建方法、调整方法团队、变更生命周期、重新打开阶段；对方法开发整体负责。'],
        ['开发人员（作者）', '填写各阶段内容、登记和记录实验、上传原始数据、提交复核。'],
        ['复核人', '审阅内容和证据，签署通过或写原因退回；不能是该阶段内容的编辑者。'],
        ['批准人（QA）', '在 GP、G4、G5 门按序在复核人之后签署；可重新打开已批准阶段。'],
        ['只读', '查看方法进度和内容。'],
        ['管理员', '管理用户和备份、校验审计链、配置文档设置。']
      ].map(function (r) { return h('tr', null, h('td', null, r[0]), h('td', null, r[1])); })))));

    page.appendChild(h('div', { class: 'card' }, h('h3', null, '七、术语小词典'), h('table', { class: 'table' },
      h('tbody', null, GLOSSARY.map(function (r) { return h('tr', null, h('td', { style: { whiteSpace: 'nowrap', fontWeight: '600' } }, r[0]), h('td', null, r[1])); })))));

    var faq = h('div', { class: 'card gd-faq' }, h('h3', null, '八、常见问题'));
    FAQ.forEach(function (q) { faq.appendChild(h('details', null, h('summary', null, q[0]), h('p', null, q[1]))); });
    page.appendChild(faq);

    page.appendChild(h('div', { class: 'card' }, h('h3', null, '九、更多资料'),
      list(['知识库：按阶段和技术列出写作要点、常见审评缺陷和实操经验。', '各阶段页顶部有“新手指引”，每个章节有写作提示和示例句；右侧“提交条件检查”会告诉您还差什么。']),
      h('p', null, h('a', { class: 'btn', href: '#/kb' }, '打开知识库'), ' ', h('a', { class: 'btn btn-primary', href: '#/methods' }, '去我的方法'))));
    container.appendChild(page);
  }

  MF.guide = { stagePanel: stagePanel, nextStepCard: nextStepCard, stages: STAGES, order: ORDER };
  MF.route('/guide', renderGuide);
})();
