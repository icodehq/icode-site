// Plays back an illustrative coding session, step by step. The steps mirror the
// real tool loop (read -> bash -> edit -> bash); it is a teaching animation, not
// a recorded run, and carries no invented metrics.
(() => {
  const root = document.querySelector("[data-demo]");
  if (!root) return;

  let t = {};
  try {
    const data = document.getElementById("demo-i18n");
    t = data ? JSON.parse(data.textContent) : {};
  } catch {
    t = {};
  }

  const STEPS = [
    { kind: "prompt", text: t.prompt || "Fix the failing tests in this repository." },
    { kind: "tool", name: "read", text: "src/math.ts" },
    { kind: "ok", name: "read", note: t.noteRead || "read 42 lines" },
    { kind: "tool", name: "bash", text: "bun test math.test.ts" },
    { kind: "fail", name: "bash", note: t.noteFail || "observes the failure" },
    { kind: "tool", name: "edit", text: "src/math.ts" },
    { kind: "ok", name: "edit", note: t.noteEdit || "repairs the code" },
    { kind: "tool", name: "bash", text: "bun test math.test.ts" },
    { kind: "ok", name: "bash", note: t.notePass || "verifies: all tests pass" },
    { kind: "answer", text: t.answer || "Fixed add() — it summed the wrong operands. All tests pass." },
  ];

  const screen = root.querySelector("[data-demo-screen]");
  const replay = root.querySelector("[data-demo-replay]");
  const title = root.querySelector("[data-demo-title]");
  if (title && t.title) title.textContent = t.title;
  if (replay && t.replay) replay.textContent = t.replay;
  let timer = null;

  const line = (step) => {
    const el = document.createElement("div");
    el.className = "term-line";
    if (step.kind === "prompt") {
      el.classList.add("term-prompt");
      el.textContent = (t.you || "You:") + "  " + step.text;
    } else if (step.kind === "answer") {
      el.classList.add("term-answer");
      el.textContent = "  " + step.text;
    } else if (step.kind === "tool") {
      el.classList.add("term-tool");
      el.textContent = `  ▸ ${step.name} ${step.text}`;
    } else {
      el.classList.add(step.kind === "fail" ? "term-fail" : "term-ok");
      const mark = step.kind === "fail" ? "×" : "✓";
      el.textContent = `  ${mark} ${step.name}${step.note ? "      ← " + step.note : ""}`;
    }
    return el;
  };

  const play = () => {
    if (timer) clearInterval(timer);
    screen.textContent = "";
    let i = 0;
    const tick = () => {
      if (i >= STEPS.length) {
        clearInterval(timer);
        timer = null;
        return;
      }
      screen.appendChild(line(STEPS[i++]));
      screen.scrollTop = screen.scrollHeight;
    };
    tick();
    timer = setInterval(tick, 650);
  };

  if (replay) replay.addEventListener("click", play);
  play();
})();
