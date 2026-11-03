// The account menu in the header is a <details>: it opens without this script. The script only closes
// it the way a menu closes - a click anywhere outside it or Esc - and keeps the lit section tab in view
// on a narrow screen, where the strip of sections scrolls sideways.
(function () {
    "use strict";
    var menu = document.querySelector("header.top details.account");
    if (menu) {
        document.addEventListener("click", function (e) {
            if (menu.open && !menu.contains(e.target)) menu.open = false;
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && menu.open) {
                menu.open = false;
                menu.querySelector("summary").focus();
            }
        });
    }
    // scrollLeft, not scrollIntoView: that one would also scroll the page up to the header
    var tabs = document.querySelector("header.top nav.tabs");
    var on = tabs && tabs.querySelector("a.on");
    if (on && tabs.scrollWidth > tabs.clientWidth)
        tabs.scrollLeft = on.offsetLeft - (tabs.clientWidth - on.offsetWidth) / 2;
})();
