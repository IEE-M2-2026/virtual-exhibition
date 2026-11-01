# Méta-affiche de l'événement

`tools/prepare_event_poster.py` compose une affiche unique (la « méta-affiche ») à partir de toutes les affiches du catalogue : chaque affiche est placée entièrement, une seule fois, dans une grille mêlant vignettes et cases de couleur portant le hashtag et/ou le titre de l'événement. Le script ne produit que des fichiers dans son dossier de sortie : il ne modifie ni les originaux, ni `res/posters.json`, ni le site.

## Prérequis

- Python 3.11 ou plus récent.
- Dépendances de `tools/requirements.txt` (dont Pillow et pypdfium2).
- Un environnement virtuel déjà installé à la racine du dépôt (`.venv`).

## Commande de base

Depuis la racine du dépôt :

```sh
.venv/bin/python tools/prepare_event_poster.py
```

Entrées par défaut :

- `res/posters.json` (catalogue) et `res/posters/` (originaux).
- Le catalogue doit couvrir toutes les affiches présentes ; la validation est celle du pipeline existant.

Sorties :

- `res/event_poster/event-poster.png` : image RVB sRGB, 3508 × 4961 pixels, résolution déclarée de 300 dpi (A3 portrait approximatif). Ce n'est pas une épreuve CMJN.
- `res/event_poster/layout.json` : paramètres et placements, avec des identifiants publics, sans noms de fichiers originaux ni champs étudiants.

L'image précédente n'est remplacée qu'après un rendu réussi ; les autres fichiers du dossier de sortie restent intacts. La génération est indépendante de la reconstruction du site.

## Options

| Option | Rôle | Valeur par défaut |
| --- | --- | --- |
| `--source-dir` | Dossier des affiches originales | `res/posters/` |
| `--catalog` | Catalogue des affiches | `res/posters.json` |
| `--output-dir` | Dossier de sortie | `res/event_poster` |
| `--width` | Largeur en pixels | 3508 |
| `--height` | Hauteur en pixels | 4961 |
| `--dpi` | Résolution déclarée | 300 |
| `--margin` | Marge extérieure | `0` |
| `--gutter` | Espacement entre les cases | `0` |
| `--min-fillers` | Nombre minimal de cases de couleur | `1` |
| `--seed` | Graine de la disposition | `2026` |
| `--hashtag` | Hashtag des cases de couleur | `"#IEE 2026"` |
| `--title` | Titre des cases de couleur | `"CRÉATIONS SUR SCÈNES"` |
| `--font` | Police TrueType/OpenType (facultatif) | police système, puis repli Pillow |

Sans `--font`, le script cherche une police système puis se rabat sur celle fournie par Pillow. Pour reproduire la typographie sur une autre machine, il est conseillé de passer une police explicite.

## Comportement de la grille

- La grille automatique équilibre deux critères : proximité du rapport médian des affiches et nombre de cases vides.
- Toutes les affiches sont placées une fois, entièrement visibles, sans découpe ni déformation. Des marges blanches peuvent apparaître dans une case lorsque son ratio diffère de celui de l'affiche.
- Aucune affiche n'est répétée pour combler les trous : les cases restantes sont des aplats, avec le hashtag, le titre, ou les deux. Au moins une case contient les deux textes lorsque ceux-ci sont tous deux renseignés.
- Les cases de couleur et les affiches sont mélangées dans la grille.
- La graine fixe reproduit la disposition avec les mêmes entrées et la même police ; changer `--seed` propose une variante.

## Exemples

Disposition par défaut :

```sh
.venv/bin/python tools/prepare_event_poster.py
```

Variante de disposition :

```sh
.venv/bin/python tools/prepare_event_poster.py --seed 17
```

Personnalisation des textes et des dimensions :

```sh
.venv/bin/python tools/prepare_event_poster.py \
  --title "CRÉATIONS SUR SCÈNES — ÉDITION 2026" \
  --hashtag "#IEE2026" \
  --width 2480 --height 3508 --dpi 200
```

## Ajouter des affiches

Ajouter une affiche impose de mettre à jour le catalogue `res/posters.json` à la main, puis de relancer la commande : la grille est entièrement recalculée.

La taille d’une case doit rester au moins égale à 64 pixels sur chaque axe ; le script demande d’augmenter les dimensions si la collection devient trop grande. La sortie est limitée à 100 millions de pixels. Pour retirer un texte, passer `--title ""` ou `--hashtag ""` ; si les deux sont vides, les aplats restent unis.
