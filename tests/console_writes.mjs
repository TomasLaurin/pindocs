/* Drives the console's variables rail outside a browser.
 *
 * The rail is the one piece of pindocs that is not Python, and the thing worth
 * pinning down about it — that two saves in flight together do not lose one —
 * only shows up in timing. So console.js is loaded into a bare V8 context with
 * two stand-ins: enough DOM for a row to be rendered and a button clicked, and
 * an app that answers `PUT /state` the way `StateStore.save` does, whole
 * document in and whole document back, after a delay long enough that the
 * clicks below all land while the first write is still on the wire.
 *
 * Nothing here is a browser. What is stubbed is only what the rail touches on
 * the way from a click to a request. The document the stand-in app is left
 * holding is printed as JSON; tests/test_console.py does the asserting.
 */

import { readFileSync } from "node:fs";
import { createContext, runInContext } from "node:vm";

const SOURCE = new URL("../src/pindocs/static/console.js", import.meta.url);
const LATENCY = 20; // ms on the wire, each way

/* ---------- the app ---------- */

let stored = { version: 1, capture: true, pinned: {}, captured: {} };
let inflight = 0;

function fetchStub(url, options = {}) {
  /* Only writes are answered. `boot()` opens with GET /spec and GET /state, so
   * leaving those hanging parks it at its first await: it never reaches the
   * DOM, and the rail is driven directly instead. */
  if (options.method !== "PUT") return new Promise(() => {});

  const sent = JSON.parse(options.body);
  inflight += 1;
  return new Promise((resolve) => {
    setTimeout(() => {
      // Written whole, and what comes back is what was written.
      stored = {
        version: 1,
        capture: Boolean(sent.capture),
        pinned: { ...sent.pinned },
        captured: { ...sent.captured },
      };
      inflight -= 1;
      resolve({ ok: true, json: async () => structuredClone(stored) });
    }, LATENCY);
  });
}

/* ---------- the page ---------- */

const NODES = new Map();

function element(tag = "div") {
  const node = {
    tag,
    children: [],
    listeners: new Map(),
    className: "",
    textContent: "",
    checked: false,
    addEventListener: (type, handler) => node.listeners.set(type, handler),
    setAttribute: (name, value) => {
      node[name] = value;
    },
    append: (...kids) => node.children.push(...kids),
    replaceChildren: (...kids) => {
      node.children = kids;
    },
  };
  return node;
}

/* One node per selector, so `#variables` is the same element every re-render. */
const documentStub = {
  querySelector: (selector) => {
    if (!NODES.has(selector)) NODES.set(selector, element(selector));
    return NODES.get(selector);
  },
  createElement: element,
};

const context = createContext({
  window: { PINDOCS: { base: "/pindocs" } },
  localStorage: { getItem: () => null, setItem: () => {} },
  document: documentStub,
  fetch: fetchStub,
  console,
});
runInContext(readFileSync(SOURCE, "utf8"), context, { filename: "console.js" });

/* ---------- clicking ---------- */

function* descendants(node) {
  for (const child of node.children ?? []) {
    yield child;
    yield* descendants(child);
  }
}

const rows = () => documentStub.querySelector("#variables").children;

/* Press the button labelled `label` on the row for `name`, the way a pointer
 * would. A missing one means the rail is not showing what was written, which
 * is the failure this file exists to catch — so say so rather than throwing a
 * property access at whoever is reading the output. */
function click(name, label) {
  const row = rows().find((node) => [...descendants(node)].some((n) => n.className === "name" && n.textContent === name));
  const button = row && [...descendants(row)].find((n) => n.textContent === label && n.listeners.has("click"));
  if (!button) throw new Error(`the rail has no ${label} button for ${name}: [${rows().map((r) => r.children[0].textContent)}]`);
  button.listeners.get("click")();
}

/* Idle is nothing in flight and nothing that puts something back in flight on
 * the turns after — true whether the writes were queued or all sent at once. */
async function settle() {
  for (let quiet = 0; quiet < 5; ) {
    await new Promise((resolve) => setTimeout(resolve, LATENCY));
    quiet = inflight === 0 ? quiet + 1 : 0;
  }
}

/* ---------- what a hurried person does ---------- */

const NAMES = ["run_id", "workspace_id", "model_id", "dataset_id", "job_id"];

// Five responses' worth of captured values, so the rail has five rows to pin.
const seeded = Object.fromEntries(NAMES.map((name, index) => [name, { value: `v_${index}`, source: "seed", at: "" }]));
await context.saveState((state) => ({ ...state, captured: seeded }));

// Every Pin button, hit before the first of them has been answered.
for (const name of NAMES) click(name, "pin");
await settle();
const afterPinning = stored;

// And the other direction: two rows dropped in the same breath.
for (const name of ["workspace_id", "dataset_id"]) click(name, "unpin");
await settle();
const afterUnpinning = stored;

console.log(JSON.stringify({ afterPinning, afterUnpinning }, null, 2));
