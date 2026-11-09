// One entry: its video while the service holds it, each post with the history of its statuses, and
// the manifest as received.
import {
  all, api, clock, entryUrl, h, header, holdsVideo, isToSchedule, notice, platformName, relative, scheduleTools,
  shortDay, status, toSchedule, when,
} from "./common.js";

const setCount = header(null);
const root = document.getElementById("entry");
const params = new URLSearchParams(location.search);

function post(entry, item, events) {
  const facts = [
    ["Account", item.account],
    ["Remote id", item.remote_id],
    ["Sent for", item.outdated ? when(item.publish_at) : ""],
    ["Failures", item.failures ? String(item.failures) : ""],
    ["Updated", when(item.updated_at)],
  ].filter(([, value]) => value);
  return h("section", { class: "post" },
    h("div", { class: "post-head" }, h("h2", {}, platformName(item.platform)), status(item.status)),
    item.error && h("p", { class: "error-text" }, item.error),
    item.outdated && h("p", { class: "muted small" }, "Sent before the latest manifest, which its platform did not receive."),
    h("dl", {}, facts.map(([name, value]) => [h("dt", {}, name), h("dd", {}, value)])),
    isToSchedule(item) && h("div", { class: "schedule" }, scheduleTools(entry, item, load)),
    h("ol", { class: "history", "aria-label": "History" },
      events.filter((event) => event.platform === item.platform).map((event) =>
        h("li", {}, when(event.at), status(event.status), event.error && h("span", { class: "error-text" }, event.error)),
      ),
    ),
  );
}

function video(entry) {
  if (holdsVideo(entry)) {
    return h("video", { src: `${entryUrl(entry)}/video`, controls: true, preload: "metadata", playsinline: true });
  }
  if (entry.video) {
    return h("p", { class: "muted" }, "The service holds no video of this entry since ", when(entry.video.released_at), ".");
  }
  if (entry.posts.some((item) => item.status === "pending")) {
    return h("p", { class: "muted" }, "No video received yet: the pending posts wait for it.");
  }
  return h("p", { class: "muted" }, "The service never received a video of this entry.");
}

function render(entry, events) {
  document.title = `${entry.key} - postillon`;
  root.replaceChildren(
    h("div", { class: "entry-head" },
      h("span", { class: "clock" }, shortDay(entry.publish_at)),
      clock(entry.publish_at),
      h("span", { class: "muted" }, relative(entry.publish_at)),
    ),
    h("h1", { class: "entry-title" }, entry.key, h("span", { class: "muted" }, ` ${entry.project}`)),
    h("div", { class: "entry" },
      h("div", { class: "entry-video" }, video(entry)),
      h("div", {},
        entry.posts.map((item) => post(entry, item, events)),
        h("p", { class: "muted small" }, "Submitted ", when(entry.submitted_at),
          entry.updated_at !== entry.submitted_at ? [", last updated ", when(entry.updated_at)] : "", "."),
        h("details", { class: "manifest" },
          h("summary", {}, "Manifest as received"),
          h("pre", {}, JSON.stringify(entry.manifest, null, 2)),
        ),
      ),
    ),
  );
}

async function load() {
  const project = params.get("project");
  const key = params.get("key");
  if (!project || !key) {
    notice("This page shows one entry: open it from the publications.", true);
    return;
  }
  try {
    const url = entryUrl({ project, key });
    const [entry, events] = await Promise.all([api(url), all(`${url}/posts/-/events`, {}, "events")]);
    render(entry, events);
  } catch (e) {
    notice(`${project}/${key}: ${e.message}`, true);
  }
  toSchedule().then((todo) => setCount(todo.length), () => {});
}

load();
