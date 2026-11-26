/* Raju Anna: inline SVG shopkeeper. Mood is a data attribute; all expressions live in common.css. */
(function () {
  let uid = 0;
  const svg = (id) => `<svg viewBox="0 0 240 270" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Raju Anna, the shopkeeper">
<defs>
  <pattern id="chk${id}" width="12" height="12" patternUnits="userSpaceOnUse">
    <rect width="12" height="12" fill="#fff8f0"/><rect width="6" height="6" fill="#d8453f"/><rect x="6" y="6" width="6" height="6" fill="#d8453f"/>
  </pattern>
</defs>
<g class="bob">
  <path d="M14 270 C14 214 58 194 120 194 C182 194 226 214 226 270 Z" fill="#f4f0e6"/>
  <path d="M62 236 C82 218 100 212 120 212" stroke="#dcd5c3" stroke-width="3" fill="none"/>
  <rect x="100" y="164" width="40" height="40" rx="12" fill="#c98f62"/>
  <path d="M96 192 L120 238 L144 192 Z" fill="#c98f62"/>
  <path d="M86 190 L120 244 L100 188 Z" fill="#e7e0cf"/>
  <path d="M154 190 L120 244 L140 188 Z" fill="#e7e0cf"/>
  <path d="M20 270 C22 226 52 204 98 194 L112 214 C84 224 66 242 62 270 Z" fill="url(#chk${id})" stroke="#b9322d" stroke-width="2.5"/>
  <rect x="156" y="232" width="38" height="34" rx="4" fill="#ebe5d6" stroke="#d3ccb9" stroke-width="2"/>
  <rect x="171" y="220" width="6" height="26" rx="2" fill="#2a5bd7"/>
  <rect x="171" y="220" width="6" height="5" rx="2" fill="#ffd45e"/>

  <ellipse cx="62" cy="106" rx="9" ry="14" fill="#cf966a"/>
  <ellipse cx="178" cy="106" rx="9" ry="14" fill="#cf966a"/>
  <ellipse cx="120" cy="104" rx="58" ry="70" fill="#d9a273"/>
  <path d="M64 88 C54 40 88 26 120 26 C152 26 186 40 176 88 C172 62 150 50 120 50 C90 50 68 62 64 88 Z" fill="#22222a"/>
  <path d="M94 36 C108 29 134 29 148 36 C134 37 108 39 94 36 Z" fill="#6f6f80"/>

  <g class="eyes">
    <g class="eyeball"><circle cx="94" cy="98" r="14" fill="#fff"/><circle data-part class="pupil" cx="94" cy="100" r="5.6" fill="#2b1b12"/><circle cx="92" cy="98" r="1.8" fill="#fff"/></g>
    <g class="eyeball"><circle cx="146" cy="98" r="14" fill="#fff"/><circle data-part class="pupil" cx="146" cy="100" r="5.6" fill="#2b1b12"/><circle cx="144" cy="98" r="1.8" fill="#fff"/></g>
    <circle data-part class="lid" cx="94" cy="98" r="14" fill="#d9a273"/>
    <circle data-part class="lid" cx="146" cy="98" r="14" fill="#d9a273"/>
    <path class="eye-happy" d="M80 102 Q94 86 108 102" stroke="#2b1b12" stroke-width="5" fill="none" stroke-linecap="round"/>
    <path class="eye-happy" d="M132 102 Q146 86 160 102" stroke="#2b1b12" stroke-width="5" fill="none" stroke-linecap="round"/>
  </g>
  <g fill="rgba(190,225,255,.2)" stroke="#4a3320" stroke-width="4.5">
    <circle cx="94" cy="98" r="17"/><circle cx="146" cy="98" r="17"/>
  </g>
  <path d="M111 95 Q120 89 129 95" stroke="#4a3320" stroke-width="4.5" fill="none"/>
  <path d="M77 94 L66 92 M163 94 L174 92" stroke="#4a3320" stroke-width="4" fill="none" stroke-linecap="round"/>
  <path data-part class="brow brow-l" d="M76 74 Q94 64 112 72" stroke="#22222a" stroke-width="7" fill="none" stroke-linecap="round"/>
  <path data-part class="brow brow-r" d="M128 72 Q146 64 164 74" stroke="#22222a" stroke-width="7" fill="none" stroke-linecap="round"/>

  <path d="M120 106 C109 128 107 136 120 138 C133 136 131 128 120 106 Z" fill="#c68d60"/>
  <circle class="blush" cx="78" cy="128" r="10" fill="#ff7a8a"/><circle class="blush" cx="162" cy="128" r="10" fill="#ff7a8a"/>

  <g class="mouths" stroke="#6b2a18" stroke-width="5" fill="none" stroke-linecap="round">
    <path class="m m-flat" d="M104 164 H136"/>
    <path class="m m-side" d="M106 165 Q122 161 136 156"/>
    <path class="m m-frown" d="M102 170 Q120 154 138 170"/>
    <path class="m m-smirk" d="M104 164 Q122 170 140 156"/>
    <g class="m m-laugh" stroke="none"><path d="M100 156 Q120 188 140 156 Z" fill="#5a1414"/><path d="M105 157 Q120 166 135 157 L133 162 Q120 170 107 162 Z" fill="#fff"/><ellipse cx="120" cy="173" rx="9" ry="4.5" fill="#ff7a92"/></g>
    <path class="m m-wail" d="M102 172 Q120 148 138 172 Q120 163 102 172 Z" fill="#5a1414" stroke="none"/>
    <g class="m m-shout" stroke="none"><ellipse cx="120" cy="164" rx="15" ry="12" fill="#5a1414"/><ellipse cx="120" cy="171" rx="9" ry="4.5" fill="#ff7a92"/></g>
  </g>
  <path d="M62 138 C78 114 106 122 120 134 C134 122 162 114 178 138 C168 156 142 146 120 144 C98 146 72 156 62 138 Z" fill="#1d1d25"/>
  <path d="M62 138 C53 139 51 150 60 154 M178 138 C187 139 189 150 180 154" stroke="#1d1d25" stroke-width="6" fill="none" stroke-linecap="round"/>

  <g class="tears" fill="#6ec8ff">
    <g transform="translate(80 118)"><path class="tear" d="M0 0 C-5 7 -5 12 0 12 C5 12 5 7 0 0 Z"/></g>
    <g transform="translate(160 118)"><path class="tear t2" d="M0 0 C-5 7 -5 12 0 12 C5 12 5 7 0 0 Z"/></g>
  </g>
  <g class="anger" transform="translate(174 44)"><path d="M0 -12 L4 -4 L12 -5 L6 2 L12 9 L3 7 L0 15 L-3 7 L-12 9 L-6 2 L-12 -5 L-4 -4 Z" fill="#ff4d6d"/></g>
</g>
</svg>`;

  function mount(el, mood) {
    if (!el.dataset.mounted) {
      el.innerHTML = svg(++uid);
      el.dataset.mounted = "1";
      el.classList.add("anna");
    }
    el.dataset.mood = mood || el.dataset.mood || "neutral";
  }

  window.Anna = {
    mount,
    mood(el, m) { if (el) { mount(el, m); } },
    mountAll() { document.querySelectorAll("[data-anna]").forEach((el) => mount(el)); },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", window.Anna.mountAll);
  else window.Anna.mountAll();
})();
