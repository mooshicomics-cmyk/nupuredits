// Builds one slide (carousel 1080x1350, story 1080x1920) from carousel.json. Shared by the editor, the export renderer and the checker.
// The look comes from state.theme (written by carousel.py from the chosen style pack): fonts + colors as CSS variables.
function loadThemeFonts(theme) {
  if (document.getElementById("cfonts")) return;
  const st = document.createElement("style"); st.id = "cfonts";
  // fonts are served by family: carousel.py resolved each one (bundled, the creator's CapCut, or a stand-in)
  st.textContent = Object.keys(theme.fonts).map(fam => `@font-face{font-family:${fam};src:url("/fonts/${fam}")}`).join("\n");
  document.head.append(st);
}
function buildSlide(state, i) {
  const d = state.slides[i], el = document.createElement("div"), theme = state.theme;
  loadThemeFonts(theme);
  el.className = "s " + d.kind + (state.format === "story" ? " story" : "");
  Object.entries(theme.vars).forEach(([k, v]) => el.style.setProperty("--" + k, v));
  el.style.setProperty("--ov", d.overlay ?? state.overlay);
  el.style.setProperty("--sh", d.shadow ?? state.shadow);
  if (d.kind === "photo") {
    const c = d.crop, img = document.createElement("img");
    img.className = "ph"; img.src = "/photos/" + encodeURIComponent(d.photo); img.draggable = false;
    img.style.width = (c.w * c.scale) + "px"; img.style.left = (-c.x) + "px"; img.style.top = (-c.y) + "px";
    const scrim = document.createElement("div"); scrim.className = "scrim";
    el.append(img, scrim);
  }
  el.insertAdjacentHTML("beforeend", d.content);
  return el;
}
