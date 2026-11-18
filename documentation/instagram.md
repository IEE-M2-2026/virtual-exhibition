# Le fil Instagram

La troisième vue de l’exposition est accessible par « Le fil Instagram » dans le bandeau de la galerie, de la halle et du fil, ou directement par `docs/instagram.html`.

Le téléphone, inspiré d’un iPhone 13 mini, et l’interface Instagram sont dessinés en HTML/CSS et SVG. Il s’agit d’une simulation locale, sans connexion à Instagram, compte ou service externe. Les icônes sociales sont décoratives. L’affiche et le bouton « Affiche suivante » constituent les commandes de lecture, accessibles aussi par Tab puis Entrée ou Espace.

Le fil lit exclusivement le catalogue public `docs/data/posters.json` et les images normalisées dans `docs/posters/texture/`. Chaque série est mélangée par Fisher–Yates ; chaque affiche paraît une fois par série, puis une nouvelle série commence sans répétition immédiate à la jonction. Les titres et auteurices viennent du catalogue commun. Une donnée manquante est signalée sans l’inventer. Les images restent entières, sans recadrage.

Après modification d’originaux ou du catalogue privé, lancer `./tools/rebuild.sh` avant de reconstruire le site. Ce script régénère les affiches et actualise aussi les empreintes CSS/JS de la nouvelle page. Pour une retouche de page seule : `.venv/bin/python tools/version_frontend.py`, puis la même commande avec `--check`.

Vérification du fil : `npm run test:instagram --prefix tools`. Le test Playwright sert le site sous `/virtual-exhibition/` et couvre le parcours complet, les légendes, la jonction entre séries, le clavier, cinq largeurs d’écran, les erreurs de catalogue, les images indisponibles et la reprise. Utiliser `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` pour un Chrome déjà installé si nécessaire. Les captures restent dans un répertoire temporaire hors dépôt.
