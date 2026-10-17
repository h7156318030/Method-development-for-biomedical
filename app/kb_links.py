"""Resource-link library of the knowledge base: curated links to regulations, agencies, pharmacopoeias, literature
and tools for analytical method development.  Links change over time, so they live in the database (kb_links):
users can add / edit / deactivate them, and admins can run a health check.  The built-in list below is only
the starting set; syncing never overwrites a link that already exists (by URL) and never revives a deactivated one.

The URLs are entry points that were believed correct when this list was written - they are NOT guaranteed to be
current.  Run the health check (admin) after installation and whenever you suspect a change."""
import concurrent.futures
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import db

CATEGORIES = {
    "regulation": ("法规与指南", "Regulations & guidelines"),
    "agency": ("监管机构", "Regulatory agencies"),
    "pharmacopoeia": ("药典与标准", "Pharmacopoeias & standards"),
    "literature": ("文献与数据库", "Literature & databases"),
    "tools": ("统计与工具", "Statistics & tools"),
    "training": ("培训与社区", "Training & communities"),
}

# (category, title_zh, title_en, url, org, language, description_zh, description_en, tags)
SEED = [
    # ---------------------------------------------------------------- regulations & guidelines
    ("regulation", "ICH 质量指导原则总览", "ICH Quality Guidelines (index)", "https://www.ich.org/page/quality-guidelines", "ICH", "en",
     "Q 系列（Q2、Q8–Q14 等）所有质量指导原则的入口。", "Entry point to all ICH Q guidelines (Q2, Q8–Q14 …).", ["ICH", "Q"]),
    ("regulation", "ICH Q14 分析方法开发（PDF）", "ICH Q14 Analytical Procedure Development (PDF)", "https://database.ich.org/sites/default/files/ICH_Q14_Guideline_2023_1116.pdf", "ICH", "en",
     "ATP、增强方法、风险管理、控制策略、已确立条件、生命周期管理。", "ATP, enhanced approach, risk management, control strategy, established conditions, lifecycle.", ["ICH", "Q14", "ATP"]),
    ("regulation", "ICH Q2(R2) 分析方法验证（PDF）", "ICH Q2(R2) Validation of Analytical Procedures (PDF)", "https://database.ich.org/sites/default/files/ICH_Q2%28R2%29_Guideline_2023_1130.pdf", "ICH", "en",
     "性能特性、报告范围、验证设计、Annex 2 各技术示例。", "Performance characteristics, reportable range, validation design, Annex 2 examples per technique.", ["ICH", "Q2", "validation"]),
    ("regulation", "ICH Q9(R1) 质量风险管理（PDF）", "ICH Q9(R1) Quality Risk Management (PDF)", "https://database.ich.org/sites/default/files/ICH_Q9%28R1%29_Guideline_Step4_2022_1219.pdf", "ICH", "en",
     "FMEA/石川图等风险评估工具的原则与主观性管理。", "Principles of risk assessment tools (FMEA, Ishikawa) and management of subjectivity.", ["ICH", "Q9", "FMEA"]),
    ("regulation", "ICH Q12 产品生命周期管理（PDF）", "ICH Q12 Lifecycle Management (PDF)", "https://database.ich.org/sites/default/files/Q12_Guideline_Step4_2019_1119.pdf", "ICH", "en",
     "已确立条件（EC）、上市后变更管理方案（PACMP）。", "Established conditions (EC) and post-approval change management protocols (PACMP).", ["ICH", "Q12", "EC"]),
    ("regulation", "ICH M10 生物分析方法验证（PDF）", "ICH M10 Bioanalytical Method Validation (PDF)", "https://database.ich.org/sites/default/files/M10_Guideline_Step4_2022_0524.pdf", "ICH", "en",
     "关键试剂管理、稳定性、平行性等原则可借用于方法开发。", "Critical-reagent management, stability and parallelism principles are reusable in method development.", ["ICH", "M10"]),
    ("regulation", "FDA：分析程序与方法验证（药品与生物制品，2015）", "FDA: Analytical Procedures and Methods Validation for Drugs and Biologics (2015)", "https://www.fda.gov/media/87801/download", "FDA", "en",
     "分析程序内容、验证与生命周期管理的 FDA 指南。", "FDA guidance on analytical procedure content, validation and lifecycle management.", ["FDA", "validation"]),
    ("regulation", "FDA 指南文件检索", "FDA Guidance Documents search", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents", "FDA", "en",
     "检索 FDA 全部现行与草案指南。", "Search all current and draft FDA guidance documents.", ["FDA"]),
    ("regulation", "FDA：CAR-T 细胞产品研发考虑（2024）", "FDA: Considerations for the Development of CAR T Cell Products (2024)", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/considerations-development-chimeric-antigen-receptor-car-t-cell-products", "FDA CBER", "en",
     "CAR-T 的 CMC 与分析方法（流式、效力等）期望。", "CMC and analytical expectations for CAR-T (flow cytometry, potency, …).", ["FDA", "CAR-T", "cell therapy"]),
    ("regulation", "FDA：细胞与基因治疗产品效力保证（草案）", "FDA: Potency Assurance for Cellular and Gene Therapy Products (draft)", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/potency-assurance-cellular-and-gene-therapy-products", "FDA CBER", "en",
     "效力检测的设计、参比品、统计。草案，请核对是否已定稿。", "Potency assay design, reference materials, statistics. Draft - check whether it has been finalised.", ["FDA", "potency", "cell therapy"]),
    ("regulation", "FDA：数据完整性与 cGMP 合规问答（2018）", "FDA: Data Integrity and Compliance With cGMP - Q&A (2018)", "https://www.fda.gov/media/119267/download", "FDA", "en",
     "ALCOA、审计追踪、电子记录要求的实操解释。", "Practical interpretation of ALCOA, audit trails and electronic-record requirements.", ["FDA", "data integrity"]),
    ("regulation", "21 CFR Part 11 电子记录与电子签名", "21 CFR Part 11 Electronic Records; Electronic Signatures", "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11", "eCFR", "en",
     "法规原文（持续更新）。", "Regulation text (continuously updated).", ["FDA", "Part 11"]),
    ("regulation", "21 CFR Part 211 药品 cGMP", "21 CFR Part 211 cGMP for Finished Pharmaceuticals", "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211", "eCFR", "en",
     "实验室控制（Subpart I）等条款。", "Laboratory controls (Subpart I) and related provisions.", ["FDA", "cGMP"]),
    ("regulation", "EMA 科学指南总览", "EMA Scientific guidelines", "https://www.ema.europa.eu/en/human-regulatory-overview/research-development/scientific-guidelines", "EMA", "en",
     "EMA 采纳的 ICH 与欧盟科学指南入口。", "Entry to ICH and EU scientific guidelines adopted by EMA.", ["EMA"]),
    ("regulation", "EudraLex 第 4 卷（欧盟 GMP，含附录 11）", "EudraLex Volume 4 (EU GMP, incl. Annex 11)", "https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en", "European Commission", "en",
     "欧盟 GMP 指南；附录 11 为计算机化系统。", "EU GMP guidelines; Annex 11 covers computerised systems.", ["EU", "GMP", "Annex 11"]),
    ("regulation", "MHRA：GxP 数据完整性指南", "MHRA: GxP data integrity guidance", "https://www.gov.uk/government/publications/guidance-on-gxp-data-integrity", "MHRA", "en",
     "英国监管机构的数据完整性指南。", "UK regulator's data-integrity guidance.", ["MHRA", "data integrity"]),
    ("regulation", "PIC/S 出版物", "PIC/S publications", "https://picscheme.org/en/publications", "PIC/S", "en",
     "含数据完整性指南 PI 041 等。", "Includes the data-integrity guidance PI 041 and others.", ["PIC/S"]),
    ("regulation", "世界卫生组织 WHO（药品质量与标准）", "WHO (medicines quality and standards)", "https://www.who.int/", "WHO", "en",
     "WHO 技术报告（TRS）与质量保证指南：请在站内检索“Expert Committee on Specifications for Pharmaceutical Preparations”。", "WHO Technical Report Series and quality-assurance guidance: search the site for the Expert Committee on Specifications for Pharmaceutical Preparations.", ["WHO"]),
    # ---------------------------------------------------------------- agencies
    ("agency", "国家药监局 NMPA", "NMPA (China)", "https://www.nmpa.gov.cn/", "NMPA", "zh", "中国药品监督管理局官网：法规、公告。", "China's regulator: regulations and announcements.", ["China", "NMPA"]),
    ("agency", "药审中心 CDE", "CDE (China)", "https://www.cde.org.cn/", "CDE", "zh", "药品审评中心：技术指导原则、ICH 中文版与实施建议。", "Center for Drug Evaluation: technical guidance, ICH Chinese versions, implementation advice.", ["China", "CDE", "ICH"]),
    ("agency", "国家药典委员会", "Chinese Pharmacopoeia Commission", "https://www.chp.org.cn/", "ChP", "zh", "中国药典及其增补、公示。", "Chinese Pharmacopoeia, supplements and public notices.", ["China", "ChP"]),
    ("agency", "药典在线", "Pharmacopoeia online (ChP)", "https://ydz.chp.org.cn/", "ChP", "zh", "中国药典在线查询（需注册）。", "Online access to the Chinese Pharmacopoeia (registration required).", ["China", "ChP"]),
    ("agency", "FDA CBER（生物制品）", "FDA CBER (biologics)", "https://www.fda.gov/vaccines-blood-biologics", "FDA", "en", "细胞与基因治疗产品的监管与指南。", "Regulation and guidance for cell and gene therapy products.", ["FDA", "CBER"]),
    ("agency", "FDA CDER（药品）", "FDA CDER (drugs)", "https://www.fda.gov/drugs", "FDA", "en", "药品监管与指南。", "Drug regulation and guidance.", ["FDA", "CDER"]),
    ("agency", "EMA 欧洲药品管理局", "EMA (European Medicines Agency)", "https://www.ema.europa.eu/", "EMA", "en", "欧盟药品监管。", "EU medicines regulation.", ["EMA"]),
    ("agency", "日本 PMDA", "PMDA (Japan)", "https://www.pmda.go.jp/english/", "PMDA", "en", "日本医药品医疗器械综合机构（英文）。", "Pharmaceuticals and Medical Devices Agency (English).", ["Japan", "PMDA"]),
    ("agency", "加拿大卫生部：药品与健康产品", "Health Canada: drugs and health products", "https://www.canada.ca/en/health-canada/services/drugs-health-products.html", "Health Canada", "en", "加拿大药品监管。", "Canadian drug regulation.", ["Canada"]),
    ("agency", "澳大利亚 TGA", "TGA (Australia)", "https://www.tga.gov.au/", "TGA", "en", "澳大利亚治疗用品管理局。", "Therapeutic Goods Administration.", ["Australia"]),
    ("agency", "ICH 官网", "ICH website", "https://www.ich.org/", "ICH", "en", "ICH 指导原则、培训材料与新闻。", "ICH guidelines, training materials and news.", ["ICH"]),
    # ---------------------------------------------------------------- pharmacopoeias & standards
    ("pharmacopoeia", "USP 美国药典", "USP", "https://www.usp.org/", "USP", "en", "美国药典官网。", "United States Pharmacopeia.", ["USP"]),
    ("pharmacopoeia", "USP–NF 在线", "USP-NF online", "https://www.uspnf.com/", "USP", "en", "<1220>、<1225>、<1226>、<1032–1034> 等通则（订阅）。", "General chapters such as <1220>, <1225>, <1226>, <1032-1034> (subscription).", ["USP", "bioassay"]),
    ("pharmacopoeia", "欧洲药典（EDQM）", "European Pharmacopoeia (EDQM)", "https://www.edqm.eu/", "EDQM", "en", "欧洲药典；通则 5.3 生物检定统计。", "Ph. Eur.; general chapter 5.3 on statistical analysis of bioassays.", ["Ph. Eur."]),
    ("pharmacopoeia", "英国药典", "British Pharmacopoeia", "https://www.pharmacopoeia.com/", "BP", "en", "英国药典在线。", "BP online.", ["BP"]),
    ("pharmacopoeia", "CLSI 临床和实验室标准协会", "CLSI", "https://clsi.org/", "CLSI", "en", "含流式细胞术方法验证指南 H62。", "Includes H62 on validation of flow cytometry assays.", ["CLSI", "flow cytometry"]),
    ("pharmacopoeia", "ISO 国际标准化组织", "ISO", "https://www.iso.org/", "ISO", "en", "ISO 17025、20395 等标准目录。", "Catalogue incl. ISO 17025, 20395.", ["ISO"]),
    ("pharmacopoeia", "ASTM International", "ASTM International", "https://www.astm.org/", "ASTM", "en", "材料与方法标准。", "Standards for materials and methods.", ["ASTM"]),
    # ---------------------------------------------------------------- literature & databases
    ("literature", "PubMed", "PubMed", "https://pubmed.ncbi.nlm.nih.gov/", "NCBI", "en", "生物医学文献检索。", "Biomedical literature search.", ["search"]),
    ("literature", "PubMed Central（开放全文）", "PubMed Central (open full text)", "https://pmc.ncbi.nlm.nih.gov/", "NCBI", "en", "开放获取的全文文献。", "Open-access full-text articles.", ["open access"]),
    ("literature", "Europe PMC", "Europe PMC", "https://europepmc.org/", "EMBL-EBI", "en", "开放文献与预印本检索。", "Open literature and preprint search.", ["open access"]),
    ("literature", "检索：MIQE 指南（qPCR）", "Search: MIQE guidelines (qPCR)", "https://pubmed.ncbi.nlm.nih.gov/?term=MIQE+guidelines", "PubMed", "en", "qPCR 实验发表与报告的最低信息要求。", "Minimum information for publication of qPCR experiments.", ["qPCR", "MIQE"]),
    ("literature", "检索：dMIQE 指南（数字 PCR）", "Search: dMIQE guidelines (digital PCR)", "https://pubmed.ncbi.nlm.nih.gov/?term=dMIQE+guidelines", "PubMed", "en", "数字 PCR 报告要求。", "Reporting requirements for digital PCR.", ["ddPCR", "dMIQE"]),
    ("literature", "检索：OMIP（流式多色面板）", "Search: OMIP (optimised multicolour immunofluorescence panels)", "https://pubmed.ncbi.nlm.nih.gov/?term=OMIP+optimized+multicolor+immunofluorescence+panel", "PubMed", "en", "已发表的流式多色面板设计。", "Published flow-cytometry panel designs.", ["flow cytometry", "panel"]),
    ("literature", "检索：相对效力 / 平行线分析", "Search: relative potency / parallel-line analysis", "https://pubmed.ncbi.nlm.nih.gov/?term=relative+potency+parallelism+bioassay", "PubMed", "en", "生物活性测定的统计方法文献。", "Statistics of bioassays.", ["bioassay", "potency"]),
    ("literature", "检索：分析方法生命周期 / ATP", "Search: analytical procedure lifecycle / ATP", "https://pubmed.ncbi.nlm.nih.gov/?term=analytical+target+profile+analytical+procedure+lifecycle", "PubMed", "en", "ATP、增强方法的实践文献。", "Practice papers on ATP and the enhanced approach.", ["ATP", "Q14"]),
    ("literature", "bioRxiv 预印本", "bioRxiv", "https://www.biorxiv.org/", "CSHL", "en", "生物学预印本（未经同行评审）。", "Biology preprints (not peer reviewed).", ["preprint"]),
    ("literature", "Google 学术", "Google Scholar", "https://scholar.google.com/", "Google", "en", "跨来源学术检索。", "Cross-source academic search.", ["search"]),
    # ---------------------------------------------------------------- statistics & tools
    ("tools", "NIST 统计方法电子手册", "NIST e-Handbook of Statistical Methods", "https://www.itl.nist.gov/div898/handbook/", "NIST", "en", "DoE、回归、测量系统分析等统计方法参考。", "Reference for DoE, regression and measurement-system analysis.", ["statistics", "DoE"]),
    ("tools", "Eurachem 指南", "Eurachem guides", "https://www.eurachem.org/index.php/publications/guides", "Eurachem", "en", "方法验证与测量不确定度指南。", "Guides on method validation and measurement uncertainty.", ["validation", "uncertainty"]),
    ("tools", "JCGM/GUM 测量不确定度", "JCGM / GUM (measurement uncertainty)", "https://www.bipm.org/en/committees/jc/jcgm", "BIPM", "en", "测量不确定度表示指南。", "Guide to the expression of uncertainty in measurement.", ["uncertainty"]),
    ("tools", "R 项目", "The R Project", "https://www.r-project.org/", "R Foundation", "en", "统计计算与作图（开源）。", "Open-source statistical computing and graphics.", ["R"]),
    ("tools", "drc：剂量-反应曲线（R 包）", "drc: dose-response curves (R package)", "https://cran.r-project.org/package=drc", "CRAN", "en", "4PL/5PL 拟合与相对效力。", "4PL/5PL fitting and relative potency.", ["R", "bioassay"]),
    ("tools", "Bioconductor", "Bioconductor", "https://www.bioconductor.org/", "Bioconductor", "en", "流式（flowCore 等）与生物信息分析包。", "Packages for flow cytometry (flowCore, …) and bioinformatics.", ["R", "flow cytometry"]),
    ("tools", "FlowRepository", "FlowRepository", "https://flowrepository.org/", "ISAC", "en", "公开流式数据集。", "Public flow-cytometry datasets.", ["flow cytometry", "data"]),
    ("tools", "ISAC 国际细胞分析学会", "ISAC (International Society for Advancement of Cytometry)", "https://isac-net.org/", "ISAC", "en", "流式标准、培训与 MIFlowCyt。", "Flow standards, training and MIFlowCyt.", ["flow cytometry"]),
    # ---------------------------------------------------------------- training & communities
    ("training", "ISPE：GAMP 5 指南（第二版）", "ISPE: GAMP 5 Guide (2nd edition)", "https://ispe.org/publications/guidance-documents/gamp-5-guide-2nd-edition", "ISPE", "en", "计算机化系统验证的行业实践。", "Industry practice for computerised-system validation.", ["GAMP", "CSV"]),
    ("training", "ISPE", "ISPE", "https://ispe.org/", "ISPE", "en", "制药工程协会。", "International Society for Pharmaceutical Engineering.", ["community"]),
    ("training", "PDA 注射剂协会", "PDA (Parenteral Drug Association)", "https://www.pda.org/", "PDA", "en", "技术报告与培训。", "Technical reports and training.", ["community"]),
]


def row_from_seed(t):
    return {"category": t[0], "title": t[1], "title_en": t[2], "url": t[3], "org": t[4], "language": t[5],
            "description": t[6], "description_en": t[7], "tags": t[8]}


def sync_builtin(conn):
    """Insert built-in links that are missing (matched by URL).  Existing rows - edited, deactivated or not - are untouched."""
    n = 0
    for t in SEED:
        d = row_from_seed(t)
        if conn.execute("SELECT 1 FROM kb_links WHERE url=?", (d["url"],)).fetchone():
            continue
        conn.execute("INSERT INTO kb_links(category,title,title_en,url,org,language,description,description_en,tags,builtin,active,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,1,1,?,?)",
                     (d["category"], d["title"], d["title_en"], d["url"], d["org"], d["language"], d["description"], d["description_en"],
                      json.dumps(d["tags"], ensure_ascii=False), db.now(), db.now()))
        n += 1
    return n


# ---------------------------------------------------------------- validation
def clean(d):
    """Validate a user supplied link dict; returns the cleaned dict or raises ValueError (message in Chinese)."""
    out = {}
    cat = d.get("category")
    if cat not in CATEGORIES:
        raise ValueError("分类无效")
    out["category"] = cat
    for k, label, n, req in (("title", "标题", 300, True), ("title_en", "英文标题", 300, False), ("org", "机构", 120, False), ("language", "语言", 20, False),
                            ("description", "说明", 1000, False), ("description_en", "英文说明", 1000, False)):
        v = d.get(k, "")
        if v is None:
            v = ""
        if not isinstance(v, str):
            raise ValueError("%s必须是文本" % label)
        v = v.strip()
        if req and not v:
            raise ValueError("请填写%s" % label)
        if len(v) > n:
            raise ValueError("%s过长（最多 %d 字）" % (label, n))
        out[k] = v
    url = d.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("请填写网址")
    url = url.strip()
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc or len(url) > 1000:
        raise ValueError("网址须以 http:// 或 https:// 开头")
    out["url"] = url
    tags = d.get("tags") or []
    if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or len(t) > 40 for t in tags):
        raise ValueError("标签须是字符串列表（最多 20 个）")
    out["tags"] = [t.strip() for t in tags if t.strip()]
    return out


# ---------------------------------------------------------------- health check
def _public_host(host):
    """True only when every address the host resolves to is public (guards the server-side check against SSRF)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


class _NoRedirectToPrivate(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlparse(newurl)
        if p.scheme not in ("http", "https") or not p.hostname or not _public_host(p.hostname):
            raise urllib.error.URLError("重定向到非公网地址，已拒绝")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url, timeout=10):
    """(status_code or None, note).  HEAD first, GET (first bytes only) as a fallback; public addresses only."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None, "网址无效"
    if not _public_host(p.hostname):
        return None, "主机无法解析或不是公网地址，已跳过检查"
    opener = urllib.request.build_opener(_NoRedirectToPrivate())
    headers = {"User-Agent": "Mozilla/5.0 (MethodFlow link check)", "Accept": "*/*"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with opener.open(req, timeout=timeout) as r:
                if method == "GET":
                    r.read(512)
                return r.status, ""
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 404, 405, 406, 429, 501):
                continue                                  # many servers reject HEAD; retry with GET
            return e.code, e.reason if isinstance(e.reason, str) else ""
        except Exception as e:                            # DNS, TLS, timeout ...
            if method == "HEAD":
                continue
            return None, "%s" % type(e).__name__
    return None, "无法访问"


def check_links(rows, workers=8):
    """rows: list of dicts with id/url.  Returns {id: (status, note)}; runs in a thread pool."""
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(check_url, r["url"]): r["id"] for r in rows}
        for f in concurrent.futures.as_completed(futs):
            try:
                out[futs[f]] = f.result()
            except Exception as e:  # pragma: no cover
                out[futs[f]] = (None, type(e).__name__)
    return out
