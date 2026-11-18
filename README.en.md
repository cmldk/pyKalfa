# pyKalfa

[Türkçe](README.md) · **English** · [Français](README.fr.md)

A pyRevit extension for Revit. Extracts parcel and building geometry from
cadastral data, and builds a floored building prototype from a Polycam scan.

## Features

| Button | What it does |
| --- | --- |
| **Parsel/Bina GIS** | In Wallonia and Flanders, fetches parcel boundaries, buildings and parcel numbers from the regional GIS services by address or CaPaKey and draws them in the active view: parcel boundaries (`DetailLine`), buildings (`FilledRegion`), road edges, street names and parcel numbers (`TextNote`). |
| **Rölöve Prototip** | Tidied, floored quick prototype from the same Polycam scan: square corners, exterior walls aligned between storeys, a floor slab on every level. |

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
startup. This takes a few minutes and shows a progress bar. It does not run again on later startups.

> Optional: you can also download it via **Code → Download ZIP**, rename
> the folder to `pyKalfa.extension`, and add its **parent** folder under
> pyRevit → Settings → *Custom Extension Folders*.

## Usage

### Parsel/Bina GIS — parcels and buildings from the geoportal

For **Wallonia** and **Flanders**; an internet connection is required.
There are no images, no scale and no OCR. Address candidates from both
regions come in one list (each row names its region); a CaPaKey is looked
up in Wallonia first, then in Flanders. Brussels is not supported.

| | Wallonia | Flanders |
|---|---|---|
| Address | ICAR (SPW) | Digitaal Vlaanderen (geolocation) |
| Parcel | SPW `CADMAP_PARCELLES` | Adpf (administrative parcels) |
| Building | SPW PICC | GRB `GBG` |
| Road / sidewalk edge | PICC "Voirie - Ligne" | GRB `WGO` |
| Street name | PICC road axis | GRB `Wegsegment` |

Parcel numbers are decoded from the CaPaKey in both regions.

1. Switch to a **plan, detail, section or elevation** view.
2. **pyKalfa** → **Parsel / Bina** → **Parsel/Bina GIS**.
3. In order:
   - type an **address** (e.g. `Rue du Parc 4, 4577 Modave`,
     `Steenstraat 10, 8000 Brugge`) or a
     **CaPaKey** (e.g. `92053D0515/00B002`)
   - pick one of the candidates found (you are asked again if none is
     found)
   - enter **how many metres** around the parcel to include (default 80,
     maximum 200)
   - a separate line style for the **selected parcel's outer boundary**
     (if skipped, the other parcels' style is used; its number is written
     like the others)
   - the **style choices**: parcel lines, frame
     (or *"Cerceve cizme"*), road and sidewalk edges (or *"Yol cizme"*),
     Text Note Type for street names (or *"Sokak adi yazma"*), building
     Filled Region Type, parcel number
     Text Note Type, north arrow (or *"Kuzey oku ekleme"*)
4. The data is fetched in a few seconds behind a progress bar, then drawn,
   and a summary opens.

> The drawing area is the selected parcel's bounding box grown by the
> margin; the frame is that rectangle, and neighbouring parcels and
> buildings that cross it are clipped at the frame. The origin is the
> frame's bottom-left corner; the data is
> north-up, so the north arrow is placed at 0°.

> Road and sidewalk edges come from the PICC "Voirie - Ligne" layer (road
> edge, path edge, back edge of the sidewalk; kerb stones, parking bays,
> crossings etc. are not drawn). Street names come from the road axes: each
> name once, at the middle of its longest axis part, rotated along the road
> and centred. Rural areas where the PICC is not detailed may have no road
> lines.

> Parcel numbers come from the data, so there are no OCR errors. A check
> image is left at `output/revit_input_preview.png`.
>
> In Flanders, road edges are the three GRB `WGO` types: carriageway edge,
> pedestrian/cycle zone (sidewalk) border and unpaved zone border.
>
> Source — Wallonia: Plan parcellaire cadastral © AGDP/SPF Finances, via SPW ;
> Bâtiments, voirie © SPW (PICC_VDIFF). Flanders: Adpf © AAPD/FOD Financiën,
> via Digitaal Vlaanderen ; GRB © Digitaal Vlaanderen.

### Rölöve Prototip — building prototype from a Polycam scan

Builds a **quick starting massing** from a Polycam (iPhone/iPad LiDAR) scan
into an empty project: walls, floor slabs, doors/windows and named rooms.
It is not a survey; fine dimensions are corrected by hand later.

**Required inputs** (Polycam Basic plan):

| Input | File | In Polycam |
|---|---|---|
| **Input 1** – Floor plan | `.dxf` (or the floor-plan `.zip`) | Floor plan → DXF |
| **Input 2** – Room list | `.csv` (taken from the floor-plan zip if it is there) | Floor plan → CSV |
| **Input 3** – Point cloud | `.laz` / `.las` — **georeferenced off** | Point cloud → LAS |
| **Input 4** – 3D model | `.glb` | Mesh → GLTF |

Polycam's OBJ (mesh) zip is not Input 1; it contains no DXF.

- **Measurement:** each storey's walls are fitted to the scan and levels
  are measured from it (main floor = 0.00).
- **Tidying:** nearly square corners (up to 5°) become 90°, exterior walls
  closer than 15 cm between storeys snap onto one line. More skewed walls
  are left as scanned; corners closed in the scan stay closed.
- **Floors:** one slab per level (you pick the type); top face at the
  level, out to the exterior face of the exterior walls. A level's slab
  covers that storey and the storey below it (an uncovered part is
  assumed to be a flat roof).
- **Walls** are attached to the next level and stop under its slab; the
  top storey's walls keep the scanned height. Exterior walls grow
  **outward from the scanned interior face**. If you change the floor type
  later, update the walls' top offset too.
- No roof, stairs or stair openings.

1. Open an empty project (the Architectural template is fine).
2. **pyKalfa** → **Duvar** → **Rolove Prototip** and pick **Input 1**.
   Inputs 2–4 with the same name in the same folder are suggested; the
   inputs window marks each one `OK` / `EKSIK` (missing), and any wrong or
   missing one can be picked with "Input N sec / degistir".
3. The summary shows the levels and the tidying counts; levels can be
   edited. A `prototip_preview_katN.png` is written per storey.
4. Pick the exterior wall type **once**, one type per interior thickness
   group, the door and window families (or "Opening kullan") and the
   **floor type**. One **Ctrl+Z** undoes everything.

Every wall/door/window carries a `pyKalfa Tarama Durumu` parameter:
**olculdu** (measured from the scan), **duzeltildi** (position corrected
from the scan or by tidying; the deviation is stored in cm), **varsayildi**
(default or unverified — check it). Use a view filter to colour them.

Running the button again in the same project is safe: elements created
earlier are kept, ones you deleted do not come back, and only missing ones
are added.

## License

[MIT](LICENSE)
