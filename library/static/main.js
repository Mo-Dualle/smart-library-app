"use strict";

// ===========================================================================
// Utils
// ===========================================================================
const Utils = {
  debounce(fn, ms = 350) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  },
  getCsrf() {
    // 1. Try the cookie (standard Django setup)
    const fromCookie = document.cookie.match(/csrftoken=([^;]+)/)?.[1];
    if (fromCookie) return decodeURIComponent(fromCookie);
    // 2. Fall back to the hidden input Django injects via {% csrf_token %}
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value ?? "";
  },
  /**
   * POST form data to a URL, return parsed JSON.
   * Throws on non-2xx responses.
   */
  async postForm(url, formData) {
    // Send CSRF in body (guaranteed) AND header (belt-and-suspenders)
    formData.append("csrfmiddlewaretoken", Utils.getCsrf());

    let res;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: { "X-CSRFToken": Utils.getCsrf() },
        body: formData,
      });
    } catch (_) {
      throw new Error("Network error — check your connection.");
    }

    // Try JSON parse; if Django returned HTML (403/login redirect) handle it
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); }
    catch (_) {
      if (res.status === 403) throw new Error("Permission denied (CSRF or session issue).");
      throw new Error("Session expired — please refresh the page.");
    }

    if (!res.ok) throw new Error(json.error ?? `Server error (${res.status}).`);
    return json;
  },
};


// ===========================================================================
// Flash messages — auto-dismiss after 5 s
// ===========================================================================
function initMessages() {
  document.querySelectorAll("#flash-messages .alert").forEach((el, i) => {
    setTimeout(() => {
      bootstrap.Alert.getOrCreateInstance(el).close();
    }, 5000 + i * 500);
  });
}


// ===========================================================================
// Navbar — highlight active link
// ===========================================================================
function initNavbar() {
  const path = window.location.pathname;
  document.querySelectorAll(".navbar-nav .nav-link").forEach((link) => {
    const href = new URL(link.href, location.origin).pathname;
    if (href !== "/" && path.startsWith(href)) link.classList.add("active");
  });
}


// ===========================================================================
// Confirm modal — intercept forms with data-confirm="Title|Body"
// ===========================================================================
function initConfirmModal() {
  /*
   * XSS-safe confirm modal.
   *
   * Uses SEPARATE data attributes instead of a pipe-delimited string so that
   * user-controlled values (book titles, member names) can never corrupt the
   * okLabel or okClass slots.
   *
   * Attributes read from the form element:
   *   data-confirm-title  — modal heading          (default: "Are you sure?")
   *   data-confirm-body   — modal body text        (default: "")
   *   data-confirm-ok     — confirm button label   (default: "Confirm")
   *   data-confirm-class  — confirm button classes (default: "btn btn-danger")
   *
   * All values are written via .textContent — never innerHTML.
   * okClass is validated against an allowlist so arbitrary strings cannot
   * reach className even in the unlikely event a value is injected.
   */
  const ALLOWED_BTN_CLASSES = new Set([
    "btn btn-danger",
    "btn btn-success",
    "btn btn-primary",
    "btn btn-warning",
    "btn btn-dark",
  ]);

  const html = `
    <div class="modal fade" id="confirmModal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title fw-bold" id="confirmModalLabel"></h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body" id="confirmModalBody"></div>
          <div class="modal-footer">
            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-danger" id="confirmModalOk">Confirm</button>
          </div>
        </div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML("beforeend", html);

  const modal   = new bootstrap.Modal(document.getElementById("confirmModal"));
  const titleEl = document.getElementById("confirmModalLabel");
  const bodyEl  = document.getElementById("confirmModalBody");
  const okBtn   = document.getElementById("confirmModalOk");
  let   pending = null;

  document.addEventListener("submit", (e) => {
    const form = e.target;
    // Support both old pipe format (data-confirm) and new separate attributes
    const hasOld = !!form.dataset.confirm;
    const hasNew = !!form.dataset.confirmTitle;
    if (!hasOld && !hasNew) return;
    e.preventDefault();

    let title, body, okLabel, okCls;

    if (hasNew) {
      // Preferred: separate attributes — no parsing, no injection surface
      title   = form.dataset.confirmTitle || "Are you sure?";
      body    = form.dataset.confirmBody  || "";
      okLabel = form.dataset.confirmOk    || "Confirm";
      okCls   = form.dataset.confirmClass || "btn btn-danger";
    } else {
      // Legacy pipe format — still supported but body may be truncated if
      // the title/body contained pipe characters (logic bug, not XSS)
      const parts = form.dataset.confirm.split("|");
      title   = parts[0] || "Are you sure?";
      body    = parts[1] || "";
      okLabel = parts[2] || "Confirm";
      okCls   = parts[3] || "btn btn-danger";
    }

    // Write text-only — never innerHTML
    titleEl.textContent = title;
    bodyEl.textContent  = body;
    okBtn.textContent   = okLabel;

    // Allowlist className to prevent CSS injection
    okBtn.className = ALLOWED_BTN_CLASSES.has(okCls) ? okCls : "btn btn-danger";

    pending = form;
    modal.show();
  });

  okBtn.addEventListener("click", () => {
    modal.hide();
    if (pending) {
      pending.removeAttribute("data-confirm");
      pending.removeAttribute("data-confirm-title");
      pending.submit();
    }
  });
}


// ===========================================================================
// Loading state — spinner on submit button
// ===========================================================================
function initLoadingStates() {
  /*
   * XSS fix: store/restore the button label using a data attribute
   * (btn.dataset.originalLabel) instead of btn.innerHTML.
   * The spinner is injected as a hardcoded string — no user data involved.
   */
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form.dataset.confirm || form.dataset.confirmTitle) return;
    const btn = form.querySelector('[type="submit"]');
    if (!btn || btn.dataset.noLoading) return;

    // Save current text label (textContent only — no HTML)
    btn.dataset.originalLabel = btn.textContent.trim();
    btn.disabled  = true;
    // Hardcoded spinner — never touches user data
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Processing\u2026';

    window.addEventListener("pageshow", () => {
      btn.disabled     = false;
      btn.textContent  = btn.dataset.originalLabel || "Submit";
      delete btn.dataset.originalLabel;
    }, { once: true });
  });
}


// ===========================================================================
// Login form — client-side validation
// ===========================================================================
function initLoginForm() {
  const form = document.getElementById("loginForm");
  if (!form) return;

  // Password show/hide
  document.getElementById("togglePwd")?.addEventListener("click", () => {
    const pwd  = form.querySelector("#password");
    const icon = document.querySelector("#togglePwd i");
    const show = pwd.type === "password";
    pwd.type = show ? "text" : "password";
    icon.classList.toggle("fa-eye",      !show);
    icon.classList.toggle("fa-eye-slash", show);
  });

  form.addEventListener("submit", (e) => {
    let ok = true;

    const email = form.querySelector("#email");
    const pwd   = form.querySelector("#password");

    const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim());
    email.classList.toggle("is-invalid", !emailOk);
    email.classList.toggle("is-valid",    emailOk);
    if (!emailOk) ok = false;

    const pwdOk = pwd.value.length > 0;
    pwd.classList.toggle("is-invalid", !pwdOk);
    pwd.classList.toggle("is-valid",    pwdOk);
    if (!pwdOk) ok = false;

    if (!ok) e.preventDefault();
  });
}


// ===========================================================================
// Register form — client-side validation
// ===========================================================================
function initRegisterForm() {
  const form = document.getElementById("registerForm");
  if (!form) return;

  const mark = (el, valid, msg = "") => {
    el.classList.toggle("is-invalid", !valid);
    el.classList.toggle("is-valid",    valid);
    if (!valid && msg) {
      const fb = el.nextElementSibling;
      if (fb?.classList.contains("invalid-feedback")) fb.textContent = msg;
    }
  };

  form.addEventListener("submit", (e) => {
    let ok = true;

    ["first_name", "last_name", "username", "phone"].forEach((id) => {
      const el    = form.querySelector(`#${id}`);
      const valid = el.value.trim().length > 0;
      mark(el, valid);
      if (!valid) ok = false;
    });

    const email   = form.querySelector("#email");
    const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim());
    mark(email, emailOk);
    if (!emailOk) ok = false;

    const p1 = form.querySelector("#password1");
    const p2 = form.querySelector("#password2");

    if (p1.value.length < 8) {
      mark(p1, false, "Password must be at least 8 characters.");
      ok = false;
    } else mark(p1, true);

    if (p2.value !== p1.value) {
      mark(p2, false, "Passwords do not match.");
      ok = false;
    } else if (p2.value) mark(p2, true);

    if (!ok) e.preventDefault();
  });
}


// ===========================================================================
// Book search — debounced live submit + instant category change
// ===========================================================================
function initBookSearch() {
  const input    = document.getElementById("searchInput");
  const category = document.getElementById("categoryFilter");
  if (!input) return;

  input.addEventListener("input", Utils.debounce(() => input.closest("form").submit(), 450));
  category?.addEventListener("change", () => input.closest("form").submit());
}


// ===========================================================================
// Borrow form — quantity validation on book detail page
// ===========================================================================
function initBorrowForm() {
  const form  = document.getElementById("borrowForm");
  if (!form) return;

  const qty   = form.querySelector("#quantity");
  const btn   = form.querySelector("#borrowBtn");
  const errEl = form.querySelector("#qtyError");
  const max   = parseInt(qty?.max ?? "1", 10);
  if (!qty) return;

  const validate = () => {
    const val     = parseInt(qty.value, 10);
    const invalid = isNaN(val) || val < 1 || val > max;
    qty.classList.toggle("is-invalid", invalid);
    qty.classList.toggle("is-valid",  !invalid);
    if (btn) btn.disabled = invalid;
    if (errEl && invalid) {
      errEl.textContent = val > max
        ? `Only ${max} cop${max === 1 ? "y" : "ies"} available.`
        : "Enter a number between 1 and " + max + ".";
    }
    return !invalid;
  };

  qty.addEventListener("input", validate);
  form.addEventListener("submit", (e) => { if (!validate()) e.preventDefault(); });
}


// ===========================================================================
// Admin forms — required field validation (book / author / category)
// ===========================================================================
function initAdminForms() {
  ["bookForm", "authorForm", "categoryForm", "staffForm"].forEach((id) => {
    const form = document.getElementById(id);
    if (!form) return;
    form.addEventListener("submit", (e) => {
      let valid = true;
      form.querySelectorAll("[required]").forEach((el) => {
        const ok = el.value.trim().length > 0;
        el.classList.toggle("is-invalid", !ok);
        el.classList.toggle("is-valid",    ok);
        if (!ok) valid = false;
      });
      if (!valid) e.preventDefault();
    });
  });
}


// ===========================================================================
// Inline Author / Category creation from the book form modals
// Each modal:
//   1. POSTs name to a JSON endpoint via fetch
//   2. On success: adds a new <option> to the dropdown, selects it, closes modal
//   3. On error:   shows the error message inside the modal (no page reload)
// ===========================================================================
function initInlineCreation() {
  const urls = window.LIBRARY_URLS;
  if (!urls) return;  // only on the book form page

  // Keep modals on <body> so they are not clipped/trapped by animated <main>
  ["authorModal", "categoryModal"].forEach((id) => {
    const el = document.getElementById(id);
    if (el && el.parentElement !== document.body) {
      document.body.appendChild(el);
    }
  });

  // ── Shared: blur focused element before Bootstrap sets aria-hidden ──────
  // This MUST use hide.bs.modal (fires before aria-hidden is applied).
  // Blurring here prevents Chrome's "Blocked aria-hidden on focused element".
  function fixAriaHidden(modalEl) {
    modalEl.addEventListener("hide.bs.modal", () => {
      if (modalEl.contains(document.activeElement)) {
        document.activeElement.blur();
      }
    });
  }

  // ── Shared modal handler factory ────────────────────────────────────────
  function setupModal({ modalId, inputId, errorId, saveBtnId, selectId, endpoint, label, photoInputId }) {
    const modalEl  = document.getElementById(modalId);
    const input    = document.getElementById(inputId);
    const errorEl  = document.getElementById(errorId);
    const saveBtn  = document.getElementById(saveBtnId);
    const select   = document.getElementById(selectId);
    const photoInput = photoInputId ? document.getElementById(photoInputId) : null;
    const preview  = photoInput?.dataset.preview ? document.querySelector(photoInput.dataset.preview) : null;
    const fallback = photoInput?.dataset.fallback ? document.querySelector(photoInput.dataset.fallback) : null;
    const initialEl = photoInput?.dataset.initial ? document.querySelector(photoInput.dataset.initial) : null;

    if (!saveBtn || !modalEl) return;

    fixAriaHidden(modalEl);

    function syncInitial() {
      if (!initialEl || !input) return;
      initialEl.textContent = (input.value.trim()[0] || "?").toUpperCase();
    }

    function resetPhoto() {
      if (photoInput) photoInput.value = "";
      if (preview) {
        preview.src = "";
        preview.classList.add("d-none");
      }
      if (fallback) {
        fallback.classList.remove("d-none");
      }
      syncInitial();
    }

    if (photoInput && preview) {
      photoInput.addEventListener("change", () => {
        const file = photoInput.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) {
          alert("Photo must be under 5 MB.");
          photoInput.value = "";
          return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
          preview.src = e.target.result;
          preview.classList.remove("d-none");
          if (fallback) fallback.classList.add("d-none");
        };
        reader.readAsDataURL(file);
      });
    }

    if (input) {
      input.addEventListener("input", syncInitial);
    }

    // Reset state on open
    modalEl.addEventListener("shown.bs.modal", () => {
      input.value = "";
      input.classList.remove("is-invalid");
      errorEl.classList.add("d-none");
      errorEl.textContent = "";
      resetPhoto();
      input.focus();
    });

    // Enter key submits
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); saveBtn.click(); }
    });

    // Save button
    saveBtn.addEventListener("click", async () => {
      const name = input.value.trim();

      // Client-side required check
      if (!name) {
        errorEl.textContent = `${label} name is required.`;
        errorEl.classList.remove("d-none");
        input.classList.add("is-invalid");
        input.focus();
        return;
      }

      // Loading state
      const originalHTML   = saveBtn.innerHTML;
      saveBtn.disabled     = true;
      saveBtn.innerHTML    = `<span class="spinner-border spinner-border-sm me-1" role="status"></span>Saving…`;
      errorEl.classList.add("d-none");

      try {
        const fd = new FormData();
        fd.append("name", name);
        if (photoInput?.files[0]) {
          if (photoInput.files[0].size > 5 * 1024 * 1024) {
            errorEl.textContent = "Photo must be under 5 MB.";
            errorEl.classList.remove("d-none");
            return;
          }
          fd.append("photo", photoInput.files[0]);
        }

        const data = await Utils.postForm(endpoint, fd);

        // Add new <option> and select it
        const opt = new Option(data.name, data.id, true, true);
        select.appendChild(opt);
        select.value = data.id;
        select.classList.remove("is-invalid");
        select.classList.add("is-valid");

        // Close modal — aria-hidden fix already handled by hide.bs.modal listener
        bootstrap.Modal.getOrCreateInstance(modalEl).hide();

      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("d-none");
        input.focus();
      } finally {
        saveBtn.disabled  = false;
        saveBtn.innerHTML = originalHTML;
      }
    });
  }

  // ── Author modal ─────────────────────────────────────────────────────────
  setupModal({
    modalId:  "authorModal",
    inputId:  "newAuthorName",
    errorId:  "authorError",
    saveBtnId:"saveAuthorBtn",
    selectId: "author_id",
    endpoint: urls.authorCreateJson,
    label:    "Author",
    photoInputId: "newAuthorPhoto",
  });

  // ── Category modal ────────────────────────────────────────────────────────
  setupModal({
    modalId:  "categoryModal",
    inputId:  "newCategoryName",
    errorId:  "categoryError",
    saveBtnId:"saveCategoryBtn",
    selectId: "category_id",
    endpoint: urls.categoryCreateJson,
    label:    "Category",
    photoInputId: "newCategoryPhoto",
  });
}

// ===========================================================================
// Image preview — live preview on file select
// ===========================================================================
function initImagePreview() {
  document.querySelectorAll("input[type='file'][data-preview]").forEach((input) => {
    const preview = document.querySelector(input.dataset.preview);
    const fallback = input.dataset.fallback ? document.querySelector(input.dataset.fallback) : null;
    const initialEl = input.dataset.initial ? document.querySelector(input.dataset.initial) : null;
    const nameInput = input.dataset.name ? document.querySelector(input.dataset.name) : null;

    if (nameInput && initialEl) {
      const sync = () => {
        initialEl.textContent = (nameInput.value.trim()[0] || "?").toUpperCase();
      };
      nameInput.addEventListener("input", sync);
      sync();
    }

    if (!preview) return;

    input.addEventListener("change", () => {
      const file = input.files[0];
      if (!file || !file.type.startsWith("image/")) return;
      if (file.size > 5 * 1024 * 1024) {
        alert("Photo must be under 5 MB.");
        input.value = "";
        return;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        preview.src = e.target.result;
        preview.classList.remove("d-none");
        preview.style.display = "block";
        if (fallback) fallback.classList.add("d-none");
      };
      reader.readAsDataURL(file);
    });
  });
}


// ===========================================================================
// Reading session timer — live elapsed time
// ===========================================================================
function initReadingTimer() {
  const el = document.getElementById("reading-timer");
  if (!el || !el.dataset.start) return;

  const start = new Date(el.dataset.start).getTime();

  const tick = () => {
    const s   = Math.floor((Date.now() - start) / 1000);
    const h   = Math.floor(s / 3600);
    const m   = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    el.textContent = h
      ? ` (${h}h ${String(m).padStart(2, "0")}m ${String(sec).padStart(2, "0")}s)`
      : ` (${m}m ${String(sec).padStart(2, "0")}s)`;
  };

  tick();
  setInterval(tick, 1000);
}



// ===========================================================================
// Navigation — NProgress top bar + page exit/entry handling
// ===========================================================================
function initNavigation() {
  /*
   * Triggers NProgress on every navigation that causes a full page load.
   * Skips:
   *   - Same-page anchor links  (#section)
   *   - External links          (different origin)
   *   - Links with target       (target="_blank")
   *   - Download links          (download attribute)
   *   - javascript: / mailto: / tel: hrefs
   *   - Links already handled by fetch (modal creation buttons)
   *
   * NProgress is stopped by the pageshow event (fires even on bfcache restore).
   */

  if (typeof NProgress === "undefined") return;

  NProgress.configure({ showSpinner: false, trickleSpeed: 80 });

  function shouldIntercept(anchor) {
    if (!anchor) return false;
    const href = anchor.getAttribute("href") || "";
    if (!href || href.startsWith("#"))      return false;   // anchor-only
    if (href.startsWith("javascript:"))     return false;
    if (href.startsWith("mailto:"))         return false;
    if (href.startsWith("tel:"))            return false;
    if (anchor.hasAttribute("download"))    return false;
    if (anchor.target && anchor.target !== "_self") return false;
    // External link
    try {
      const url = new URL(href, location.origin);
      if (url.origin !== location.origin)   return false;
    } catch (_) {
      return false;
    }
    return true;
  }

  // Intercept all qualifying link clicks
  document.addEventListener("click", (e) => {
    const anchor = e.target.closest("a");
    if (!anchor || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (!shouldIntercept(anchor)) return;
    NProgress.start();
  });

  // Intercept form submits (page-navigating forms only — not fetch forms)
  document.addEventListener("submit", (e) => {
    const form = e.target;
    // Skip forms intercepted by confirm modal or fetch (inline creation)
    if (form.dataset.confirmTitle || form.dataset.confirm) return;
    if (form.id === "bookForm" || form.id === "authorForm" || form.id === "categoryForm") return;
    NProgress.start();
  });

  // Stop progress when page is fully shown (handles bfcache too)
  window.addEventListener("pageshow", () => NProgress.done());

  // Handle browser back/forward — NProgress may still be running
  window.addEventListener("popstate", () => NProgress.done());
}

// ===========================================================================
// Boot
// ===========================================================================
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();   // must run first — starts NProgress before other inits
  initMessages();
  initNavbar();
  initConfirmModal();
  initLoadingStates();
  initLoginForm();
  initRegisterForm();
  initBookSearch();
  initBorrowForm();
  initAdminForms();
  initInlineCreation();   // ← new
  initImagePreview();
  initReadingTimer();
});
