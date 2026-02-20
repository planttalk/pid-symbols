# automation-labs-pid-symbols

Tooling to classify P&ID SVG symbols and (optionally) generate augmented PNG datasets.

## Augmentation (PNG)

- Uses Albumentations on SVGs rendered at their intrinsic size.
- Skips `*_debug.svg` files.
- Writes PNGs only (no JSON and no registry).
- Output defaults to `<input>-augmented` when using `--augment` or `--augment-source`.

### Examples

```powershell
python main.py --augment --augment-count 5
python main.py --augment-source processed --augment-count 5
python main.py --augment-source completed --augment-count 5
```

