for (const button of document.querySelectorAll("[data-reveal]")) {
  button.addEventListener("click", () => {
    const target = document.getElementById(button.dataset.reveal);
    if (!target) return;
    target.classList.toggle("is-hidden");
    button.textContent = target.classList.contains("is-hidden")
      ? button.textContent.replace("收起", "展开").replace("隐藏", "看")
      : button.textContent.replace("展开", "收起").replace("看", "隐藏");
  });
}

const toolSteps = {
  prepare: {
    text:
      "第一步是确认 Daikon 可运行。Daikon 本体是 Java 工具；Python 项目需要先把运行时值转换成 Daikon 的轨迹格式。",
    code: `java -version
ls /tmp/daikon-5.8.24/daikon.jar

expected:
  daikon.jar exists`,
  },
  trace: {
    text:
      "第二步是跑真实 workload。这里用 SWE-Perf 官方性能测试触发 Astropy，再记录目标函数入口和出口的值。",
    code: `python .../real_trace_astropy_16058.py \\
  --daikon-jar /tmp/daikon-5.8.24/daikon.jar

output:
  runtime_trace.jsonl`,
  },
  mine: {
    text:
      "第三步是把轨迹转成 Daikon 文件，然后调用 Daikon 挖运行时关系。脚本内部会生成 .decls 和 .dtrace，并运行 daikon.Daikon。",
    code: `generated:
  real_trace.decls
  real_trace.dtrace

internal command:
  java -cp daikon.jar daikon.Daikon real_trace.decls real_trace.dtrace

output:
  daikon_output.txt
  invariant_context.json`,
  },
  package: {
    text:
      "第四步是筛选和压缩。原始 Daikon 输出很多，真正给 Codex 的只保留和目标函数、候选优化有关的几条证据。",
    code: `python codex-skills/daikon-invariant-mining/scripts/invariant_tool.py \\
  --context .../astropy__astropy-16058.real-daikon.json \\
  --target validate_power \\
  --limit 12

agent evidence:
  if p is int, validate_power(p) returns p unchanged
  preserve fallback path`,
  },
};

document.addEventListener("click", (event) => {
  const button = event.target.closest(".tool-step");
  if (!button) return;
  const toolStepText = document.querySelector("#tool-step-text");
  const toolStepCode = document.querySelector("#tool-step-code code");
  const item = toolSteps[button.dataset.toolStep];
  if (!item || !toolStepText || !toolStepCode) return;
  for (const other of document.querySelectorAll(".tool-step")) {
    other.classList.toggle("is-active", other === button);
  }
  toolStepText.textContent = item.text;
  toolStepCode.textContent = item.code;
});

const sweperfParts = {
  input: {
    kicker: "Task input",
    title: "Agent 看到的是一个真实仓库任务",
    text:
      "对 astropy__astropy-16058，任务输入包含仓库、性能优化描述、可能相关的目标函数和官方性能测试。Agent 不会直接拿到“正确补丁”。",
    code: `{
  "repo": "astropy/astropy",
  "instance_id": "astropy__astropy-16058",
  "target_functions": [
    "CompositeUnit.__init__",
    "validate_power",
    "maybe_simple_fraction"
  ]
}`,
  },
  patch: {
    kicker: "Agent output",
    title: "Agent 要交的是 patch，不是文字解释",
    text:
      "SWE-Perf 会把 agent 生成的代码修改真正应用到仓库里。也就是说，agent 的输出必须能落到真实代码上，而不是只给一个优化建议。",
    code: `diff --git a/astropy/units/utils.py b/astropy/units/utils.py

def validate_power(p):
    if p.__class__ is int:
        return p
    ...

def sanitize_power(p):
    return maybe_simple_fraction(p)`,
  },
  eval: {
    kicker: "Official evaluation",
    title: "官方评估同时看正确性和性能",
    text:
      "一个 patch 先要能 apply，再通过正确性测试，最后才比较性能测试耗时。性能变快但测试失败，不能算成功。",
    code: `Evaluation checklist:
  1. patch applies
  2. correctness tests pass
  3. performance test improves

Example:
  0.01084s -> 0.01001s
  relative improvement: 7.67%`,
  },
  bridge: {
    kicker: "Why Daikon",
    title: "SWE-Perf 只告诉我们快不快，不解释为什么安全",
    text:
      "这就是 Daikon 介入的位置：它从运行轨迹里挖出输入/输出关系，帮助 agent 看到“哪些路径可能可以更便宜”，同时提醒它保留兜底逻辑。",
    code: `Daikon evidence:
  arg0_is_int <= result_is_same_as_arg0

Agent hint:
  if input is a simple int, consider returning it directly
  otherwise keep the original slow path`,
  },
};

document.addEventListener("click", (event) => {
  const button = event.target.closest(".explorer-tab");
  if (!button) return;
  const item = sweperfParts[button.dataset.sweperfPart];
  if (!item) return;

  for (const other of document.querySelectorAll(".explorer-tab")) {
    other.classList.toggle("is-active", other === button);
  }

  document.querySelector("#sweperf-panel-kicker").textContent = item.kicker;
  document.querySelector("#sweperf-panel-title").textContent = item.title;
  document.querySelector("#sweperf-panel-text").textContent = item.text;
  document.querySelector("#sweperf-panel-code code").textContent = item.code;
});

const daikonButton = document.querySelector("#run-daikon");
const daikonResult = document.querySelector("#daikon-result");

if (daikonButton && daikonResult) {
  daikonButton.addEventListener("click", async () => {
    daikonButton.disabled = true;
    daikonButton.textContent = "运行中...";
    daikonResult.className = "daikon-result is-loading";
    daikonResult.innerHTML = `
      <p>正在调用本地 Daikon skill 工具...</p>
      <div class="loading-bar"><span></span></div>
    `;

    try {
      const response = await fetch("/api/daikon");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Daikon tool failed");
      }
      const parsed = parseDaikonOutput(payload.stdout);
      daikonResult.className = "daikon-result is-ready";
      daikonResult.innerHTML = `
        <div class="result-kv">
          <span>Coverage</span>
          <strong>${escapeHtml(parsed.coverage)}</strong>
        </div>
        <ul>
          ${parsed.invariants.map((item) => `<li><code>${escapeHtml(item)}</code></li>`).join("")}
        </ul>
        <p>${escapeHtml(parsed.implication)}</p>
        <details>
          <summary>查看工具原始输出</summary>
          <pre><code>${escapeHtml(payload.stdout)}</code></pre>
        </details>
      `;
      daikonButton.textContent = "重新运行";
      daikonButton.disabled = false;
    } catch (error) {
      daikonResult.className = "daikon-result is-error";
      daikonResult.innerHTML = `
        <p>运行失败：${escapeHtml(error.message)}</p>
        <p>请用 <code>python demo_server.py</code> 启动本地后端后再打开网页。</p>
      `;
      daikonButton.textContent = "重新运行";
      daikonButton.disabled = false;
    }
  });
}

function parseDaikonOutput(text) {
  const coverage = text.match(/Coverage:\s*(.+)/)?.[1] || "not reported";
  const invariantLines = text
    .split("\n")
    .filter((line) => line.startsWith("- astropy.units.utils.validate_power"))
    .slice(0, 2)
    .map((line) => line.replace(/^- .*?:\s*/, "").replace(/\s+\[score=.*$/, ""));
  const implication =
    text.match(/Optimization implications:\n- (.+)/)?.[1] ||
    "工具返回了运行时语义证据；需要 agent 判断它是否支持带兜底路径的优化。";
  return {
    coverage,
    invariants: invariantLines.length ? invariantLines : ["No runtime evidence extracted"],
    implication,
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const powerCases = {
  int: {
    old: ["检查是否合法", "尝试转换成标准表示", "返回结果"],
    next: ["判断它是简单整数", "直接返回输入"],
    oldCost: 68,
    newCost: 22,
    oldLabel: "medium",
    newLabel: "low",
    summary:
      "对整数输入，Daikon 证据支持“直接返回输入”。原逻辑也正确，但做了更多检查。",
  },
  float: {
    old: ["检查是否合法", "尝试转成更标准的分数", "返回转换后的值"],
    next: ["确认它是合法数字", "先返回输入", "以后真的需要时再转换"],
    oldCost: 92,
    newCost: 46,
    oldLabel: "high",
    newLabel: "medium",
    summary:
      "对小数输入，新版本不急着转换成标准表示。只有后面真的需要时才做转换。",
  },
  fraction: {
    old: ["检查是否合法", "可能继续转换表示", "返回结果"],
    next: ["判断它已经是分数", "直接返回输入", "以后需要时再处理"],
    oldCost: 74,
    newCost: 28,
    oldLabel: "medium",
    newLabel: "low",
    summary:
      "分数本身已经表达了精确值。检查阶段不一定要立即改写它。",
  },
  array: {
    old: ["检查是不是合法输入", "确认里面的值是否一致", "取出结果或报错"],
    next: ["仍然做完整检查", "保留原来的兜底行为"],
    oldCost: 82,
    newCost: 78,
    oldLabel: "high",
    newLabel: "high",
    summary:
      "这个输入说明不能盲目走快路径。遇到复杂输入时，仍然要保留原来的检查和错误处理。",
  },
};

const oldPath = document.querySelector("#old-path");
const newPath = document.querySelector("#new-path");
const oldMeter = document.querySelector("#old-meter");
const newMeter = document.querySelector("#new-meter");
const oldCost = document.querySelector("#old-cost");
const newCost = document.querySelector("#new-cost");
const playSummary = document.querySelector("#play-summary");

function renderPowerCase(key) {
  const item = powerCases[key];
  if (!item || !oldPath || !newPath) return;

  oldPath.innerHTML = item.old.map((step) => `<li>${step}</li>`).join("");
  newPath.innerHTML = item.next.map((step) => `<li>${step}</li>`).join("");
  oldMeter.style.width = `${item.oldCost}%`;
  newMeter.style.width = `${item.newCost}%`;
  oldCost.textContent = item.oldLabel;
  newCost.textContent = item.newLabel;
  playSummary.textContent = item.summary;

  for (const button of document.querySelectorAll(".power-button")) {
    button.classList.toggle("is-active", button.dataset.power === key);
  }
}

for (const button of document.querySelectorAll(".power-button")) {
  button.addEventListener("click", () => renderPowerCase(button.dataset.power));
}

renderPowerCase("int");
