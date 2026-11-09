// The entries by publication time: upcoming ones from the nearest, then a line at the present time, then
// past ones from the latest; one column per platform.
import { api, clock, dayKey, dayName, entryPage, h, header, notice, platformName, status, toSchedule } from "./common.js";

const PAGE = 100;
const setCount = header("publications");
const filters = document.getElementById("filters");
const board = document.getElementById("board");
const more = document.getElementById("more");
const projects = new Set();
let entries = [];
let nextToken = null;

function row(entry, platforms) {
  const posts = Object.fromEntries(entry.posts.map((post) => [post.platform, post]));
  const errors = entry.posts.filter((post) => post.error);
  return h("a", { class: "row", href: entryPage(entry) },
    h("div", { class: "row-line" },
      clock(entry.publish_at),
      h("span", { class: "row-name" },
        entry.key,
        filters.elements.project.value ? "" : h("span", { class: "project" }, entry.project),
      ),
      platforms.map((platform) =>
        h("span", { class: "cell" },
          h("span", { class: "cell-platform" }, platformName(platform)),
          posts[platform] ? status(posts[platform].status) : h("span", { class: "muted", "aria-label": "no post" }, "-"),
        ),
      ),
    ),
    errors.map((post) => h("div", { class: "error-text" }, `${platformName(post.platform)}: ${post.error}`)),
  );
}

function days(list, platforms) {
  const groups = [];
  for (const entry of list) {
    const date = new Date(entry.publish_at);
    const key = dayKey(date);
    if (groups.at(-1)?.key !== key) groups.push({ key, date, entries: [] });
    groups.at(-1).entries.push(entry);
  }
  return groups.map((group) => [
    h("h2", { class: "day" }, dayName(group.date)),
    group.entries.map((entry) => row(entry, platforms)),
  ]);
}

function render() {
  if (!entries.length) {
    board.replaceChildren(h("div", { class: "empty" }, h("p", {}, "No entry matches these filters.")));
    return;
  }
  const platforms = [...new Set(entries.flatMap((entry) => entry.posts.map((post) => post.platform)))].sort();
  board.style.setProperty("--platforms", platforms.length);
  const now = Date.now();
  const upcoming = entries.filter((entry) => new Date(entry.publish_at) > now).reverse();
  const past = entries.filter((entry) => new Date(entry.publish_at) <= now);
  board.replaceChildren(
    ...[
      h("div", { class: "board-head", "aria-hidden": "true" },
        h("span", {}, "Time"), h("span", {}, "Entry"), platforms.map((p) => h("span", {}, platformName(p)))),
      days(upcoming, platforms),
      h("div", { class: "now" }, "Now, ", clock(new Date(now).toISOString())),
      days(past, platforms),
    ].flat(Infinity),
  );
}

function addProjects(list) {
  for (const entry of list) {
    if (projects.has(entry.project)) continue;
    projects.add(entry.project);
    filters.elements.project.append(h("option", {}, entry.project));
  }
}

async function load(append) {
  const project = filters.elements.project.value || "-";
  const params = new URLSearchParams({ page_size: PAGE });
  if (filters.elements.status.value) params.set("filter", `posts.status = "${filters.elements.status.value}"`);
  if (append && nextToken) params.set("page_token", nextToken);
  try {
    const page = await api(`/v1/projects/${encodeURIComponent(project)}/entries?${params}`);
    addProjects(page.entries);
    entries = append ? entries.concat(page.entries) : page.entries;
    nextToken = page.next_page_token;
    more.hidden = !nextToken;
    render();
  } catch (e) {
    notice(`The service did not answer: ${e.message}`, true);
  }
}

filters.addEventListener("change", () => load(false));
more.addEventListener("click", () => load(true));
load(false);
toSchedule().then((todo) => setCount(todo.length), () => {});
