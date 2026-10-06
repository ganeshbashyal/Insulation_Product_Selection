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
  const restrictedPage = /^\/(?:my-account|cart|checkout|order-pay|order-received|view-order)(?:\/|$)/i.test(location.pathname);
  const pageContext = restrictedPage ? null : {
    page_url: location.origin + location.pathname,
    page_type: script.dataset.pageType || "other",
    product_id: script.dataset.productId || undefined,
    variation_id: script.dataset.variationId || undefined,
    product_name: script.dataset.productName || undefined,
    product_category: script.dataset.productCategory || undefined,
    product_url: script.dataset.productUrl || undefined
  };
  const url = new URL("/widget", host);
  url.search = new URLSearchParams({site_id: script.dataset.siteId, parent_origin: location.origin});
  frame.addEventListener("load", () => {
    if (frame.contentWindow) {
      frame.contentWindow.postMessage({type: "aurora-page-context", pageContext}, host);
    }
  });
  let loaded = false;
  button.addEventListener("click", () => {
    if (!loaded) { frame.src = url.href; loaded = true; }
    frame.hidden = !frame.hidden;
    button.setAttribute("aria-expanded", String(!frame.hidden));
  });
  shadow.append(button, frame);
  document.body.append(container);
})();
