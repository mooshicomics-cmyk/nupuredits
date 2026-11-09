# hf-reel — generic HyperFrames composition template

The GENERIC scaffold for a reel's animated-type composition. `build-hf-captions.py` copies this into
`projects/<JOB>/hf-captions/` when that folder isn't set up yet, then writes `index.html` into it.

Composition id is the generic `reel` (override with the `COMP` env var). This template contains NO
personal reel, footage, or fonts — the engine resolves the chosen style pack's fonts at build time
(see `product/stylepack.py` + `product/creative-vault/style-packs.json`). Never scaffold a reel by
copying someone's personal `projects/<their-reel>/` folder.
