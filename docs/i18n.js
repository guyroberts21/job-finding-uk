/* English / Chinese (Simplified) strings for the page.
   Job titles, employers and advert text come from the job boards and stay in their original language. */
(() => {
  "use strict";

  const STRINGS = {
    en: {
      appTitle: "Job Finder for 宝宝",
      docTitle: "Job Finder for 宝宝",
      tagline: "Graduate roles in comms, community, admin & support, refreshed every morning.",
      loading: "Loading…",
      summary: "Summary",
      filters: "Filters",
      jobTypes: "Job types",
      search: "Search",
      searchPlaceholder: "Title, employer, skill…",
      location: "Location",
      allLocations: "All locations",
      visaSponsorship: "Visa sponsorship",
      any: "Any",
      "visa.offered": "Sponsorship offered",
      "visa.not_offered": "No sponsorship",
      "visa.not_offered_long": "Not offered",
      "visa.rtw_required": "Right to work needed",
      "visa.rtw_required_long": "Right to work required",
      "visa.not_stated": "Not stated",
      sortBy: "Sort by",
      "sort.match": "Best match",
      "sort.closing": "Closing soonest",
      "sort.posted": "Newest",
      "sort.salary": "Highest salary",
      "sort.time": "Quickest to apply",
      minMatch: "Minimum match:",
      hideSenior: "Hide senior roles",
      newOnly: "New today",
      closingSoon: "Closing within 7 days",
      reset: "Reset filters",
      "th.match": "Match",
      "th.role": "Role",
      "th.location": "Location",
      "th.salary": "Salary",
      "th.closes": "Closes",
      "th.application": "Application",
      "th.visa": "Visa",
      "th.links": "Links",
      langNote: "",
      updatedAgo: "Updated {when}",
      waitingFirst: "Waiting for the first daily update",
      minAgo: "{n} min ago",
      hAgo: "{n} h ago",
      loadFailed: "Couldn't load job data",
      loadFailedRow: "Couldn't load jobs ({err}). Try refreshing the page.",
      toastNew: "Updated: {n} new job",
      toastNewPlural: "Updated: {n} new jobs",
      toastRefreshed: "Listings refreshed",
      noticeKeysLead: "Almost ready: ",
      noticeKeys1: "the daily job feed needs its free API keys. Add ",
      noticeKeys2: " (and optionally ",
      noticeKeys3: ") as repository secrets, then run the “Daily job update” workflow. See the README for the 5-minute steps.",
      noticeErrors: "The last update hit errors: {errors}",
      "stat.live": "live roles",
      "stat.new": "new today",
      "stat.closing": "closing this week",
      "stat.strong": "strong matches (70%+)",
      count: "Showing {shown} of {total} roles",
      emptyFiltered: "No roles match these filters. Try lowering the minimum match or clearing a filter.",
      emptyNone: "No roles yet — the first daily update hasn't run.",
      tagNew: "New",
      notStated: "Not stated",
      posted: "Posted {date}",
      viewListing: "View listing ↗",
      viewListingAria: "View the full listing for {title} (opens in a new tab)",
      apply: "Apply ↗",
      applyAria: "Apply for {title} on the employer's site (opens in a new tab)",
      details: "Details",
      hideDetails: "Hide details",
      "check.ok": "Link checked",
      "check.blocked": "Open manually",
      "check.unknown": "Not verified",
      "check.skipped": "Not checked",
      "check.closed": "Closed",
      "check.broken": "Broken link",
      "panel.summary": "Summary",
      noSummary: "No summary available — open the listing.",
      shortPreview: "{source} only shares a short preview; see the listing for the full advert.",
      "panel.resp": "Key responsibilities",
      noResp: "Not listed in the advert preview — see the full listing.",
      "panel.apply": "How to apply",
      applyVia: "Apply via: {via}",
      "panel.match": "Match {score}%",
      mentions: "Mentions: {list}",
      sourceLine: "Source: {source} · First seen {first} · Last confirmed live {last}",
      listingCheck: "Listing check: {note}",
      applyCheck: "Apply-link check: {note}",
      footer1a: "Listings come from the official ",
      footer1b: " and ",
      footer1c: " APIs. Links are checked daily, but always confirm details and closing dates on the listing before applying.",
      footer2: "Match % and application times are automated estimates based on the CV's skills, not a guarantee.",
      reedJobs: "Jobs by Reed",
      adzunaJobs: "Jobs by Adzuna",
      joobleJobs: "Jooble",
      nhsJobs: "NHS Jobs",
      minutes: "{n} min",
      hours: "{n} h",
      listSep: ", ",
    },
    zh: {
      appTitle: "宝宝的求职小助手",
      docTitle: "宝宝的求职小助手",
      tagline: "传播、社区、行政与支持类毕业生岗位，每天早上自动更新。",
      loading: "加载中…",
      summary: "概览",
      filters: "筛选",
      jobTypes: "职位类型",
      search: "搜索",
      searchPlaceholder: "职位名称、雇主、技能…（英文）",
      location: "地点",
      allLocations: "全部地点",
      visaSponsorship: "签证担保",
      any: "不限",
      "visa.offered": "提供签证担保",
      "visa.not_offered": "不提供担保",
      "visa.not_offered_long": "不提供担保",
      "visa.rtw_required": "需已有工作许可",
      "visa.rtw_required_long": "需已有英国工作许可",
      "visa.not_stated": "未说明",
      sortBy: "排序",
      "sort.match": "最匹配",
      "sort.closing": "最先截止",
      "sort.posted": "最新发布",
      "sort.salary": "薪资最高",
      "sort.time": "申请最快",
      minMatch: "最低匹配度：",
      hideSenior: "隐藏高级职位",
      newOnly: "今日新增",
      closingSoon: "7 天内截止",
      reset: "重置筛选",
      "th.match": "匹配度",
      "th.role": "职位",
      "th.location": "地点",
      "th.salary": "薪资",
      "th.closes": "截止日期",
      "th.application": "申请方式",
      "th.visa": "签证",
      "th.links": "链接",
      langNote: "职位名称、雇主和招聘广告内容来自英国招聘网站，保留英文原文；其余界面均为中文。",
      updatedAgo: "{when}更新",
      waitingFirst: "等待第一次每日更新",
      minAgo: "{n} 分钟前",
      hAgo: "{n} 小时前",
      loadFailed: "无法加载职位数据",
      loadFailedRow: "无法加载职位（{err}）。请刷新页面重试。",
      toastNew: "已更新：新增 {n} 个职位",
      toastNewPlural: "已更新：新增 {n} 个职位",
      toastRefreshed: "职位列表已刷新",
      noticeKeysLead: "快完成了：",
      noticeKeys1: "每日职位更新需要免费的 API 密钥。请将 ",
      noticeKeys2: "（以及可选的 ",
      noticeKeys3: "）添加为仓库密钥，然后运行 “Daily job update” 工作流。详见 README。",
      noticeErrors: "上次更新出错：{errors}",
      "stat.live": "在招职位",
      "stat.new": "今日新增",
      "stat.closing": "本周截止",
      "stat.strong": "高度匹配（70%+）",
      count: "显示 {shown} / {total} 个职位",
      emptyFiltered: "没有符合筛选条件的职位。试试降低最低匹配度或清除筛选。",
      emptyNone: "暂无职位——第一次每日更新还没有运行。",
      tagNew: "新",
      notStated: "未说明",
      posted: "{date}发布",
      viewListing: "查看职位 ↗",
      viewListingAria: "查看 {title} 的完整职位信息（在新标签页打开）",
      apply: "申请 ↗",
      applyAria: "在雇主网站申请 {title}（在新标签页打开）",
      details: "详情",
      hideDetails: "收起详情",
      "check.ok": "链接已检查",
      "check.blocked": "请手动打开",
      "check.unknown": "未验证",
      "check.skipped": "未检查",
      "check.closed": "已关闭",
      "check.broken": "链接失效",
      "panel.summary": "职位摘要",
      noSummary: "暂无摘要——请打开职位页面查看。",
      shortPreview: "{source} 只提供简短预览，完整广告请打开职位页面查看。",
      "panel.resp": "主要职责",
      noResp: "广告预览中未列出——请查看完整职位信息。",
      "panel.apply": "如何申请",
      applyVia: "申请渠道：{via}",
      "panel.match": "匹配度 {score}%",
      mentions: "广告提到：{list}",
      sourceLine: "来源：{source} · 首次发现 {first} · 最近确认在招 {last}",
      listingCheck: "职位链接检查：{note}",
      applyCheck: "申请链接检查：{note}",
      footer1a: "职位来自官方 ",
      footer1b: " 和 ",
      footer1c: " 接口。链接每天检查一次，但申请前请务必在职位页面核对详情和截止日期。",
      footer2: "匹配度和申请时间是根据简历技能自动估算的，仅供参考。",
      reedJobs: "Reed 招聘",
      adzunaJobs: "Adzuna 招聘",
      joobleJobs: "Jooble",
      nhsJobs: "NHS Jobs（英国国民医疗服务体系）",
      minutes: "{n} 分钟",
      hours: "{n} 小时",
      listSep: "、",
    },
  };

  // ---- Chinese versions of the text the fetcher generates (exact English strings → Chinese) ----
  const ZH_EXACT = {
    // categories / locations (by id)
    "cat.digital_community": "数字包容与社区",
    "cat.comms": "传播、内容与社交媒体",
    "cat.admin": "行政与客户服务",
    "cat.support": "老年人、青少年与中文支持",
    "loc.manchester": "曼彻斯特",
    "loc.sheffield": "谢菲尔德",
    "loc.london": "伦敦",
    "loc.remote": "远程（英国）",
    // application process types
    "Application form + supporting statement": "申请表 + 个人陈述",
    "Email CV + covering letter": "邮件发送简历 + 求职信",
    "Apply on employer / agency website": "在雇主 / 中介网站申请",
    "Quick apply on Reed (CV)": "Reed 快速申请（简历）",
    "Via Adzuna to the employer / agency site": "经 Adzuna 跳转到雇主 / 中介网站",
    "Via Jooble to the employer / agency site": "经 Jooble 跳转到雇主 / 中介网站",
    "Open the listing (Jooble forwards you to the original advert)": "打开职位页面（Jooble 会跳转到原始招聘广告）",
    "Jooble → advertiser": "Jooble → 招聘方",
    "Create an account on the NHS Jobs website": "在 NHS Jobs 网站注册账号",
    "NHS Jobs": "NHS Jobs 网站",
    // steps
    "Request or download the application pack": "索取或下载申请资料包",
    "Fill in personal details, education and employment history": "填写个人信息、教育和工作经历",
    "Write a supporting statement against the person specification (STAR examples)": "对照岗位要求（Person Specification）写个人陈述，用 STAR 法举例",
    "Complete the equality monitoring form and submit": "填写平等机会监测表并提交",
    "Tailor the CV to the advert": "根据招聘广告调整简历",
    "Write a short covering email or letter": "写一封简短的求职邮件或求职信",
    "Email both to the address in the advert": "把简历和求职信发到广告中的邮箱",
    "Create an account on the employer's portal": "在雇主的招聘网站注册账号",
    "Upload a tailored CV and fill in the form": "上传调整好的简历并填写表格",
    "Answer any screening questions, then submit": "回答筛选问题，然后提交",
    "Open the apply link (employer or agency site)": "打开申请链接（雇主或中介网站）",
    "Upload a tailored CV and complete the form": "上传调整好的简历并完成表格",
    "Sign in to Reed": "登录 Reed",
    "Upload the tailored CV": "上传调整好的简历",
    "Add a short cover note, then submit": "附上一段简短的求职说明，然后提交",
    "Open the listing (Adzuna forwards you to the advertiser)": "打开职位页面（Adzuna 会跳转到招聘方网站）",
    "Follow the advertiser's apply steps": "按招聘方的申请步骤操作",
    "Upload a tailored CV and submit": "上传调整好的简历并提交",
    "Answer the application questions in full": "完整回答申请问题",
    "Write a tailored cover letter": "写一封有针对性的求职信",
    "Add a portfolio link": "附上作品集链接",
    // notes
    "The advert mentions an assessment, test or task": "广告提到有测评、测试或任务",
    "A DBS check is mentioned (usually after an offer)": "需要 DBS 背景审查（通常在录用后进行）",
    "The advert asks for the CV as a Word document": "广告要求简历为 Word 格式",
    "Times include tailoring the CV/statement; first-time portal sign-ups take longer": "时间包括调整简历 / 陈述；首次注册招聘网站会更久",
    // apply via
    "Reed (quick apply)": "Reed（快速申请）",
    "Adzuna → advertiser": "Adzuna → 招聘方",
    // match reasons: skill groups
    "Social media": "社交媒体",
    "Content & copywriting": "内容与文案",
    "Video & design": "视频与设计",
    "Events": "活动策划",
    "Community engagement": "社区参与",
    "Digital inclusion": "数字包容",
    "Customer service": "客户服务",
    "Admin & IT": "行政与办公软件",
    "Research & reporting": "调研与报告",
    "Older people": "老年人服务",
    "Young people": "青少年工作",
    "Journalism & media": "新闻与媒体",
    "Communication skills": "沟通能力",
    "Languages": "语言能力",
    "Entry-level": "入门级",
    "Little overlap with the CV skills": "与简历技能重合较少",
    // bonuses / penalties
    "Mandarin/Chinese is an asset": "会中文 / 普通话是加分项",
    "Open to graduates / entry level": "欢迎应届生 / 入门级",
    "Digital inclusion work": "数字包容工作",
    "Supports older people": "服务老年人",
    "Junior-friendly job title": "适合新人的职位名称",
    "Senior role": "高级职位",
    "Manager role": "经理职位",
    "Asks for 3+ years' experience": "要求 3 年以上经验",
    "Asks for 2 years' experience": "要求 2 年经验",
    "Asks for an experienced professional": "要求有经验的专业人士",
    "Driving licence required": "需要驾照",
    "Specialist qualification needed": "需要专业资格",
    "Sales/commission role": "销售 / 提成类职位",
    // flags
    "Driving licence": "驾照",
    "DBS check": "DBS 背景审查",
    "Mandarin/Chinese": "中文 / 普通话",
    "Portfolio requested": "需要作品集",
    "Cover letter": "求职信",
    "Supporting statement": "个人陈述",
    "No CVs accepted": "不接受简历",
    "Assessment/test": "测评 / 测试",
    "Weekend/evening work": "周末 / 晚间工作",
    "Hybrid": "混合办公",
    "Remote/home-based": "远程 / 居家办公",
    // link-check notes
    "Page loaded": "页面正常",
    "Page says the vacancy has closed": "页面显示职位已关闭",
    "Not a web link": "不是网页链接",
    "Test run": "测试运行",
    // salary / contract
    "Not stated": "未说明",
    "Salary not specified": "未说明薪资",
    "Salary negotiable": "薪资面议",
    "Competitive salary": "薪资有竞争力",
  };

  // Patterns for generated text with a variable part.
  const ZH_PATTERNS = [
    [/^Online portal \((.+)\)$/, (m) => `在线招聘系统（${m[1]}）`],
    [/^Create an account on the (.+)$/, (m) => `在${m[1]}注册账号`],
    [/^Employer site \((.+)\)$/, (m) => `雇主网站（${m[1]}）`],
    [/^Site blocks automated checks \((\d+)\); open it manually$/, (m) => `网站阻止自动检查（${m[1]}），请手动打开`],
    [/^Page not found \((\d+)\)$/, (m) => `页面不存在（${m[1]}）`],
    [/^Could not reach page: (.+)$/, (m) => `无法访问页面：${m[1]}`],
  ];

  const ZH_CONTRACT = { permanent: "长期", contract: "合同", temporary: "临时", "full-time": "全职", "part-time": "兼职",
    internship: "实习", apprenticeship: "学徒", volunteer: "志愿者", secondment: "借调", "fixed-term": "固定期限",
    "fixed term": "固定期限", bank: "临时人员库（Bank）" };
  const ZH_SALARY = [
    [/\bper annum\b/gi, "/年"], [/\bper year\b/gi, "/年"], [/\bper hour\b/gi, "/小时"], [/\bper day\b/gi, "/天"],
    [/\bper week\b/gi, "/周"], [/\bper month\b/gi, "/月"], [/\bpro[- ]rata\b/gi, "按比例"], [/\binc(luding)? benefits\b/gi, "含福利"],
    [/\(est\.\)/g, "（估算）"], [/^up to\b/i, "最高"], [/\bnegotiable\b/gi, "可议"], [/\bOTE\b/g, "含提成预期收入"],
    [/\bplus benefits\b/gi, "另加福利"], [/\bbonus\b/gi, "奖金"],
  ];

  const STORE_KEY = "jobfinder-lang";
  let lang = "en";
  try {
    const fromUrl = new URLSearchParams(location.search).get("lang");
    const saved = localStorage.getItem(STORE_KEY);
    lang = fromUrl === "zh" || fromUrl === "en" ? fromUrl : saved === "zh" ? "zh" : "en";
  } catch (e) { /* storage blocked: stay on English */ }

  const fill = (s, vars) => (vars ? s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? vars[k] : "")) : s);

  const I18N = {
    get lang() { return lang; },
    locale() { return lang === "zh" ? "zh-CN" : "en-GB"; },
    t(key, vars) {
      const s = (STRINGS[lang] && STRINGS[lang][key]) ?? STRINGS.en[key] ?? key;
      return fill(s, vars);
    },
    /** Translate a generated English string (process step, flag, reason…). Falls back to the original. */
    tx(text) {
      if (lang !== "zh" || typeof text !== "string" || !text) return text;
      if (ZH_EXACT[text]) return ZH_EXACT[text];
      for (const [rx, fn] of ZH_PATTERNS) {
        const m = text.match(rx);
        if (m) return fn(m);
      }
      return text;
    },
    category(id, fallback) { return lang === "zh" ? ZH_EXACT[`cat.${id}`] || fallback : fallback; },
    place(id, fallback) { return lang === "zh" ? ZH_EXACT[`loc.${id}`] || fallback : fallback; },
    reason(r) {
      if (lang !== "zh" || typeof r !== "string") return r;
      const m = r.match(/^Skills overlap: (.+)$/);
      if (m) return "技能匹配：" + m[1].split(", ").map((x) => ZH_EXACT[x] || x).join("、");
      const pm = r.match(/^([+−-]) (.+)$/);
      if (pm) return `${pm[1]} ${ZH_EXACT[pm[2]] || pm[2]}`;
      return ZH_EXACT[r] || r;
    },
    contract(s) {
      if (lang !== "zh" || !s) return s;
      return s.split(/,\s*/).map((p) => ZH_CONTRACT[p.toLowerCase()] || p).join("，");
    },
    salary(s) {
      if (lang !== "zh" || !s) return s;
      if (ZH_EXACT[s]) return ZH_EXACT[s];
      return ZH_SALARY.reduce((acc, [rx, rep]) => acc.replace(rx, rep), s).replace(/\s+\//g, "/");
    },
    setLang(next) {
      lang = next === "zh" ? "zh" : "en";
      try { localStorage.setItem(STORE_KEY, lang); } catch (e) { /* ignore */ }
      I18N.applyStatic();
    },
    /** Update every element marked with data-i18n / data-i18n-placeholder / data-i18n-aria. */
    applyStatic(root = document) {
      document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
      document.title = I18N.t("docTitle");
      root.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = I18N.t(n.dataset.i18n); });
      root.querySelectorAll("[data-i18n-placeholder]").forEach((n) => { n.placeholder = I18N.t(n.dataset.i18nPlaceholder); });
      root.querySelectorAll("[data-i18n-aria]").forEach((n) => { n.setAttribute("aria-label", I18N.t(n.dataset.i18nAria)); });
      root.querySelectorAll(".lang-btn").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
      const note = document.getElementById("langNote");
      if (note) note.hidden = lang !== "zh";
    },
  };

  window.I18N = I18N;
})();
