# pyKalfa

[Türkçe](README.md) · [English](README.en.md) · **Français**

Une extension pyRevit pour Revit. Elle extrait la géométrie des parcelles
et des bâtiments à partir de données cadastrales, et produit un prototype
de bâtiment avec dalles à partir d'un scan Polycam.

## Fonctionnalités

| Bouton | Rôle |
| --- | --- |
| **Parsel/Bina GIS** | En Wallonie et en Flandre, récupère les limites de parcelles, les bâtiments et les numéros de parcelles depuis les services SIG régionaux à partir d'une adresse ou d'un CaPaKey, et les dessine dans la vue active : limites de parcelles (`DetailLine`), bâtiments (`FilledRegion`), bords de voirie, noms de rues et numéros de parcelles (`TextNote`). |
| **Rölöve Prototip** | Prototype rapide, nettoyé et avec dalles, depuis le même scan Polycam : angles droits, murs extérieurs alignés d'un étage à l'autre, une dalle par niveau. |

## Prérequis

- Windows + Autodesk Revit
- [pyRevit](https://github.com/pyrevitlabs/pyRevit)
- [Python 3](https://www.python.org) — cochez bien **« Add python.exe to PATH »** lors de l'installation

## Installation

1. Dans Revit, onglet **pyRevit** → **Extensions**.
2. Ajoutez une nouvelle extension avec cette adresse :
   ```
   https://github.com/cmldk/pyKalfa.git
   ```
3. Faites **Reload** (ou redémarrez Revit).

Les paquets Python nécessaires sont installés automatiquement au premier
démarrage. Cela prend quelques minutes et une barre de progression
s'affiche. L'opération ne se
répète pas aux démarrages suivants.

> Facultatif : vous pouvez aussi télécharger le dossier via **Code →
> Download ZIP**, le renommer en `pyKalfa.extension` et ajouter son
> dossier **parent** dans pyRevit → Settings → *Custom Extension
> Folders*.

## Utilisation

### Parsel/Bina GIS — parcelles et bâtiments depuis le géoportail

Pour la **Wallonie** et la **Flandre** ; connexion internet requise. Pas
d'images, pas d'échelle, pas d'OCR. Les adresses candidates des deux
régions arrivent dans une même liste (chaque ligne indique sa région) ; un
CaPaKey est cherché d'abord en Wallonie, puis en Flandre. Bruxelles n'est
pas pris en charge.

| | Wallonie | Flandre |
|---|---|---|
| Adresse | ICAR (SPW) | Digitaal Vlaanderen (geolocation) |
| Parcelle | SPW `CADMAP_PARCELLES` | Adpf (parcelles administratives) |
| Bâtiment | PICC du SPW | GRB `GBG` |
| Bord de voirie / trottoir | PICC « Voirie - Ligne » | GRB `WGO` |
| Nom de rue | axe de voirie PICC | GRB `Wegsegment` |

Les numéros de parcelle sont décodés du CaPaKey dans les deux régions.

1. Passez dans une vue **en plan, de détail, en coupe ou en élévation**.
2. **pyKalfa** → **Parsel / Bina** → **Parsel/Bina GIS**.
3. Dans l'ordre :
   - saisissez une **adresse** (p. ex. `Rue du Parc 4, 4577 Modave`,
     `Steenstraat 10, 8000 Brugge`) ou
     un **CaPaKey** (p. ex. `92053D0515/00B002`)
   - choisissez l'un des résultats (la question est reposée si rien n'est
     trouvé)
   - indiquez **combien de mètres** autour de la parcelle inclure (80 par
     défaut, 200 au maximum)
   - un line style distinct pour la **limite extérieure de la parcelle
     choisie** (si ignoré, le style des autres parcelles est utilisé ; son
     numéro est écrit comme les autres)
   - les **choix de styles** : lignes de
     parcelles, cadre (ou *« Cerceve cizme »*), bords de voirie et de
     trottoir (ou *« Yol cizme »*), Text Note Type des noms de rues (ou
     *« Sokak adi yazma »*), Filled Region Type des
     bâtiments, Text Note Type des numéros, flèche du nord (ou *« Kuzey
     oku ekleme »*)
4. Les données sont récupérées en quelques secondes avec une barre de
   progression, puis dessinées ; un récapitulatif s'ouvre.

> La zone dessinée est le rectangle englobant de la parcelle choisie,
> agrandi de la marge ; le cadre est ce rectangle, et les parcelles et
> bâtiments voisins qui le traversent y sont découpés. L'origine est le
> coin inférieur gauche du cadre ; les
> données sont orientées nord en haut, la flèche du nord est donc posée à
> 0°.

> Les bords de voirie et de trottoir viennent de la couche PICC « Voirie -
> Ligne » (bord de voirie, bord de chemin, arrière du trottoir ; bordures,
> parkings, passages piétons, etc. ne sont pas dessinés). Les noms de rues
> viennent des axes de voirie : chaque nom une fois, au milieu de sa plus
> longue partie d'axe, tourné dans le sens de la rue et centré. En zone
> rurale peu détaillée au PICC, il peut n'y avoir aucune ligne de voirie.

> Les numéros de parcelles viennent des données : aucune erreur d'OCR.
> Une image de contrôle est laissée dans `output/revit_input_preview.png`.
>
> En Flandre, les bords de voirie sont les trois types GRB `WGO` : bord de
> chaussée, limite de zone piétons/cyclistes (trottoir) et limite de zone
> non revêtue.
>
> Source — Wallonie : Plan parcellaire cadastral © AGDP/SPF Finances, via
> SPW ; Bâtiments, voirie © SPW (PICC_VDIFF). Flandre : Adpf © AAPD/FOD
> Financiën, via Digitaal Vlaanderen ; GRB © Digitaal Vlaanderen.

### Rölöve Prototip — prototype de bâtiment depuis un scan Polycam

Produit une **volumétrie de départ rapide** à partir d'un scan Polycam
(LiDAR iPhone/iPad) dans un projet vide : murs, dalles, portes/fenêtres et
pièces nommées. Ce n'est pas un relevé ; les cotes fines se corrigent
ensuite à la main.

**Entrées nécessaires** (abonnement Polycam Basic) :

| Entrée | Fichier | Dans Polycam |
|---|---|---|
| **Input 1** – Plan d'étage | `.dxf` (ou le `.zip` du plan d'étage) | Floor plan → DXF |
| **Input 2** – Liste des pièces | `.csv` (repris du zip du plan s'il s'y trouve) | Floor plan → CSV |
| **Input 3** – Nuage de points | `.laz` / `.las` — **géoréférencement désactivé** | Point cloud → LAS |
| **Input 4** – Modèle 3D | `.glb` | Mesh → GLTF |

Le zip OBJ (maillage) de Polycam n'est pas l'Input 1 ; il ne contient pas
de DXF.

- **Mesure :** les murs de chaque étage sont calés sur le scan et les
  niveaux y sont mesurés (étage principal = 0.00).
- **Nettoyage :** les angles presque droits (jusqu'à 5°) passent à 90°, les
  murs extérieurs à moins de 15 cm d'un étage à l'autre sont alignés sur
  une même ligne. Les murs plus inclinés restent tels que scannés ; les
  angles fermés dans le scan restent fermés.
- **Dalles :** une dalle par niveau (type au choix) ; face supérieure au
  niveau, jusqu'à la face extérieure des murs extérieurs. La dalle d'un
  niveau couvre cet étage et celui du dessous (une partie non couverte est
  supposée être un toit plat).
- **Les murs** sont attachés au niveau supérieur et s'arrêtent sous sa
  dalle ; les murs du dernier étage gardent la hauteur scannée. Les murs
  extérieurs s'épaississent **vers l'extérieur depuis la face intérieure
  scannée**. Si vous changez ensuite le type de dalle, mettez aussi à jour
  le décalage supérieur des murs.
- Pas de toiture, d'escalier ni de trémie.

1. Ouvrez un projet vide (le gabarit Architectural suffit).
2. **pyKalfa** → **Duvar** → **Rolove Prototip** et choisissez l'**Input 1**.
   Les Inputs 2–4 de même nom dans le même dossier sont proposés ; la
   fenêtre des entrées marque chacune `OK` / `EKSIK` (manquante), et une
   entrée erronée ou manquante se choisit avec « Input N sec / degistir ».
3. Le résumé affiche les niveaux et les chiffres du nettoyage ; les niveaux
   sont modifiables. Un `prototip_preview_katN.png` est écrit par étage.
4. Choisissez le type de mur extérieur **une fois**, un type par groupe
   d'épaisseur intérieure, les familles de portes et fenêtres (ou
   « Opening kullan ») et le **type de dalle**. Un seul **Ctrl+Z** annule
   tout.

Chaque mur/porte/fenêtre porte le paramètre `pyKalfa Tarama Durumu` :
**olculdu** (mesuré dans le scan), **duzeltildi** (position corrigée par le
scan ou par le nettoyage ; l'écart est stocké en cm), **varsayildi**
(valeur par défaut ou non vérifiée — à contrôler). Un filtre de vue permet
de les colorer.

Relancer le bouton dans le même projet est sans risque : les éléments déjà
créés sont conservés, ceux que vous avez supprimés ne reviennent pas, seuls
les manquants sont ajoutés.

## Licence

[MIT](LICENSE)
