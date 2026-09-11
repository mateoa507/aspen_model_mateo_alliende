"""
Reproject each TIF from EPSG:32612 to EPSG:3857 (Web Mercator),
colorize with an appropriate colormap, and save as PNG with alpha.
Also produce a forest-masked variant of every layer using
Monroe_ForestMask.tif (1 = forest, 0 = non-forest).
"""
import os
import json
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from PIL import Image

UPLOADS = '/mnt/user-data/uploads'
OUT_DIR = '/home/claude/site'
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(f'{OUT_DIR}/layers', exist_ok=True)

FOREST_MASK_FILE = 'Monroe_ForestMask.tif'  # binary: 1=forest, 0=non-forest, optional 255=nodata

LAYERS = [
    {
        'file': 'Monroe_Aspen_ContinuousDensity.tif',
        'key': 'aspen',
        'name': 'Aspen Density',
        'cmap': 'YlGn',
        'norm': 'log',
        'units': 'stems/ha (modeled)',
        'description': 'Continuous aspen stem density. Higher = denser aspen stands.',
    },
    {
        'file': 'Monroe_HighRegen_Probability.tif',
        'key': 'regen',
        'name': 'High Regen Probability',
        'cmap': 'viridis',
        'norm': 'linear',
        'vmin': 0.0,
        'vmax': 1.0,
        'units': 'probability (0–1)',
        'description': 'Predicted probability of high post-fire regeneration.',
    },
    {
        'file': 'Monroe_Phenology.tif',
        'key': 'phenology',
        'name': 'Phenology',
        'cmap': 'RdYlGn',
        'norm': 'diverging',
        'center': 0.0,
        'pct_clip': (1, 99),
        'units': 'index (centered at 0)',
        'description': 'Phenological signal centered at 0. Negative = browner/earlier; positive = greener/later.',
    },
    {
        'file': 'Monroe_RdNBR_Severity.tif',
        'key': 'severity',
        'name': 'Burn Severity (RdNBR)',
        'cmap': 'RdBu_r',
        'norm': 'diverging',
        'center': 0.0,
        'pct_clip': (1, 99),
        'units': 'RdNBR (centered at 0)',
        'description': 'Relativized differenced Normalized Burn Ratio. Red = higher severity, blue = unburned/recovery.',
    },
]


def reproject_to_webmercator(src_path, resampling=Resampling.bilinear):
    """Open a source raster, reproject to EPSG:3857, return (array, dst_transform, width, height, src_meta)."""
    with rasterio.open(src_path) as src:
        dst_crs = 'EPSG:3857'
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        nodata = src.nodata
        # Initialize destination with nodata value, or NaN for floats
        if nodata is not None:
            dst_arr = np.full((height, width), nodata, dtype=src.dtypes[0])
        else:
            dst_arr = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            resampling=resampling,
            src_nodata=nodata,
            dst_nodata=nodata,
        )
        wgs = transform_bounds(src.crs, 'EPSG:4326', *src.bounds, densify_pts=21)
    return {
        'array': dst_arr,
        'transform': transform,
        'width': width,
        'height': height,
        'nodata': nodata,
        'wgs_bounds': wgs,  # (west, south, east, north)
    }


# -----------------------------------------------------------------------------
# 1) Reproject the forest mask once at the resolution of the first layer's
#    Web-Mercator grid. We reproject each layer independently below, and they
#    share the same source grid (988x1648 in 32612), so their dst grids will
#    match too — we'll re-reproject the mask if any layer's dst differs.
# -----------------------------------------------------------------------------
mask_path = os.path.join(UPLOADS, FOREST_MASK_FILE)
have_mask = os.path.exists(mask_path)
if have_mask:
    print(f'Forest mask present: {mask_path}')
else:
    print('No forest mask found; will skip forest variants.')


# We'll cache reprojected masks by (width, height) of the destination grid
mask_cache = {}

def get_forest_mask_for_grid(width, height, dst_transform):
    """Reproject the binary forest mask onto a target Web-Mercator grid using nearest neighbor."""
    key = (width, height)
    if key in mask_cache:
        return mask_cache[key]

    with rasterio.open(mask_path) as src:
        # Force the same destination grid as the layer
        dst_arr = np.full((height, width), 0, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs='EPSG:3857',
            resampling=Resampling.nearest,  # preserve binary classes
            src_nodata=src.nodata,
            dst_nodata=0,                    # treat nodata as non-forest
        )
    forest = (dst_arr == 1)
    mask_cache[key] = forest
    return forest


# -----------------------------------------------------------------------------
# 2) Process each layer
# -----------------------------------------------------------------------------
manifest = {'layers': [], 'has_forest_mask': have_mask}

for spec in LAYERS:
    src_path = os.path.join(UPLOADS, spec['file'])
    print(f"\nProcessing {spec['file']} ...")
    r = reproject_to_webmercator(src_path)
    dst_arr = r['array']
    height, width = dst_arr.shape
    nodata_val = r['nodata']

    valid_mask = (
        (dst_arr != nodata_val) & np.isfinite(dst_arr)
        if nodata_val is not None else np.isfinite(dst_arr)
    )
    valid = dst_arr[valid_mask]
    print(f"  Valid pixels: {valid.size:,}; range {float(valid.min()):.3f} .. {float(valid.max()):.3f}")

    # Compute color norm
    if spec['norm'] == 'log':
        positive = valid[valid > 0]
        vmin = max(float(np.percentile(positive, 1)), 1e-3)
        vmax = float(np.percentile(positive, 99))
        norm = mcolors.LogNorm(vmin=vmin, vmax=vmax, clip=True)
    elif spec['norm'] == 'diverging':
        lo, hi = spec.get('pct_clip', (1, 99))
        a = float(np.percentile(np.abs(valid), max(lo, hi)))
        vmin, vmax = -a, a
        norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=spec.get('center', 0.0), vmax=vmax)
    else:
        vmin = float(spec.get('vmin', float(np.percentile(valid, 1))))
        vmax = float(spec.get('vmax', float(np.percentile(valid, 99))))
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)

    cmap = cm.get_cmap(spec['cmap'])
    normed = norm(np.ma.masked_where(~valid_mask, dst_arr))
    rgba = cmap(normed)
    rgba = (rgba * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid_mask, 255, 0)

    # ---- write FULL variant ----
    full_png = f'{OUT_DIR}/layers/{spec["key"]}_full.png'
    Image.fromarray(rgba, mode='RGBA').save(full_png, optimize=True)
    print(f"  Wrote {full_png}")

    # ---- write FOREST variant ----
    forest_png = None
    if have_mask:
        forest = get_forest_mask_for_grid(width, height, r['transform'])
        rgba_forest = rgba.copy()
        # zero alpha where non-forest
        rgba_forest[..., 3] = np.where(valid_mask & forest, 255, 0).astype(np.uint8)
        forest_png = f'{OUT_DIR}/layers/{spec["key"]}_forest.png'
        Image.fromarray(rgba_forest, mode='RGBA').save(forest_png, optimize=True)
        n_forest = int(forest.sum())
        n_valid_forest = int((valid_mask & forest).sum())
        print(f"  Wrote {forest_png} (forest pixels visible: {n_valid_forest:,} of {valid_mask.sum():,} valid)")

    west, south, east, north = r['wgs_bounds']
    manifest['layers'].append({
        'key': spec['key'],
        'name': spec['name'],
        'files': {
            'full':   f'layers/{spec["key"]}_full.png',
            'forest': f'layers/{spec["key"]}_forest.png' if have_mask else None,
        },
        'cmap': spec['cmap'],
        'norm': spec['norm'],
        'vmin': float(vmin),
        'vmax': float(vmax),
        'center': float(spec.get('center', 0.0)) if spec['norm'] == 'diverging' else None,
        'units': spec['units'],
        'description': spec['description'],
        'bounds': {
            'west':  float(west),
            'south': float(south),
            'east':  float(east),
            'north': float(north),
        },
        'width':  int(width),
        'height': int(height),
    })

# Top-level bounds + center
b = manifest['layers'][0]['bounds']
manifest['bounds'] = b
manifest['center'] = {
    'lat': (b['south'] + b['north']) / 2.0,
    'lon': (b['west'] + b['east']) / 2.0,
}
manifest['crs_source'] = 'EPSG:32612'
manifest['crs_display'] = 'EPSG:3857 / WGS84 bounds for overlay'

with open(f'{OUT_DIR}/manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)
print('\nWrote manifest.json')
