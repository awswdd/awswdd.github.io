/* =========================================================
   Wdd's Blog — 大纲交互
   · 滚动高亮当前小节 (scrollspy)
   · 阅读进度条
   · 移动端目录抽屉开关
   ========================================================= */
(function () {
  "use strict";

  var header = document.querySelector(".site-header");
  var headerH = header ? header.offsetHeight : 56;

  /* ---------- 收集大纲链接与对应标题 ---------- */
  var tocLinks = Array.prototype.slice.call(
    document.querySelectorAll(".toc-nav a[href^='#']")
  );

  var entries = tocLinks
    .map(function (link) {
      var id = decodeURIComponent(link.getAttribute("href").slice(1));
      var target = document.getElementById(id);
      return target ? { link: link, target: target } : null;
    })
    .filter(Boolean);

  /* ---------- scrollspy：高亮当前小节 ---------- */
  var current = null;

  function setActive(link) {
    if (link === current) return;
    if (current) current.classList.remove("is-active");
    if (link) {
      link.classList.add("is-active");
      // 让激活项在侧栏可视区内
      var box = link.getBoundingClientRect();
      var sidebar = document.querySelector(".toc-sidebar__inner");
      if (sidebar) {
        var sb = sidebar.getBoundingClientRect();
        if (box.top < sb.top || box.bottom > sb.bottom) {
          link.scrollIntoView({ block: "nearest" });
        }
      }
    }
    current = link;
  }

  function onScroll() {
    var probe = headerH + 24;
    var active = entries.length ? entries[0].link : null;
    for (var i = 0; i < entries.length; i++) {
      var top = entries[i].target.getBoundingClientRect().top;
      if (top - probe <= 0) {
        active = entries[i].link;
      } else {
        break;
      }
    }
    // 滚到底部时高亮最后一项
    if (
      window.innerHeight + window.scrollY >=
      document.body.scrollHeight - 4
    ) {
      active = entries[entries.length - 1].link;
    }
    setActive(active);
    updateProgress();
  }

  /* ---------- 阅读进度条 ---------- */
  var progress = document.getElementById("reading-progress");

  function updateProgress() {
    if (!progress) return;
    var docH = document.documentElement.scrollHeight - window.innerHeight;
    var pct = docH > 0 ? (window.scrollY / docH) * 100 : 0;
    progress.style.width = Math.min(100, Math.max(0, pct)) + "%";
  }

  /* ---------- requestAnimationFrame 节流 ---------- */
  var ticking = false;
  function requestTick() {
    if (!ticking) {
      window.requestAnimationFrame(function () {
        onScroll();
        ticking = false;
      });
      ticking = true;
    }
  }

  window.addEventListener("scroll", requestTick, { passive: true });
  window.addEventListener("resize", requestTick, { passive: true });

  /* ---------- 移动端目录抽屉 ---------- */
  var toggle = document.getElementById("toc-toggle");
  var sidebar = document.getElementById("toc");
  var backdrop = document.getElementById("toc-backdrop");

  function openToc() {
    if (!sidebar) return;
    sidebar.classList.add("is-open");
    if (backdrop) {
      backdrop.hidden = false;
      requestAnimationFrame(function () { backdrop.classList.add("is-open"); });
    }
    if (toggle) toggle.setAttribute("aria-expanded", "true");
  }

  function closeToc() {
    if (!sidebar) return;
    sidebar.classList.remove("is-open");
    if (backdrop) {
      backdrop.classList.remove("is-open");
      setTimeout(function () { backdrop.hidden = true; }, 220);
    }
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      if (sidebar && sidebar.classList.contains("is-open")) closeToc();
      else openToc();
    });
  }
  if (backdrop) backdrop.addEventListener("click", closeToc);

  // 点击大纲项后在移动端自动收起抽屉
  tocLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      if (window.matchMedia("(max-width: 980px)").matches) closeToc();
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeToc();
  });

  /* ---------- 初始化 ---------- */
  onScroll();
})();
