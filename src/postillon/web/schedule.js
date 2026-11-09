// The posts the operator schedules by hand, nearest first.
import {
  clock, entryPage, entryUrl, h, header, holdsVideo, notice, platformName, relative, scheduleTools, shortDay, toSchedule,
} from "./common.js";

const setCount = header("schedule");
const list = document.getElementById("list");

function item(entry, post) {
  return h("article", { class: "todo" },
    holdsVideo(entry)
      ? h("video", { src: `${entryUrl(entry)}/video`, controls: true, preload: "metadata", playsinline: true })
      : h("p", { class: "muted" }, "Video not received yet."),
    h("div", {},
      h("div", { class: "todo-when" },
        h("span", { class: "clock" }, shortDay(entry.publish_at)),
        clock(entry.publish_at),
        h("span", { class: "muted" }, relative(entry.publish_at)),
      ),
      h("div", { class: "todo-where" },
        h("a", { href: entryPage(entry) }, entry.key),
        h("span", { class: "muted" }, ` ${entry.project}, ${platformName(post.platform)} account ${post.account}`),
      ),
      scheduleTools(entry, post, load),
    ),
  );
}

async function load() {
  try {
    const todo = await toSchedule();
    setCount(todo.length);
    list.replaceChildren(
      ...(todo.length
        ? todo.map(([entry, post]) => item(entry, post))
        : [h("div", { class: "empty" },
            h("p", {}, "Nothing to schedule. A post on a manual platform shows here until it is marked scheduled."),
            h("a", { class: "button", href: "publications.html" }, "See publications"),
          )]),
    );
  } catch (e) {
    notice(`The service did not answer: ${e.message}`, true);
  }
}

load();
