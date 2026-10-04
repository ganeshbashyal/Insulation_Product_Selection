(() => {
  "use strict";
  const script = document.currentScript;
  if (!script || !script.dataset.siteId) return;
  const host = new URL(script.src).origin;
  const container = document.createElement("div");
  const shadow = container.attachShadow({mode: "closed"});
  const button = document.createElement("button");
  button.textContent = "Product questions";
  button.setAttribute("aria-expanded", "false");
  button.style.cssText = "position:fixed;right:20px;bottom:20px;padding:14px;border:0;border-radius:24px;background:#087f7a;color:white;font:16px system-ui;cursor:pointer;z-index:2147483000";
  const frame = document.createElement("iframe");
  frame.title = "Product enquiry chat";
  frame.referrerPolicy = "no-referrer";
  frame.style.cssText = "position:fixed;right:20px;bottom:78px;width:min(390px,calc(100vw - 40px));height:min(580px,calc(100vh - 110px));border:1px solid #bbb;border-radius:12px;z-index:2147483000;background:white";
  frame.hidden = true;
  const url = new URL("/widget", host);
  url.search = new URLSearchParams({site_id: script.dataset.siteId, parent_origin: location.origin});
  let loaded = false;
  button.addEventListener("click", () => {
    if (!loaded) { frame.src = url.href; loaded = true; }
    frame.hidden = !frame.hidden;
    button.setAttribute("aria-expanded", String(!frame.hidden));
  });
  shadow.append(button, frame);
  document.body.append(container);
})();
