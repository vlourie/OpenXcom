// A ticket's picture opens over the page, not in place of it: Esc, a click anywhere or the cross
// brings the ticket back. Without this script the link still opens the picture in a new tab.
(function () {
    "use strict";
    var dialog = null, img = null;

    function build() {
        dialog = document.createElement("dialog");
        dialog.className = "lightbox";
        var close = document.createElement("button");
        close.type = "button";
        close.className = "close";
        close.setAttribute("aria-label", document.documentElement.lang === "ru" ? "Закрыть" : "Close");
        close.textContent = "×";
        img = document.createElement("img");
        img.alt = "";
        dialog.append(close, img);
        // any click closes it: on the picture, on the cross or on the dark around them
        dialog.addEventListener("click", function () { dialog.close(); });
        dialog.addEventListener("close", function () { img.removeAttribute("src"); });
        document.body.append(dialog);
    }

    document.addEventListener("click", function (e) {
        var a = e.target.closest && e.target.closest("a[data-image]");
        // Ctrl/Shift/middle click keep their usual meaning: a new tab or window
        if (!a || e.button !== 0 || e.ctrlKey || e.shiftKey || e.metaKey || e.altKey) return;
        if (!dialog) build();
        if (typeof dialog.showModal !== "function") return;
        e.preventDefault();
        img.src = a.href;
        img.alt = a.textContent;
        dialog.showModal();
    });
})();
