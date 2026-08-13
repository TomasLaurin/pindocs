/* The console.
 *
 * Deliberately dependency-free and unbundled: it is served by the app it
 * documents, so a build step would only stand between an edit and seeing it.
 *
 * Requests go straight from here to the app's own routes — same origin, so what
 * you are debugging is the real request, not a proxy's impression of one.
 */

const BASE = window.FASTAPI_DOCS.base;
const METHODS = ["get", "post", "put", "patch", "delete", "head", "options"];
const TOKEN_KEY = `fastapi-docs:token:${BASE}`;
const COLLAPSED_KEY = `fastapi-docs:collapsed:${BASE}`;

/* Tags open by default — a console that greets you with nothing but tag names
 * has hidden the only thing you came for. What you fold away is remembered. */
let COLLAPSED = new Set();
try {
  COLLAPSED = new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "[]"));
} catch {
  COLLAPSED = new Set();
}

let SPEC = null;
let STATE = { capture: true, pinned: {}, captured: {} };
let INDEX = [];
let CURRENT = null;

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) node.append(child);
  }
  return node;
}

/* ---------- schema ---------- */

function pointer(ref) {
  if (!ref || !ref.startsWith("#/")) return null;
  return ref
    .slice(2)
    .split("/")
    .reduce((node, part) => node?.[part.replace(/~1/g, "/").replace(/~0/g, "~")], SPEC);
}

function deref(node, seen = new Set()) {
  if (!node || typeof node !== "object") return node;
  if (!node.$ref) return node;
  if (seen.has(node.$ref)) return {};
  const target = pointer(node.$ref);
  return target ? deref(target, new Set([...seen, node.$ref])) : {};
}

function stringSample(schema) {
  switch (schema.format) {
    case "date-time":
      return new Date().toISOString();
    case "date":
      return new Date().toISOString().slice(0, 10);
    case "uuid":
      return "00000000-0000-0000-0000-000000000000";
    case "email":
      return "user@example.com";
    case "uri":
    case "url":
      return "https://example.com";
    default:
      return "";
  }
}

/* A body worth editing rather than typing from scratch. Known variables win over
 * the schema's own suggestion — a body field called project_id should arrive
 * holding the project you are actually working in. */
function sample(schema, name = "", depth = 0, seen = new Set()) {
  schema = deref(schema, seen);
  if (!schema || typeof schema !== "object" || depth > 6) return null;

  const known = lookup(name);
  if (known && ["string", "integer", "number", undefined].includes(schema.type)) {
    return schema.type === "integer" || schema.type === "number" ? Number(known) || known : known;
  }
  if (schema.example !== undefined) return schema.example;
  if (schema.default !== undefined) return schema.default;
  if (Array.isArray(schema.enum) && schema.enum.length) return schema.enum[0];

  if (Array.isArray(schema.allOf)) {
    return Object.assign({}, ...schema.allOf.map((part) => sample(part, name, depth + 1, seen) ?? {}));
  }
  const union = schema.anyOf || schema.oneOf;
  if (Array.isArray(union) && union.length) {
    const branch = union.find((part) => deref(part, seen)?.type !== "null") ?? union[0];
    return sample(branch, name, depth + 1, seen);
  }

  const type = Array.isArray(schema.type) ? schema.type.find((t) => t !== "null") : schema.type;
  if (type === "array") return [sample(schema.items, name, depth + 1, seen)].filter((v) => v !== null);
  if (type === "integer" || type === "number") return 0;
  if (type === "boolean") return false;
  if (type === "string") return stringSample(schema);

  if (type === "object" || schema.properties) {
    const body = {};
    for (const [key, property] of Object.entries(schema.properties || {})) {
      const value = sample(property, key, depth + 1, seen);
      if (value !== null) body[key] = value;
    }
    return body;
  }
  return null;
}

/* ---------- index ---------- */

function buildIndex() {
  const byTag = new Map();

  for (const [path, operations] of Object.entries(SPEC.paths || {})) {
    const shared = operations.parameters || [];
    for (const method of METHODS) {
      const operation = operations[method];
      if (!operation) continue;

      const entry = {
        id: `${method.toUpperCase()} ${path}`,
        method: method.toUpperCase(),
        path,
        summary: operation.summary || "",
        description: operation.description || "",
        parameters: [...shared, ...(operation.parameters || [])].map((p) => deref(p)),
        body: bodySchema(operation),
        tags: operation.tags?.length ? operation.tags : ["untagged"],
      };

      for (const tag of entry.tags) {
        if (!byTag.has(tag)) byTag.set(tag, []);
        byTag.get(tag).push(entry);
      }
    }
  }

  const described = new Map((SPEC.tags || []).map((tag) => [tag.name, tag.description || ""]));
  const declared = SPEC["x-tagGroups"]?.length ? SPEC["x-tagGroups"] : [{ name: "API", tags: [...byTag.keys()] }];

  /* The same guarantee the server makes, made again here — because it is a
   * different set. An operation carrying no tag at all never reached the
   * server's grouping, so it arrives holding the synthetic tag below, which no
   * declared group claims. Health probes are the usual case, and a console that
   * hid them would be repeating the trick this library exists to avoid. */
  const claimed = new Set(declared.flatMap((group) => group.tags || []));
  const orphans = [...byTag.keys()].filter((tag) => !claimed.has(tag));
  const groups = orphans.length ? [...declared, { name: "Other", tags: orphans }] : declared;

  return groups
    .map((group) => ({
      name: group.name,
      tags: (group.tags || [])
        .filter((tag) => byTag.has(tag))
        .map((tag) => ({ name: tag, description: described.get(tag) || "", operations: byTag.get(tag) })),
    }))
    .filter((group) => group.tags.length);
}

function bodySchema(operation) {
  const content = deref(operation.requestBody)?.content;
  if (!content) return null;
  const type = Object.keys(content).find((key) => key.includes("json")) || Object.keys(content)[0];
  return type ? { mediaType: type, schema: content[type].schema } : null;
}

/* ---------- values ---------- */

function lookup(name) {
  if (!name) return undefined;
  if (STATE.pinned[name] !== undefined) return STATE.pinned[name];
  return STATE.captured[name]?.value;
}

function resolve(name, schema = {}) {
  if (STATE.pinned[name] !== undefined) return { value: STATE.pinned[name], source: "pinned" };
  if (STATE.captured[name] !== undefined) return { value: STATE.captured[name].value, source: "captured" };
  const resolved = deref(schema) || {};
  for (const key of ["default", "example"]) {
    if (resolved[key] !== undefined) return { value: String(resolved[key]), source: "schema" };
  }
  if (Array.isArray(resolved.enum) && resolved.enum.length) return { value: String(resolved.enum[0]), source: "schema" };
  return { value: "", source: "" };
}

async function saveState(next) {
  const response = await fetch(`${BASE}/state`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(next),
  });
  STATE = await response.json();
  renderVariables();
  if (CURRENT) renderOperation(CURRENT);
}

/* ---------- sidebar ---------- */

function renderNav(filter = "") {
  const nav = $("#nav");
  nav.replaceChildren();
  const needle = filter.trim().toLowerCase();

  for (const group of INDEX) {
    const tags = group.tags
      .map((tag) => ({
        ...tag,
        operations: tag.operations.filter(
          (op) =>
            !needle ||
            op.path.toLowerCase().includes(needle) ||
            op.summary.toLowerCase().includes(needle) ||
            op.method.toLowerCase().includes(needle) ||
            tag.name.toLowerCase().includes(needle),
        ),
      }))
      .filter((tag) => tag.operations.length);

    if (!tags.length) continue;

    const holding = tags.some((tag) => tag.operations.includes(CURRENT));
    const section = fold("group", `group:${group.name}`, needle || holding);
    section.append(el("summary", { class: "group-name", text: group.name }));
    nav.append(section);

    for (const tag of tags) {
      const details = fold("tag", `tag:${tag.name}`, needle || tag.operations.includes(CURRENT));
      details.append(el("summary", { text: tag.name, title: tag.description }));
      for (const op of tag.operations) {
        details.append(
          el(
            "button",
            {
              class: "op",
              type: "button",
              title: op.summary || op.path,
              "aria-current": op === CURRENT ? "true" : "false",
              onclick: () => select(op),
            },
            el("span", { class: `method method-${op.method.toLowerCase()}`, text: op.method }),
            el("span", { class: "path", text: op.path }),
          ),
        );
      }
      section.append(details);
    }
  }
}

/* A `details` that remembers whether you folded it. `forced` wins for the two
 * cases where hiding would be wrong however you left it: a filter is narrowing
 * the list, or the operation on screen lives inside. */
function fold(className, key, forced) {
  const folded = COLLAPSED.has(key) && !forced;
  const node = el("details", { class: className, ...(folded ? {} : { open: "" }) });

  // `toggle` does not bubble, so a tag folding inside a group does not read as
  // the group folding.
  node.addEventListener("toggle", () => {
    if (node.open) COLLAPSED.delete(key);
    else COLLAPSED.add(key);
    localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...COLLAPSED]));
  });
  return node;
}

function select(op) {
  CURRENT = op;
  location.hash = encodeURIComponent(op.id);
  renderNav($("#filter").value);
  renderOperation(op);
}

/* ---------- operation ---------- */

function renderOperation(op) {
  const root = $("#operation");
  root.replaceChildren();

  root.append(
    el(
      "div",
      { class: "op-head" },
      el("span", { class: `method method-${op.method.toLowerCase()}`, text: op.method }),
      el("span", { class: "url", text: op.path }),
    ),
  );
  if (op.summary) root.append(el("p", { class: "op-summary", text: op.summary }));
  if (op.description) root.append(el("p", { class: "op-description", text: op.description }));

  const inputs = new Map();
  const relevant = op.parameters.filter((p) => ["path", "query", "header"].includes(p.in));

  if (relevant.length) {
    root.append(el("h3", { text: "Parameters" }));
    for (const parameter of relevant) {
      const { value, source } = resolve(parameter.name, parameter.schema);
      const input = el("input", { type: "text", value, placeholder: describeType(parameter.schema) });
      inputs.set(parameter, input);
      root.append(
        el(
          "div",
          { class: "field" },
          el(
            "label",
            {},
            parameter.name,
            parameter.required ? el("span", { class: "req", text: " *" }) : null,
            el("span", { class: "where", text: parameter.in }),
          ),
          el("div", {}, input, el("span", { class: `source source-${source}`, text: sourceLabel(source, parameter.name) })),
        ),
      );
    }
  }

  let bodyEditor = null;
  if (op.body) {
    root.append(el("h3", { text: `Body — ${op.body.mediaType}` }));
    const skeleton = sample(op.body.schema);
    bodyEditor = el("textarea", { spellcheck: "false" });
    bodyEditor.value = skeleton === null ? "" : JSON.stringify(skeleton, null, 2);
    root.append(bodyEditor);
  }

  const button = el("button", { class: "primary", type: "button", text: "Send" });
  const timing = el("span", { class: "hint" });
  const actions = el("div", { class: "actions" }, button, timing);
  root.append(actions);

  const responseSlot = el("div");
  root.append(responseSlot);

  const fire = () => send(op, inputs, bodyEditor, button, timing, responseSlot);
  button.addEventListener("click", fire);
  root.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") fire();
  });
}

function describeType(schema) {
  const resolved = deref(schema) || {};
  const type = Array.isArray(resolved.type) ? resolved.type.filter((t) => t !== "null").join("|") : resolved.type;
  return [type || "string", resolved.format].filter(Boolean).join(" · ");
}

function sourceLabel(source, name) {
  if (source === "pinned") return `pinned ${name}`;
  if (source === "captured") return `captured from ${STATE.captured[name]?.source || "a response"}`;
  return "";
}

/* ---------- sending ---------- */

function buildUrl(op, inputs) {
  let path = op.path;
  const query = new URLSearchParams();

  for (const [parameter, input] of inputs) {
    const value = input.value.trim();
    if (parameter.in === "path") {
      path = path.replace(`{${parameter.name}}`, encodeURIComponent(value));
    } else if (parameter.in === "query" && value !== "") {
      query.append(parameter.name, value);
    }
  }
  const search = query.toString();
  return path + (search ? `?${search}` : "");
}

async function send(op, inputs, bodyEditor, button, timing, slot) {
  const url = buildUrl(op, inputs);
  const headers = {};
  for (const [parameter, input] of inputs) {
    if (parameter.in === "header" && input.value.trim()) headers[parameter.name] = input.value.trim();
  }

  const token = $("#token").value.trim();
  if (token) headers.authorization = token.includes(" ") ? token : `Bearer ${token}`;

  let body;
  if (bodyEditor && bodyEditor.value.trim()) {
    headers["content-type"] = op.body.mediaType;
    body = bodyEditor.value;
    if (op.body.mediaType.includes("json")) {
      try {
        JSON.parse(body);
      } catch (error) {
        slot.replaceChildren(renderFailure(`Request body is not valid JSON — ${error.message}`));
        return;
      }
    }
  }

  button.disabled = true;
  timing.textContent = "sending…";
  const started = performance.now();

  try {
    const response = await fetch(url, { method: op.method, headers, body });
    const elapsed = Math.round(performance.now() - started);
    const text = await response.text();
    let parsed = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }

    timing.textContent = `${elapsed} ms · ${formatBytes(text.length)}`;
    const captured = parsed !== null ? await capture(op, parsed) : [];
    slot.replaceChildren(renderResponse(response, text, parsed, elapsed, captured));
  } catch (error) {
    timing.textContent = "";
    slot.replaceChildren(renderFailure(`${error}`));
  } finally {
    button.disabled = false;
  }
}

async function capture(op, parsed) {
  if (!STATE.capture) return [];
  const before = { ...STATE.captured };
  const response = await fetch(`${BASE}/capture`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ operation: op.id, path: op.path, body: parsed }),
  });
  STATE = await response.json();
  renderVariables();

  return Object.entries(STATE.captured)
    .filter(([name, entry]) => before[name]?.value !== entry.value)
    .map(([name, entry]) => `${name} = ${entry.value}`);
}

function renderResponse(response, text, parsed, elapsed, captured) {
  const ok = response.ok;
  const node = el(
    "div",
    { class: "response" },
    el(
      "div",
      { class: "response-head" },
      el("span", { class: ok ? "status-ok" : "status-bad", text: `${response.status} ${response.statusText}` }),
      el("span", { text: `${elapsed} ms` }),
      el("span", { text: formatBytes(text.length) }),
    ),
    el("pre", { text: parsed !== null ? JSON.stringify(parsed, null, 2) : text || "(empty body)" }),
  );
  if (captured.length) {
    node.append(el("div", { class: "captured-note", text: `captured  ${captured.join("   ·   ")}` }));
  }
  return node;
}

function renderFailure(message) {
  return el(
    "div",
    { class: "response" },
    el("div", { class: "response-head" }, el("span", { class: "status-bad", text: "failed" })),
    el("pre", { text: message }),
  );
}

function formatBytes(count) {
  return count < 1024 ? `${count} B` : `${(count / 1024).toFixed(1)} kB`;
}

/* ---------- variables rail ---------- */

function renderVariables() {
  const root = $("#variables");
  root.replaceChildren();
  $("#capture").checked = STATE.capture;

  const pinned = Object.entries(STATE.pinned);
  const captured = Object.entries(STATE.captured).filter(([name]) => STATE.pinned[name] === undefined);

  if (!pinned.length && !captured.length) {
    root.append(el("p", { class: "empty-note", text: "Nothing yet. Send a request, or pin a value below." }));
    return;
  }

  for (const [name, value] of pinned) {
    root.append(variableRow(name, value, "pinned", null));
  }
  for (const [name, entry] of captured) {
    root.append(variableRow(name, entry.value, "captured", entry.source));
  }
}

function variableRow(name, value, kind, origin) {
  const input = el("input", { class: "value", type: "text", value });

  input.addEventListener("change", () => {
    const next = { ...STATE, pinned: { ...STATE.pinned, [name]: input.value } };
    saveState(next);
  });

  const action =
    kind === "pinned"
      ? el("button", {
          class: "pin",
          type: "button",
          text: "unpin",
          title: "Stop overriding this name",
          onclick: () => {
            const pinnedNext = { ...STATE.pinned };
            delete pinnedNext[name];
            saveState({ ...STATE, pinned: pinnedNext });
          },
        })
      : el("button", {
          class: "pin",
          type: "button",
          text: "pin",
          title: "Keep this value — responses will stop overwriting it",
          onclick: () => saveState({ ...STATE, pinned: { ...STATE.pinned, [name]: value } }),
        });

  return el(
    "div",
    { class: "variable" },
    el("span", { class: "name", text: name, title: name }),
    action,
    input,
    origin ? el("span", { class: "meta", text: origin, title: origin }) : null,
  );
}

/* ---------- boot ---------- */

function restore() {
  const wanted = decodeURIComponent(location.hash.slice(1));
  const all = INDEX.flatMap((group) => group.tags.flatMap((tag) => tag.operations));
  const op = all.find((candidate) => candidate.id === wanted);
  if (op) {
    CURRENT = op;
    renderOperation(op);
  }
}

async function boot() {
  const [spec, state] = await Promise.all([
    fetch(`${BASE}/spec`).then((response) => response.json()),
    fetch(`${BASE}/state`).then((response) => response.json()),
  ]);
  SPEC = spec;
  STATE = state;
  INDEX = buildIndex();

  $("#token").value = localStorage.getItem(TOKEN_KEY) || "";
  $("#token").addEventListener("change", (event) => localStorage.setItem(TOKEN_KEY, event.target.value));
  $("#filter").addEventListener("input", (event) => renderNav(event.target.value));
  $("#capture").addEventListener("change", (event) => saveState({ ...STATE, capture: event.target.checked }));
  $("#clear-captured").addEventListener("click", () => saveState({ ...STATE, captured: {} }));
  $("#add-variable").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const name = String(form.get("name")).trim();
    if (name) saveState({ ...STATE, pinned: { ...STATE.pinned, [name]: String(form.get("value")) } });
    event.target.reset();
  });

  restore();
  renderNav();
  renderVariables();
}

boot();
