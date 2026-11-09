# Font Sources — the 3 launch style packs

> **Backup font access + build reference.** The kit still installs these fonts for the creator; this is the
> "where each font came from" fallback — if an install hiccups, or they want a font in Canva or elsewhere,
> the source link is right here. License column is kept as a future note for when the self-serve kit sells
> to strangers. Companion to `style-packs.json` (pack
> config). Last sourced: 2026-08-02.

## The one rule this doc exists to enforce

Winging the EULA on **the creator's own IP** is her call. But **shipping someone else's font FILE is a different
exposure no EULA covers.** Two clean ways to use a font in the kit:

1. **Ship the file** — only OK if the font is **OFL / public-domain / the creator-owned.** (Google Fonts = safe.)
2. **Don't ship the file; let the creator's own CapCut supply it** — the font lives in CapCut's in-app
   library, the creator picks it natively, and the engine references it by CapCut `resource_id` instead of
   copying a `.ttf` into the kit. Safe for restricted fonts, because we never redistribute anything.

⚠️ **`packbuild.py` currently does #1 for every font** (`capcut_font_path()` → `shutil.copy` into the
creator's CapCut Fonts dir). For any font marked ❌ below, that copy is redistribution of a paid/restricted
file. Those packs need to move to the #2 path (resource_id, no file shipped) **or** swap to an OFL
lookalike before the self-serve kit ships.

## Source table

| Font | File | Pack · role | Source (link) | License | Ship the file? |
|---|---|---|---|---|---|
| **Playfair Display** | `PlayfairDisplay-VF.ttf` | Editorial · headline | [Google Fonts](https://fonts.google.com/specimen/Playfair+Display) | OFL | ✅ yes |
| **Poppins** | `Poppins-Black/SemiBold.ttf` | Editorial · caption | [Google Fonts](https://fonts.google.com/specimen/Poppins) | OFL | ✅ yes |
| **Inter** | `Inter-Black.otf`, `Inter-Medium.ttf` | Butter · headline+takeover / caption | [Google Fonts](https://fonts.google.com/specimen/Inter) · [Fontsource](https://fontsource.org/fonts/inter) | OFL | ✅ yes |
| **Space Grotesk** | `SpaceGrotesk-VF.ttf` | Butter · label | [Google Fonts](https://fonts.google.com/specimen/Space+Grotesk) | OFL | ✅ yes |
| **Noto Sans Adlam** | `NotoSansAdlam.ttf` | Playful · caption/accent fallback (used until Ugly Dave is in CapCut) | [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Sans+Adlam) | OFL | ✅ yes |
| **Prosecco and Baguette** | `Prosecco.ttf` | Editorial · accent/takeover | [PeachCreme](https://www.peachcreme.com/products/prosecco-and-baguette-quirky-font) · [Creative Market](https://creativemarket.com/PeachCremeFonts/92091908-Prosecco-and-Baguette-Script-Font) · [MyFonts](https://www.myfonts.com/collections/prosecco-and-baguette-font-peach-creme) | **Paid commercial** (Gulya Yeap / PeachCreme). Demo not allowed in final use. | ❌ NO — CapCut-native path only |
| **Soup Du Jour** (+ Hollow) | `SoupDuJour.ttf`, `SoupDuJourHollow.ttf` | Playful · headline + thought bubble (solid) / takeover (hollow) | [dafont](https://www.dafont.com/soup-du-jour.font) · [MyFonts](https://www.myfonts.com/collections/soup-du-jour-font-pizzadudedk/) | **Restricted** — Pizzadude.dk (Jakob Fischer). "Distribution prohibited without permission." Free demo = non-commercial. | ❌ NO — CapCut-native path only |
| **Ugly Dave** | `UglyDaveAlternates.otf` | Playful · caption + accent caption + eyebrow | CapCut's own font library (free in CapCut); the engine finds it there by name | The file itself is never included in the kit: it comes from CapCut | ❌ NO — CapCut-native path only |
| **Bloop** | `Bloop.ttf` | Butter · accent/eyebrow | [dafont](https://www.dafont.com/bloop.font) — ⚠️ exact "Bloop" UNCONFIRMED (several fonts share the name; the file was captured from CapCut's cache) | Free personal use only / non-commercial (for the dafont one) | ❌ NO until the exact foundry is confirmed |

## Where each pack stands

- **Butter** — headline/takeover Inter Black + caption Inter Medium (both OFL ✅, ship the files). Only the
  **Bloop** eyebrow accent is unclear → confirm or swap. **Caption-font note:** the caption is the STATIC
  `Inter-Medium.ttf` (weight 500), NOT the variable `Inter-VF.ttf`. `Inter-VF.ttf` was retired as the caption
  font because CapCut resolved the variable font to its lightest instance, "Inter Thin"; the static Medium
  renders correctly.
- **Editorial** — headline Playfair (✅). **Prosecco** accent is paid ❌ → CapCut-native only, or swap to an
  OFL script.
- **Playful** — captions, accent and eyebrow are **Ugly Dave** ❌ → CapCut-native only; the bundled Noto Sans Adlam (✅)
  stands in until it is added. **Soup Du Jour** (both variants) is restricted ❌ → CapCut-native only.

## Action items before the self-serve kit ships

1. **Prosecco / Soup Du Jour** — keep in the packs (creators have them in CapCut natively) but make the engine
   reference them by CapCut `resource_id` and **stop shipping the captured `.ttf`.** No file in the kit.
2. **Bloop** — identify the exact font; if it's the personal-use dafont one, swap the Butter accent to an OFL
   lookalike (it's the only non-clear font in an otherwise-safe pack).

> Fonts confirmed shippable as files today: **Playfair Display, Poppins, Noto Sans Adlam, Inter, Space Grotesk**
> (all OFL). Everything else is either creator-supplied-via-CapCut or needs a swap.
