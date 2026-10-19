// The administration page: a client of the API under /v1 (see docs/admin-page.md).
"use strict";

const PAGE = 50;
const filters = document.getElementById("filters");
const projects = new Set();
let offset = 0;

function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(name, value);
  }
  node.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
  return node;
}

// A key holds `/` between its segments, which the routes take as part of the path.
function entryUrl(entry) {
  const key = entry.key.split("/").map(encodeURIComponent).join("/");
  return `/v1/projects/${encodeURIComponent(entry.project)}/entries/${key}`;
}

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.detail;
    throw new Error(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
  }
  return body;
}

const LOCAL = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function time(iso) {
  return iso ? h("time", { datetime: iso, title: `${iso} (UTC)` }, LOCAL.format(new Date(iso))) : "";
}

function until(iso) {
  const minutes = Math.round((new Date(iso) - Date.now()) / 60000);
  if (minutes < 0) return "passed";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return days ? `in ${days} d ${hours} h` : `in ${hours} h ${minutes % 60} min`;
}

function showError(message) {
  const node = document.getElementById("error");
  node.textContent = message || "";
  node.hidden = !message;
}

function badge(status) {
  return h("span", { class: `badge ${status}` }, status.replace("_", " "));
}

function postView(post) {
  return h("div", { class: "post" },
    h("div", { class: "post-line" },
      h("span", { class: "platform" }, post.platform),
      badge(post.status),
      h("span", { class: "muted" }, post.account),
      post.remote_id && h("span", { class: "muted" }, post.remote_id),
      post.failures > 0 && h("span", { class: "muted" }, `${post.failures} failure(s)`),
    ),
    post.error && h("div", { class: "error" }, post.error),
    h("details", {},
      h("summary", {}, `History, updated `, time(post.updated_at)),
      h("ol", {}, post.events.map((event) =>
        h("li", {}, time(event.at), " ", badge(event.status), event.error ? ` ${event.error}` : ""))),
    ),
  );
}

function entryView(entry) {
  return h("div", { class: "card" },
    h("div", { class: "entry-head" },
      h("span", { class: "entry-name" }, `${entry.project} / ${entry.key}`),
      h("span", {}, time(entry.publish_at)),
    ),
    h("div", { class: "muted" },
      "Submitted ", time(entry.submitted_at),
      entry.updated_at !== entry.submitted_at ? [", updated ", time(entry.updated_at)] : "",
      entry.video_released_at ? [", video released ", time(entry.video_released_at)] : ", video held",
    ),
    h("div", { class: "posts" }, entry.posts.map(postView)),
  );
}

// navigator.clipboard exists in a secure context only, which a page served over plain HTTP on the
// local network is not: execCommand copies there.
function copy(textarea, button) {
  textarea.select();
  const done = navigator.clipboard
    ? navigator.clipboard.writeText(textarea.value)
    : Promise.resolve(document.execCommand("copy"));
  done.then(() => {
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy caption"; }, 1500);
  });
}

async function markScheduled(entry, post, button) {
  button.disabled = true;
  try {
    await api(`${entryUrl(entry)}/posts/${post.platform}/scheduled`, { method: "POST" });
    await load();
  } catch (e) {
    showError(`${entry.project}/${entry.key} ${post.platform}: ${e.message}`);
    button.disabled = false;
  }
}

function todoView(entry, post) {
  const content = entry.manifest.posts[post.platform] || {};
  const caption = h("textarea", { readonly: true }, content.caption || "");
  const copyButton = h("button", { type: "button", onclick: () => copy(caption, copyButton) }, "Copy caption");
  const scheduleButton = h("button", { type: "button", class: "primary" }, "Mark scheduled");
  scheduleButton.addEventListener("click", () => markScheduled(entry, post, scheduleButton));
  return h("div", { class: "card todo" },
    h("video", { src: `${entryUrl(entry)}.mp4`, controls: true, preload: "metadata", playsinline: true }),
    h("div", {},
      h("div", { class: "entry-head" },
        h("span", { class: "entry-name" }, `${entry.project} / ${entry.key}`),
        h("span", { class: "muted" }, `${post.platform}, ${post.account}`),
      ),
      h("div", { class: "when" }, time(entry.publish_at), " ", h("span", { class: "muted" }, until(entry.publish_at))),
      caption,
      h("div", { class: "actions" },
        copyButton,
        h("a", { href: `${entryUrl(entry)}.mp4`, download: "" }, "Download video"),
        scheduleButton,
      ),
    ),
  );
}

async function loadTodo() {
  const pending = await api("/v1/entries?status=pending&limit=500");
  const now = Date.now();
  const todo = pending
    .filter((entry) => new Date(entry.publish_at) > now)
    .flatMap((entry) => entry.posts.filter((p) => p.manual && p.status === "pending").map((post) => [entry, post]))
    .reverse();
  document.getElementById("todo-list").replaceChildren(...todo.map(([entry, post]) => todoView(entry, post)));
  document.getElementById("todo").hidden = todo.length === 0;
}

function query() {
  const params = new URLSearchParams({ limit: PAGE, offset });
  for (const name of ["project", "status"]) {
    const value = filters.elements[name].value;
    if (value) params.set(name, value);
  }
  return params;
}

function addProjects(entries) {
  const select = filters.elements.project;
  for (const entry of entries) {
    if (projects.has(entry.project)) continue;
    projects.add(entry.project);
    select.append(h("option", {}, entry.project));
  }
}

async function loadEntries(append) {
  offset = append ? offset + PAGE : 0;
  const entries = await api(`/v1/entries?${query()}`);
  addProjects(entries);
  const list = document.getElementById("entries");
  const views = entries.map(entryView);
  if (append) list.append(...views);
  else list.replaceChildren(...(views.length ? views : [h("p", { class: "muted" }, "No entry.")]));
  document.getElementById("more").hidden = entries.length < PAGE;
}

async function load() {
  showError("");
  try {
    await Promise.all([loadTodo(), loadEntries(false)]);
  } catch (e) {
    showError(e.message);
  }
}

filters.addEventListener("change", () => loadEntries(false).catch((e) => showError(e.message)));
document.getElementById("refresh").addEventListener("click", load);
document.getElementById("more").addEventListener("click", () => loadEntries(true).catch((e) => showError(e.message)));
load();
