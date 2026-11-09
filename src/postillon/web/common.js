// What the administration pages share: the API client, the formats of times and statuses, and the
// header (see docs/admin-page.md).

export function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(name, value === true ? "" : value);
  }
  node.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false && c !== ""));
  return node;
}

export function entryUrl(entry) {
  return `/v1/projects/${encodeURIComponent(entry.project)}/entries/${encodeURIComponent(entry.key)}`;
}

// The service holds the video: received, and not released since every platform has it.
export function holdsVideo(entry) {
  return Boolean(entry.video && !entry.video.released_at);
}

export function entryPage(entry) {
  return `entry.html?${new URLSearchParams({ project: entry.project, key: entry.key })}`;
}

// An error answers application/problem+json: its `detail` says why, its `title` otherwise.
export async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const reason = body && (body.detail || body.title);
    throw new Error(reason || `${response.status} ${response.statusText}`);
  }
  return body;
}

// Every item of a paged list, following its page tokens.
export async function all(path, params, field) {
  const items = [];
  let token = "";
  do {
    const query = new URLSearchParams({ ...params, page_size: 500 });
    if (token) query.set("page_token", token);
    const page = await api(`${path}?${query}`);
    items.push(...page[field]);
    token = page.next_page_token;
  } while (token);
  return items;
}

// English names like the rest of the page, a 24-hour clock; the time zone stays the browser's.
const LOCALE = "en-GB";
const CLOCK = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit" });
const DAY = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", month: "long" });
const SHORT_DAY = new Intl.DateTimeFormat(LOCALE, { weekday: "short", day: "numeric", month: "short" });
const FULL = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

function utc(iso) {
  return `${iso.replace("+00:00", "Z")} (UTC)`;
}

// Times show in the browser's time zone, the one TikTok Studio schedules in; UTC on hover.
export function clock(iso) {
  return h("time", { class: "clock", datetime: iso, title: utc(iso) }, CLOCK.format(new Date(iso)));
}

export function when(iso) {
  return iso ? h("time", { datetime: iso, title: utc(iso) }, FULL.format(new Date(iso))) : "";
}

export function shortDay(iso) {
  return SHORT_DAY.format(new Date(iso));
}

// The local calendar day of a time, as a sortable string.
export function dayKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function dayName(date) {
  const today = new Date();
  const offset = Math.round((new Date(dayKey(date)) - new Date(dayKey(today))) / 86400000);
  const relative = { [-1]: "Yesterday", 0: "Today", 1: "Tomorrow" }[offset];
  const name = DAY.format(date);
  return relative ? [`${relative}, `, h("span", { class: "muted" }, name)] : name;
}

export function relative(iso) {
  const minutes = Math.round((new Date(iso) - Date.now()) / 60000);
  const span = Math.abs(minutes);
  const days = Math.floor(span / 1440);
  const hours = Math.floor((span % 1440) / 60);
  const text = days ? `${days} d ${hours} h` : hours ? `${hours} h ${span % 60} min` : `${span} min`;
  return minutes >= 0 ? `in ${text}` : `${text} ago`;
}

const WORDS = {
  pending: "pending",
  in_progress: "sending",
  scheduled: "scheduled",
  published: "published",
  failed: "failed",
  rejected: "rejected",
};

export function status(value) {
  return h("span", { class: `status ${value}` }, h("span", { class: "mark", "aria-hidden": "true" }), WORDS[value] || value);
}

const PLATFORMS = { youtube: "YouTube", instagram: "Instagram", tiktok: "TikTok" };

export function platformName(platform) {
  return PLATFORMS[platform] || platform;
}

export function isToSchedule(post) {
  return post.manual && post.status === "pending" && new Date(post.publish_at) > Date.now();
}

export function notice(message, isError) {
  const node = document.getElementById("notice");
  node.textContent = message || "";
  node.classList.toggle("error", Boolean(isError));
  node.hidden = !message;
}

// The pending posts of manual platforms, nearest first, as [entry, post] pairs.
export async function toSchedule() {
  const now = new Date().toISOString();
  const entries = await all("/v1/projects/-/entries", {
    filter: `posts.manual = true AND posts.status = "pending" AND publish_at > "${now}"`,
    order_by: "publish_at",
  }, "entries");
  return entries.flatMap((entry) => entry.posts.filter(isToSchedule).map((post) => [entry, post]));
}

export function header(current) {
  const link = (href, name, label, extra) =>
    h("a", { href, "aria-current": current === name ? "page" : null }, label, extra);
  const count = h("span", { class: "count", hidden: true });
  document.body.prepend(
    h("header", { class: "top" },
      h("div", { class: "wrap" },
        h("a", { class: "wordmark", href: "./" }, "postillon"),
        h("nav", { class: "nav" },
          link("./", "schedule", "To schedule", count),
          link("publications.html", "publications", "Publications"),
        ),
      ),
    ),
  );
  return (n) => {
    count.textContent = String(n);
    count.hidden = n === 0;
  };
}

// navigator.clipboard exists in a secure context only, which a page served over plain HTTP on the
// local network is not: execCommand copies there.
export function copy(textarea, button) {
  textarea.select();
  const done = navigator.clipboard
    ? navigator.clipboard.writeText(textarea.value)
    : Promise.resolve(document.execCommand("copy"));
  const label = button.textContent;
  done.then(() => {
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = label; }, 1500);
  });
}

// The operator's tools for a post to schedule: its caption to copy, the video to download once
// received, and the button that marks it scheduled; `onScheduled` runs once the API accepts.
export function scheduleTools(entry, post, onScheduled) {
  const content = entry.manifest.posts[post.platform] || {};
  const caption = h("textarea", { class: "caption", readonly: true, "aria-label": "Caption" }, content.caption || "");
  const copyButton = h("button", { type: "button", onclick: () => copy(caption, copyButton) }, "Copy caption");
  // The operator cannot schedule a video the service has not received.
  const scheduleButton = h("button", { type: "button", class: "primary", disabled: !holdsVideo(entry) }, "Mark scheduled");
  scheduleButton.addEventListener("click", async () => {
    scheduleButton.disabled = true;
    try {
      await api(`${entryUrl(entry)}/posts/${post.platform}:mark-scheduled`, { method: "POST" });
      notice(`${entry.key} marked scheduled on ${platformName(post.platform)}.`);
      onScheduled();
    } catch (e) {
      notice(`${entry.key} on ${platformName(post.platform)}: ${e.message}`, true);
      scheduleButton.disabled = false;
    }
  });
  return [
    caption,
    h("div", { class: "actions" },
      copyButton,
      holdsVideo(entry)
        ? h("a", { class: "button", href: `${entryUrl(entry)}/video`, download: true }, "Download video")
        : h("span", { class: "muted" }, "Video not received yet"),
      scheduleButton,
    ),
  ];
}
