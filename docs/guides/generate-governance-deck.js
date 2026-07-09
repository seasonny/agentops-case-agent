/**
 * Case Agent — 治理與價值主張 Workshop 簡報
 * 白底、簡潔、約 10–12 張 / 10 分鐘
 *
 * 產出：docs/guides/Case-Agent-Governance-Workshop.pptx
 * 執行：node docs/guides/generate-governance-deck.js
 */

const path = require("path");
const pptxgen = require("pptxgenjs");

const OUT = path.join(__dirname, "Case-Agent-Governance-Workshop.pptx");

const C = {
  bg: "FFFFFF",
  title: "111827",
  body: "374151",
  muted: "6B7280",
  accent: "1D4ED8",
  accentLight: "EFF6FF",
  line: "E5E7EB",
  warn: "B45309",
  warnBg: "FFFBEB",
  ok: "047857",
  okBg: "ECFDF5",
};

function slide(pres) {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  return s;
}

function header(s, title, subtitle) {
  s.addText(title, {
    x: 0.7,
    y: 0.45,
    w: 8.6,
    h: 0.65,
    fontSize: 26,
    bold: true,
    color: C.title,
    fontFace: "Arial",
  });
  if (subtitle) {
    s.addText(subtitle, {
      x: 0.7,
      y: 1.05,
      w: 8.6,
      h: 0.35,
      fontSize: 13,
      color: C.muted,
      fontFace: "Arial",
    });
  }
  s.addShape("rect", {
    x: 0.7,
    y: 1.45,
    w: 1.2,
    h: 0.04,
    fill: { color: C.accent },
    line: { color: C.accent },
  });
}

function bullets(s, items, opts = {}) {
  const y = opts.y ?? 1.75;
  const h = opts.h ?? 4.8;
  s.addText(
    items.map((t) => ({ text: t, options: { bullet: true, breakLine: true } })),
    {
      x: 0.7,
      y,
      w: 8.6,
      h,
      fontSize: opts.fontSize ?? 15,
      color: C.body,
      fontFace: "Arial",
      paraSpaceAfter: 10,
      valign: "top",
    }
  );
}

function quoteBox(s, text, y = 5.0) {
  s.addShape("rect", {
    x: 0.7,
    y,
    w: 8.6,
    h: 0.95,
    fill: { color: C.accentLight },
    line: { color: C.line, width: 0.5 },
  });
  s.addText(text, {
    x: 0.95,
    y: y + 0.12,
    w: 8.1,
    h: 0.7,
    fontSize: 14,
    color: C.accent,
    bold: true,
    fontFace: "Arial",
    valign: "middle",
  });
}

function createPresentation() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "Case Agent";
  pres.title = "Case Agent — 治理與價值主張";

  // 1 封面
  {
    const s = slide(pres);
    s.addText("Case Agent", {
      x: 0.7,
      y: 1.8,
      w: 8.6,
      h: 0.9,
      fontSize: 40,
      bold: true,
      color: C.title,
      fontFace: "Arial",
    });
    s.addText("可治理的 Enterprise AI Agent 參考實作", {
      x: 0.7,
      y: 2.75,
      w: 8.6,
      h: 0.5,
      fontSize: 20,
      color: C.accent,
      fontFace: "Arial",
    });
    s.addText("LLM 理解 · 程式治理 · 縱深防禦", {
      x: 0.7,
      y: 3.45,
      w: 8.6,
      h: 0.4,
      fontSize: 14,
      color: C.muted,
      fontFace: "Arial",
    });
    s.addShape("rect", {
      x: 0.7,
      y: 4.2,
      w: 2.0,
      h: 0.05,
      fill: { color: C.accent },
      line: { color: C.accent },
    });
  }

  // 2 問題
  {
    const s = slide(pres);
    header(s, "企業真正缺的是什麼？", "不是更聰明的 chatbot");
    bullets(s, [
      "LLM 能力已足夠，但 Enterprise 採用卡在校準與信任",
      "Support Case 需要：理解、執行、回覆——且每一步可稽核",
      "全自動、無邊界的 AI 在 production 不可接受",
      "我們要的是：敢放進既有 workflow 的隊友，不是自走炮",
    ]);
    quoteBox(s, "目標不是最大化自動化，是建立信任。");
  }

  // 3 核心命題
  {
    const s = slide(pres);
    header(s, "核心命題：Prompt 不是治理", "引導 ≠ 約束");
    s.addShape("rect", {
      x: 0.7,
      y: 1.85,
      w: 8.6,
      h: 1.35,
      fill: { color: C.warnBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText("只在 prompt 寫「請不要執行危險指令」\n→ 沒有約束力，上不了 production", {
      x: 0.95,
      y: 2.0,
      w: 8.2,
      h: 1.1,
      fontSize: 16,
      color: C.warn,
      fontFace: "Arial",
      valign: "middle",
    });
    bullets(
      s,
      [
        "Prompt：引導 LLM 怎麼想、怎麼寫",
        "Policy / Guardrail：程式 enforce——能不能做、能不能發",
        "兩者缺一不可，但不能互相取代",
      ],
      { y: 3.45, fontSize: 16 }
    );
    quoteBox(s, "Governance over Intelligence — 治理比聰明更重要。");
  }

  // 4 分工
  {
    const s = slide(pres);
    header(s, "誰負責什麼？", "理解交 LLM，邊界交程式");
    const rows = [
      [
        { text: "環節", options: { bold: true, fill: { color: C.accentLight } } },
        { text: "負責方", options: { bold: true, fill: { color: C.accentLight } } },
        { text: "能否只靠 Prompt？", options: { bold: true, fill: { color: C.accentLight } } },
      ],
      ["理解意圖", "LLM", "—"],
      ["能不能執行", "Policy / Decision Engine", "❌ 必須程式"],
      ["實際操作", "MCP + argv 白名單", "❌ 必須程式"],
      ["解讀結果", "LLM", "—"],
      ["回覆能不能發", "Grounding + Guardrail", "❌ 必須程式"],
      ["留下軌跡", "Audit", "❌ 必須程式"],
    ];
    s.addTable(rows, {
      x: 0.7,
      y: 1.75,
      w: 8.6,
      colW: [2.2, 3.2, 3.2],
      fontSize: 13,
      color: C.body,
      border: { type: "solid", color: C.line, pt: 0.5 },
      align: "left",
      valign: "middle",
    });
  }

  // 5 縱深防禦
  {
    const s = slide(pres);
    header(s, "縱深防禦（Defense in Depth）", "每一層可設定、可測試、可稽核");
    const flow = [
      "事件進入",
      "L0  Trigger — 誰的留言要處理？",
      "    → LLM 理解 — 意圖、工具計畫、協作回覆",
      "L1  危險指令攔截",
      "L2  Policy — 能力包、工具 allowlist",
      "L3  Exec MCP — argv 白名單",
      "    → 執行 → LLM 解讀",
      "L4  Grounding + Guardrail — 防偽造、防洩漏",
      "    → Audit / 回覆",
    ];
    s.addText(flow.join("\n"), {
      x: 0.9,
      y: 1.8,
      w: 4.2,
      h: 4.5,
      fontSize: 13,
      color: C.body,
      fontFace: "Courier New",
      valign: "top",
    });
    bullets(
      s,
      [
        "客戶敢用，是因為邊界清楚",
        "不是因為模型特別聰明",
        "LLM 負責「提議」",
        "程式負責「裁決」",
      ],
      { y: 1.85, h: 3.5 }
    );
    s.addShape("rect", {
      x: 5.35,
      y: 1.75,
      w: 4.0,
      h: 3.6,
      fill: { color: C.okBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText(
      "允許才執行\n允許才發送",
      {
        x: 5.55,
        y: 2.9,
        w: 3.6,
        h: 1.2,
        fontSize: 22,
        bold: true,
        color: C.ok,
        align: "center",
        valign: "middle",
        fontFace: "Arial",
      }
    );
  }

  // 6 Guardrailed ReAct
  {
    const s = slide(pres);
    header(s, "Guardrailed ReAct", "不是傳聲筒，是在 workflow 裡協作");
    const steps = [
      ["Reason", "LLM 讀 Case、理解 SE 要什麼"],
      ["Decision", "DecisionEngine 單次裁決（policy + approval）"],
      ["Act", "MCP 執行（允許時）"],
      ["Observe", "LLM 解讀 MCP 輸出"],
      ["Reply", "撰寫回覆 → Grounding → 發送"],
    ];
    let y = 1.85;
    steps.forEach(([label, desc], i) => {
      s.addShape("rect", {
        x: 0.7,
        y,
        w: 1.3,
        h: 0.55,
        fill: { color: C.accent },
        line: { color: C.accent },
      });
      s.addText(label, {
        x: 0.7,
        y,
        w: 1.3,
        h: 0.55,
        fontSize: 12,
        bold: true,
        color: C.bg,
        align: "center",
        valign: "middle",
        fontFace: "Arial",
      });
      s.addText(desc, {
        x: 2.15,
        y: y + 0.08,
        w: 7.1,
        h: 0.4,
        fontSize: 14,
        color: C.body,
        fontFace: "Arial",
      });
      if (i < steps.length - 1) {
        s.addText("↓", {
          x: 1.2,
          y: y + 0.52,
          w: 0.3,
          h: 0.25,
          fontSize: 12,
          color: C.muted,
        });
      }
      y += 0.78;
    });
    quoteBox(s, "對話是介面，Workflow 才是產品。", 5.15);
  }

  // 6b Decision 合一 — 現況 vs 目標
  {
    const s = slide(pres);
    header(s, "Decision 合一", "一個菱形：理解 → 裁決 → 執行");
    s.addText("現況（Defense in Depth）", {
      x: 0.7,
      y: 1.75,
      w: 4.0,
      h: 0.35,
      fontSize: 14,
      bold: true,
      color: C.warn,
      fontFace: "Arial",
    });
    s.addText(
      "Understanding 預檢 / 過濾\n→ policy 節點\n→ execute 前 approval\n\n行為正確，裁決分散",
      {
        x: 0.7,
        y: 2.15,
        w: 4.0,
        h: 2.5,
        fontSize: 13,
        color: C.body,
        fontFace: "Arial",
        valign: "top",
      }
    );
    s.addText("合一後（Reference 目標）", {
      x: 5.3,
      y: 1.75,
      w: 4.0,
      h: 0.35,
      fontSize: 14,
      bold: true,
      color: C.ok,
      fontFace: "Arial",
    });
    s.addShape("rect", {
      x: 5.3,
      y: 2.15,
      w: 4.0,
      h: 2.5,
      fill: { color: C.okBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText(
      "Understanding → 只產出建議\nDecisionEngine.evaluate()\n  · 危險指令 / policy\n  · 人工核准\n→ 一個 DecisionResult\n→ 允許才 execute",
      {
        x: 5.5,
        y: 2.3,
        w: 3.6,
        h: 2.2,
        fontSize: 13,
        color: C.body,
        fontFace: "Arial",
        valign: "top",
      }
    );
    quoteBox(s, "不允許 → 說明原因 / 請人核准 — 已有；合一讓「誰說 no」只有一個答案。", 4.85);
  }

  // 6c Approval Gate — 主角是核准，不是 trigger 來源
  {
    const s = slide(pres);
    header(s, "Approval Gate", "Trusted Governance 的核心");
    const steps = [
      ["Decision", "requires_approval — 程式判定，非 LLM"],
      ["Pending", "保存待執行計畫 + fingerprint"],
      ["Provider", "Slack / AWX / ITSM / CLI …"],
      ["Approver", "治理通道 grant — 非對話 OK"],
      ["Resume", "接續 Execute → Audit 串鏈"],
    ];
    let y = 1.85;
    steps.forEach(([label, desc], i) => {
      s.addShape("rect", {
        x: 0.7,
        y,
        w: 1.45,
        h: 0.5,
        fill: { color: C.accent },
        line: { color: C.accent },
      });
      s.addText(label, {
        x: 0.7,
        y,
        w: 1.45,
        h: 0.5,
        fontSize: 11,
        bold: true,
        color: C.bg,
        align: "center",
        valign: "middle",
        fontFace: "Arial",
      });
      s.addText(desc, {
        x: 2.3,
        y: y + 0.06,
        w: 7.0,
        h: 0.38,
        fontSize: 14,
        color: C.body,
        fontFace: "Arial",
      });
      if (i < steps.length - 1) {
        s.addText("↓", {
          x: 1.25,
          y: y + 0.48,
          w: 0.3,
          h: 0.22,
          fontSize: 11,
          color: C.muted,
        });
      }
      y += 0.72;
    });
    s.addShape("rect", {
      x: 5.2,
      y: 1.85,
      w: 4.1,
      h: 2.9,
      fill: { color: C.okBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText(
      "三角色\n\nRequester — 觸發計畫\nApprover — 治理通道批核\nAgent — Pending + Resume\n\nTrigger ≠ Approval",
      {
        x: 5.4,
        y: 2.05,
        w: 3.7,
        h: 2.5,
        fontSize: 12,
        color: C.body,
        fontFace: "Arial",
        valign: "top",
      }
    );
    quoteBox(
      s,
      "Audit：decision → approval_requested → granted → executed — 可問責才敢上 Production。",
      5.05
    );
  }

  // 6d Reference 範例（trigger 之一，非主角）
  {
    const s = slide(pres);
    header(s, "Reference 範例", "Case Agent：工單留言只是 Trigger 之一");
    bullets(s, [
      "Requester：工單診斷請求（trigger 規則可配置）",
      "Decision：must-gather → requires_approval",
      "Approver：SRE 經 Slack / CLI 在治理通道 grant",
      "Agent：resume 執行 → grounded 結果回工單",
      "重點在 Approval + Audit，不在 Requester 說幾次話",
    ], { y: 1.85, fontSize: 15 });
    quoteBox(
      s,
      "Case 是協作介面；Approval 是治理介面 — 兩者分開。",
      4.85
    );
  }

  // 7 兩條路徑
  {
    const s = slide(pres);
    header(s, "同一 Case，兩種協作路徑", "由 LLM 依上下文選擇，不寫死場景");
    // Path A
    s.addShape("rect", {
      x: 0.7,
      y: 1.75,
      w: 4.0,
      h: 3.5,
      fill: { color: C.accentLight },
      line: { color: C.line, width: 0.5 },
    });
    s.addText("路徑 A — 需要證據", {
      x: 0.9,
      y: 1.95,
      w: 3.6,
      h: 0.4,
      fontSize: 16,
      bold: true,
      color: C.accent,
      fontFace: "Arial",
    });
    s.addText("call_mcp\n\n· Policy 放行後跑 MCP\n· 回覆附真實執行結果\n· Grounding 防偽造", {
      x: 0.9,
      y: 2.45,
      w: 3.6,
      h: 2.6,
      fontSize: 14,
      color: C.body,
      fontFace: "Arial",
      valign: "top",
    });
    // Path B
    s.addShape("rect", {
      x: 5.3,
      y: 1.75,
      w: 4.0,
      h: 3.5,
      fill: { color: C.okBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText("路徑 B — 需要對齊", {
      x: 5.5,
      y: 1.95,
      w: 3.6,
      h: 0.4,
      fontSize: 16,
      bold: true,
      color: C.ok,
      fontFace: "Arial",
    });
    s.addText(
      "reply_only\n\n· SE 給診斷或建議\n· 客戶視角協作回覆\n· 有理解、有行動，非「收到了」",
      {
        x: 5.5,
        y: 2.45,
        w: 3.6,
        h: 2.6,
        fontSize: 14,
        color: C.body,
        fontFace: "Arial",
        valign: "top",
      }
    );
  }

  // 8 價值主張
  {
    const s = slide(pres);
    header(s, "價值主張", "我們交付什麼？");
    const rows = [
      [
        { text: "價值", options: { bold: true, fill: { color: C.accentLight } } },
        { text: "對企業的意義", options: { bold: true, fill: { color: C.accentLight } } },
      ],
      ["治理可見", "被擋、需核准時，原因清楚可解釋"],
      ["回覆可稽核", "宣稱的結果對得上 MCP 輸出"],
      ["Human by Exception", "高風險必經 Approval Gate；Approver 在治理通道 grant"],
      ["可擴充", "換 Connector / Policy / MCP，不改核心"],
      ["受控協作", "縮短排查來回，而非追求自動結案"],
    ];
    s.addTable(rows, {
      x: 0.7,
      y: 1.75,
      w: 8.6,
      colW: [2.4, 6.2],
      fontSize: 14,
      color: C.body,
      border: { type: "solid", color: C.line, pt: 0.5 },
      align: "left",
      valign: "middle",
    });
  }

  // 9 不是什麼
  {
    const s = slide(pres);
    header(s, "我們刻意不做什麼", "Reference，不是綁場景的產品");
    bullets(s, [
      "不是「會解某一類 ticket」的垂直產品",
      "不是無邊界自主操作",
      "不是用 if-else 寫死每種故障流程",
      "不是取代 Support Engineer 或客戶 SRE",
    ], { y: 1.85 });
    s.addShape("rect", {
      x: 0.7,
      y: 4.0,
      w: 8.6,
      h: 1.5,
      fill: { color: C.accentLight },
      line: { color: C.line, width: 0.5 },
    });
    s.addText(
      "我們交付：模式 + 治理 + 一個能跑的 Connector 範例\nCase Portal 是範例；場景與政策由你們接上去",
      {
        x: 0.95,
        y: 4.2,
        w: 8.1,
        h: 1.1,
        fontSize: 15,
        color: C.accent,
        bold: true,
        fontFace: "Arial",
        valign: "middle",
      }
    );
  }

  // 10 擴充接點
  {
    const s = slide(pres);
    header(s, "擴充接點", "PoC 後由你們延伸");
    bullets(s, [
      "Connector — Jira、ServiceNow、Slack、Email",
      "Policy — enterprise profile、能力包、工具 allowlist",
      "MCP — 叢集、CMDB、自動化平台",
      "Prompts — 語氣與領域（不取代 policy）",
      "Webhook / Approval — 通知與人工核准",
    ], { y: 1.85, fontSize: 16 });
  }

  // 11 PoC 成功
  {
    const s = slide(pres);
    header(s, "PoC 怎麼算成功？", "");
    s.addShape("rect", {
      x: 0.7,
      y: 1.75,
      w: 4.0,
      h: 2.2,
      fill: { color: C.warnBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText("❌ 不是", {
      x: 0.9,
      y: 1.95,
      w: 3.6,
      h: 0.35,
      fontSize: 14,
      bold: true,
      color: C.warn,
      fontFace: "Arial",
    });
    s.addText("自動結案\n解完所有 ticket\n模型越自主越好", {
      x: 0.9,
      y: 2.35,
      w: 3.6,
      h: 1.4,
      fontSize: 14,
      color: C.body,
      fontFace: "Arial",
    });
    s.addShape("rect", {
      x: 5.3,
      y: 1.75,
      w: 4.0,
      h: 2.2,
      fill: { color: C.okBg },
      line: { color: C.line, width: 0.5 },
    });
    s.addText("✅ 是", {
      x: 5.5,
      y: 1.95,
      w: 3.6,
      h: 0.35,
      fontSize: 14,
      bold: true,
      color: C.ok,
      fontFace: "Arial",
    });
    s.addText(
      "團隊相信這套縱深防禦\n能安全接到你們的 workflow\n受控協作可縮短排查時間",
      {
        x: 5.5,
        y: 2.35,
        w: 3.6,
        h: 1.4,
        fontSize: 14,
        color: C.body,
        fontFace: "Arial",
      }
    );
    quoteBox(
      s,
      "Success is measured by whether an enterprise feels confident enough to adopt AI.",
      4.35
    );
  }

  // 12 收尾
  {
    const s = slide(pres);
    header(s, "下一步", "Milestone B");
    bullets(s, [
      "選 1 個進行中 Case → make dry-run 驗證",
      "展示 policy-dump、audit trail、grounding",
      "依你們場景接 Connector / Policy / MCP",
    ], { y: 1.85, fontSize: 17 });
    s.addText("Case Agent", {
      x: 0.7,
      y: 4.8,
      w: 8.6,
      h: 0.5,
      fontSize: 22,
      bold: true,
      color: C.title,
      fontFace: "Arial",
    });
    s.addText("LLM 理解 · 程式治理 · 可擴充 Reference", {
      x: 0.7,
      y: 5.3,
      w: 8.6,
      h: 0.35,
      fontSize: 13,
      color: C.muted,
      fontFace: "Arial",
    });
  }

  return pres.writeFile({ fileName: OUT });
}

createPresentation()
  .then(() => console.log(`Wrote ${OUT}`))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
