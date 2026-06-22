# Guide-driven peak integration

This branch adds a small standard-library Python package, `peak_processing`,
for turning unintegrated chromatogram points into integration instructions and
area calculations.

## Inputs

### Peak processing guide

Use the uploaded guide CSV now committed at:

```text
data/peak_processing_guide.csv
```

The parser reads:

- compound name
- integration notes
- smoothing, expected RT, RT window, minimum peak width/height, noise, baseline,
  and peak splitting settings
- before-integration categories
- after-integration categories

### Unintegrated samples

Provide a CSV with one row per chromatogram point. Required logical columns are:

```csv
sample_id,compound,retention_time,intensity
sample-001,Glycine,7.88,1004
sample-001,Glycine,7.89,1012
```

Common aliases such as `sample`, `rt`, `rt_min`, `abundance`, and `signal` are
also accepted.

### Manual integrations for accuracy checks

Optionally provide:

```csv
sample_id,compound,manual_area,start_rt_min,end_rt_min
sample-001,Glycine,12345.6,8.25,8.49
```

The output will include absolute and relative area error.

## Run

```bash
python3 -m peak_processing \
  --guide data/peak_processing_guide.csv \
  --samples path/to/unintegrated_samples.csv \
  --manual path/to/manual_integrations.csv \
  --output path/to/integration_results.csv
```

`--manual` is optional.

## Algorithm summary

For each `(sample_id, compound)` group, the integrator:

1. Loads the matching guide row.
2. Restricts points to the expected RT +/- RT half window.
3. Applies Gaussian smoothing using the guide width.
4. Estimates and subtracts a linear baseline from the edge windows.
5. Finds candidate apices above the guide minimum peak height and noise floor.
6. Classifies the observed before-integration peak state.
7. Uses guide notes/actions to select left, right, or closest candidate peak.
8. Sets integration bounds using threshold crossings and valley cuts around
   neighboring peaks.
9. Calculates baseline-corrected area with the trapezoidal rule.
10. Emits the selected algorithm steps and manual-area comparison fields.
