# Monroe Mountain — Aspen Atlas

Two pages over Monroe Mountain (Fishlake National Forest, Utah):

- **`index.html`** — results landing page with summary statistics, charts,
  and prose slots you can fill in.
- **`map.html`** — the interactive map with four predictive raster
  layers (aspen density, high-regen probability, phenology, burn
  severity) and an NLCD forest-mask toggle.

Both pages cross-link via the top nav.

## Adding your own writing

The home page (`index.html`) has labeled placeholders called "prose
slots" between every section. Open `index.html` in any text editor and
search for `prose-slot`. Each block looks like this:

```html
<div class="prose-slot">
  Hero / introduction prose goes here — what the project is, who it's for…
</div>
```

Replace the placeholder text inside the `<div>` with your own writing
(plain HTML — `<p>` tags for paragraphs, `<em>` for italics, `<a>` for
links). Or, if you want the slot styling to disappear once you've added
content, change the surrounding tag from `<div class="prose-slot">` to
just `<p>`.

The numbers in the charts and tables are hard-coded into `index.html` —
look for the section labeled `<!-- =========== Probability distribution
=========== -->` etc. and you'll find the values inline. To update them,
edit the SVG `text` elements and the `<rect>` / `<line>` / `<path>`
coordinates that depend on them.

## Run it locally

The site is a plain static folder — no build step. You just need to serve it
over HTTP (browsers won't load PNGs/JSON via `file://` for security reasons).

From this folder:

```bash
# Python 3
python -m http.server 8000

# or Node
npx serve .
```

Then open http://localhost:8000

## Host it for free

Drop the entire folder into any of these:

- **GitHub Pages** — push to a repo, enable Pages in settings.
- **Netlify Drop** — drag the folder onto https://app.netlify.com/drop.
- **Cloudflare Pages** — same idea, drag-and-drop deployment.

## What's in the folder

```
index.html         # the site (HTML + CSS + JS, single file)
manifest.json      # layer metadata (bounds, ranges, colormap names, file paths)
build_layers.py    # build script that produces the PNGs and manifest
layers/
  aspen_full.png        aspen_forest.png        # YlGn,    log scale
  regen_full.png        regen_forest.png        # viridis, linear 0–1
  phenology_full.png    phenology_forest.png    # RdYlGn,  diverging at 0
  severity_full.png     severity_forest.png     # RdBu_r,  diverging at 0
```

Each layer ships in two variants. The "Forest only" toggle on the site
swaps between them at the URL level — `_full` shows the entire study
extent, `_forest` masks pixels outside NLCD classes 41 / 42 / 43.

The `aspen` and `regen` layers were already forest-restricted by your R
pipeline (`stack_forest`), so their two PNGs look identical. The toggle
is most useful for `phenology` and `severity`, which span the full
study extent in their `_full` form and shrink down to the forest
footprint in `_forest`.

## Geographic context

Source rasters: 30 m grid in **EPSG:32612** (UTM Zone 12N).
WGS84 bounding box of the modeling extent:

| | latitude | longitude |
|---|---|---|
| south-west | 38.317° N | 112.164° W |
| north-east | 38.766° N | 111.818° W |

That's the southern part of the Sevier Plateau / Monroe Mountain massif.

## Color choices

| Layer | Colormap | Why |
|---|---|---|
| Aspen Density | YlGn (log scale) | Single-hue green ramp reads as "vegetation density"; log scale tames the long right tail (1 → 16,000 stems/ha) |
| High Regen Probability | viridis | Perceptually uniform, colorblind-safe; the canonical 0–1 ramp |
| Phenology | RdYlGn (diverging at 0) | Centered at zero so red ↔ green carry the sign of the phenological anomaly |
| Burn Severity (RdNBR) | RdBu_r (diverging at 0) | Fire-ecology convention: red = high severity, blue = unburned/recovery |

## About your TIFs and georeferencing

Your uploaded files were **already proper GeoTIFFs** in EPSG:32612 — no
re-georeferencing needed. The site's build script just reprojected them to
Web Mercator and rendered colorized PNGs.

If you ever produce an array in R that *isn't* georeferenced and want to
turn it into a GeoTIFF, here's the pattern:

```r
library(terra)

# Suppose `m` is a numeric matrix or array, and you know the spatial
# extent + CRS of the cells.
m <- matrix(runif(988 * 1648), nrow = 1648, ncol = 988)

r <- rast(
  m,
  extent = ext(398880, 428520, 4241670, 4291110),  # xmin, xmax, ymin, ymax
  crs    = "EPSG:32612"                            # UTM Zone 12N
)

# nodata convention used by the build script:
NAflag(r) <- -9999

writeRaster(
  r,
  "Monroe_NewLayer.tif",
  overwrite = TRUE,
  datatype  = "FLT4S",     # 32-bit float
  gdal      = c("COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3")
)
```

The four parameters that make a TIF a *Geo*TIFF:
1. **`extent`** — the xmin/xmax/ymin/ymax of the raster in projected units
2. **`crs`** — the coordinate reference system (here EPSG:32612)
3. **Cell resolution** — implied by extent ÷ dimensions (here 30 m × 30 m)
4. **`NAflag`** — sentinel value for missing data so the renderer can mask it

To rebuild the site after replacing or adding a TIF, re-run the Python
build script (see `build_layers.py` in your conversation history) — it'll
regenerate the PNGs and `manifest.json`.

## Adding a new layer

1. Add an entry to the `LAYERS` list in `build_layers.py` — file name,
   colormap (`YlGn`, `viridis`, `RdYlGn`, `RdBu_r`, `magma`, `cividis`, etc.),
   and norm (`linear`, `log`, or `diverging`).
2. Re-run the script. It writes a new PNG to `layers/` and updates
   `manifest.json`.
3. Refresh the page. The layer appears automatically — `index.html` reads
   `manifest.json` at runtime, so no HTML edits needed.

## Troubleshooting

- **Map area is empty / fonts look generic** — you opened `index.html`
  directly in the browser. Use a local server instead (see "Run it locally"
  above).
- **Map shows but overlays don't** — check the browser DevTools network
  panel for 404s on the PNGs in `layers/`.
- **Basemap tiles don't load** — the Esri tile servers occasionally
  rate-limit. Try the "None" basemap; the colorized overlays themselves are
  self-contained and won't be affected.
