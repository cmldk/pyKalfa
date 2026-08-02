# pyKalfa

[Türkçe](README.md) · **English** · [Français](README.fr.md)

A pyRevit extension for Revit. Extracts parcel and building geometry from
cadastral images, and real walls from floor plan DXF files.

## Features

| Button | What it does |
| --- | --- |
| **Parsel/Bina Aktar** | Turns cadastral images (PNG) into Revit geometry: parcel boundaries as `DetailLine`, buildings as `FilledRegion`, parcel numbers as `TextNote`. |
| **Duvar Aktar** | Converts walls in a floor plan DXF into real Revit `Wall` elements. |

## Requirements

- Windows + Autodesk Revit
- [pyRevit](https://github.com/pyrevitlabs/pyRevit)
- [Python 3](https://www.python.org) — make sure **"Add python.exe to PATH"** is checked during setup

## Installation

1. In Revit, go to the **pyRevit** tab → **Extensions**.
2. Add a new extension using this URL:
   ```
   https://github.com/cmldk/pyKalfa.git
   ```
3. **Reload** pyRevit (or restart Revit).

The required Python packages are installed automatically on first
startup. This takes a few minutes (the OCR library is ~1-1.5 GB) and
shows a progress bar. It does not run again on later startups.

> Optional: you can also download it via **Code → Download ZIP**, rename
> the folder to `pyKalfa.extension`, and add its **parent** folder under
> pyRevit → Settings → *Custom Extension Folders*.

## Usage

### Parsel/Bina Aktar — parcels and buildings

1. Switch to a **plan, detail, section or elevation** view (it does not
   work in 3D views).
2. **pyKalfa** → **Parsel / Bina** → **Parsel/Bina Aktar**.
3. Provide the inputs as they are requested:
   - select the parcel image (PNG)
   - select the building image (PNG)
   - enter the map scale denominator (`500` for 1:500)
   - pick a **Line Style** for parcel boundaries
   - pick a **Filled Region Type** for buildings
   - pick a **Text Note Type** for parcel numbers
4. Image processing runs behind a progress bar; you are not asked
   anything during this step.
5. The geometry is drawn and a summary of created elements appears.

> Sample images are in the `assets/` folder (`parsel_500.png`,
> `bina_500.png`); your own images should look like these.

> Parcel numbers are read with OCR, which is about 80% accurate. Similar
> characters (G/6, A/4, B/8, S/5) may be confused — compare the result
> with the source image and correct it manually if needed.

### Duvar Aktar — walls from DXF

1. Switch to a **plan view** for the level where the walls belong.
2. **pyKalfa** → **Duvar** → **Duvar Aktar**.
3. Then:
   - select the **DXF file**
   - *(if needed)* confirm the drawing units, moving the drawing to the
     origin, or single-line mode
   - choose the **layer** — the tool suggests the most likely wall
     layer. Doors and windows are drawn exactly like walls, so the layer
     is the only thing that separates them; this step matters
   - set the **wall height** and pick a **Level** and **Wall Type**
4. Confirm, and when it finishes you get the number of created and
   failed walls plus the total length.

> The whole import is a single transaction: if you do not like the
> result, a single **Ctrl+Z** in Revit undoes all of it.

## License

[MIT](LICENSE)
