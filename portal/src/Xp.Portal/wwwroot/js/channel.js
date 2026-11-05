// The feed of a channel keeps itself fresh: every three seconds, and only while the tab is in view, it asks
// /api/v1/voice/rooms/<room>/messages?after=<last line> and adds what is new. Without this script the page
// works all the same - a post reloads it. Nothing a player wrote goes in as markup: lines are built from
// elements and text nodes (textContent), and an address becomes a link only if it is http or https.
(function () {
    "use strict";
    var box = document.getElementById("lines");
    if (!box || !window.fetch) return;

    var url = box.dataset.url;
    var after = box.dataset.after;
    var me = box.dataset.me;
    var canModerate = box.dataset.canModerate === "1";
    var every = 3000;
    var timer = 0;
    var stopped = false;
    var busy = false;

    function atEnd() { return box.scrollHeight - box.scrollTop - box.clientHeight < 40; }
    function toEnd() { box.scrollTop = box.scrollHeight; }

    // "{0} joined" with names put in: split and join, so a name that looks like a pattern stays a name
    function fill(template, a, b) {
        return (template || "").split("{0}").join(a || "").split("{1}").join(b || "");
    }

    function camel(s) { return s.replace(/-([a-z])/g, function (_, c) { return c.toUpperCase(); }); }

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    }

    // text with addresses: plain text nodes between <a> elements
    function richText(parent, text) {
        var rx = /https?:\/\/[^\s<>"']+/gi;
        var at = 0, m;
        while ((m = rx.exec(text)) !== null) {
            var addr = m[0].replace(/[.,;:!?)]+$/, "");
            parent.appendChild(document.createTextNode(text.slice(at, m.index)));
            var ok = false;
            try { var u = new URL(addr); ok = u.protocol === "http:" || u.protocol === "https:"; } catch (e) { ok = false; }
            if (ok) {
                var a = el("a", "", addr);
                a.href = addr;
                a.rel = "nofollow noopener";
                a.target = "_blank";
                parent.appendChild(a);
            } else {
                parent.appendChild(document.createTextNode(addr));
            }
            at = m.index + addr.length;
            rx.lastIndex = at;
        }
        parent.appendChild(document.createTextNode(text.slice(at)));
    }

    function sysText(l) {
        var name = l.author ? l.author.name : "";
        if (l.event === "topic" && !l.body) return fill(box.dataset.sTopicCleared, name);
        var tpl = box.dataset[camel("s-" + l.event)];
        return tpl ? fill(tpl, name, l.body) : (l.event + " " + l.body);
    }

    function lineNode(l) {
        var cls = "line" + (l.kind === "system" ? " sys" : "") + (l.mention ? " mention" : "") + (l.mine ? " mine" : "");
        var row = el("div", cls);
        row.dataset.id = String(l.id);
        var t = el("time", "", new Date(l.at).toISOString().slice(11, 16));
        t.setAttribute("datetime", l.at);
        row.appendChild(t);
        var name = l.author ? l.author.name : "";
        if (l.kind === "system") {
            row.appendChild(el("span", "body", "-- " + sysText(l)));
        } else if (l.kind === "action") {
            var act = el("span", "body", "* ");
            act.appendChild(el("b", "nick", name));
            act.appendChild(document.createTextNode(" "));
            richText(act, l.body);
            row.appendChild(act);
        } else {
            row.appendChild(el("span", "nick", "<" + name + ">"));
            row.appendChild(document.createTextNode(" "));
            var body = el("span", "body");
            richText(body, l.body);
            row.appendChild(body);
        }
        if (l.kind !== "system" && (l.mine || canModerate)) {
            var del = el("button", "link del", "×");
            del.type = "submit";
            del.setAttribute("form", "delete-form");
            del.name = "id";
            del.value = String(l.id);
            del.title = box.dataset.sDelete || "";
            del.setAttribute("aria-label", box.dataset.sDelete || "");
            row.appendChild(del);
        }
        return row;
    }

    function people(list) {
        var ul = document.getElementById("people");
        if (!ul) return;
        while (ul.firstChild) ul.removeChild(ul.firstChild);
        list.forEach(function (a) {
            var li = el("li");
            li.appendChild(el("span", "mark", (a.operator ? "@" : "") + (a.voice ? "+" : "")));
            li.appendChild(el("span", "nick", a.person.name));
            if (a.muted) li.appendChild(el("span", "hint", " · " + (ul.dataset.sSilent || "")));
            ul.appendChild(li);
        });
    }

    function apply(view) {
        var stick = atEnd();
        var end = document.getElementById("end");
        (view.removed || []).forEach(function (id) {
            var gone = box.querySelector('.line[data-id="' + String(id).replace(/[^0-9]/g, "") + '"]');
            if (gone) gone.parentNode.removeChild(gone);
        });
        if (view.lines && view.lines.length) {
            var empty = document.getElementById("empty");
            if (empty) empty.parentNode.removeChild(empty);
            view.lines.forEach(function (l) {
                if (box.querySelector('.line[data-id="' + String(l.id).replace(/[^0-9]/g, "") + '"]')) return;
                box.insertBefore(lineNode(l), end);
            });
        }
        if (typeof view.last === "number" || typeof view.last === "string") { after = String(view.last); box.dataset.after = after; }
        var topic = document.getElementById("topic");
        if (topic) topic.textContent = view.topic || box.dataset.sNotopic || "";
        people(view.attendees || []);
        if (stick) toEnd();
    }

    function schedule(ms) {
        window.clearTimeout(timer);
        if (stopped) return;
        timer = window.setTimeout(poll, ms || every);
    }

    function poll() {
        if (stopped || busy) return;
        // a tab nobody looks at asks for nothing; it asks at once when it comes back
        if (document.visibilityState === "hidden") return;
        busy = true;
        fetch(url + "?after=" + encodeURIComponent(after), {
            credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" }
        }).then(function (r) {
            busy = false;
            if (r.status === 429) { schedule(15000); return null; }
            // signed out, not allowed any more, or the room is gone: nothing more to ask
            if (r.status === 401 || r.status === 403 || r.status === 404) { stopped = true; return null; }
            if (!r.ok) { schedule(10000); return null; }
            return r.json();
        }).then(function (view) {
            if (view) { apply(view); schedule(every); }
        }).catch(function () {
            busy = false;
            schedule(10000);
        });
    }

    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible") { window.clearTimeout(timer); poll(); }
    });
    toEnd();
    // a post comes back as a reload: the next line goes on being typed, and the page does not ride down to #end
    var say = document.getElementById("say");
    if (say && (location.hash === "#end" || location.search.indexOf("handler=") >= 0)) {
        say.focus({ preventScroll: true });
        // the browser goes to the anchor after "load" has run and that drops the focus: undo it on the next turn
        window.addEventListener("load", function () {
            window.setTimeout(function () {
                window.scrollTo(0, 0);
                say.focus({ preventScroll: true });
            }, 0);
        });
    }
    schedule(every);
})();
