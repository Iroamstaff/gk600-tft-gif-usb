# Réparer les menus de l'écran du GK600 (expérimental)

> **Statut : expérimental.** Vérifié en exécutant le vrai code du firmware Frieren V1.17 (même
> plateforme, même protocole) dans un émulateur, puis sur de vrais GK600 (`0DB0:EA47`) : sonde,
> retour et écriture de 384 pages en firmware V1.20 le 18 novembre 2026, puis réparation complète
> d'un clavier abîmé en firmware V1.04 le 19 novembre (menus et animation de démarrage revenus,
> GIF intact). Vous restez seul responsable de ce que vous faites avec votre clavier.
>
> **Débutant ?** Inutile de lire la suite : double-cliquez sur `GK600-Repair.bat` et suivez les
> instructions (voir [README.md](README.md)). Ce guide explique ce que fait l'outil et son usage
> manuel.

## Le symptôme

Après l'envoi d'un GIF, les écrans de menus (luminosité, effets, couleurs, connexion…) affichent
des morceaux d'un ancien GIF, ou du noir. L'animation de démarrage marche encore, l'envoi de
nouveaux GIF aussi. `Fn + Échap` (réinitialisation) ne change rien.

## La cause

Tout ce que l'écran affiche est stocké dans une puce mémoire flash à part. Les menus sont au début
de la puce (`0x000000` à `0x1A0000`), le GIF commence à `0x3C0000`.

Le firmware écrit le GIF à la suite, sans vérifier la fin de la puce. L'adresse tient sur
24 bits : arrivée au bout, l'écriture repart au début de la puce, **sur les menus**. C'est démontré
dans le code du firmware de la plateforme et reproduit en émulation. Un clavier cousin, l'AULA
F108 Pro, a perdu ses menus de la même façon après un GIF trop long ([compte rendu de parsiya](https://github.com/parsiya/f108-pro/blob/main/ai-docs/lcd-upload-investigation.md)).

| Taille de la puce | Le GIF déborde sur les menus à partir de |
|---|---|
| 16 Mo (taille du dump public d'un GK600) | 419 images : impossible avec le logiciel MSI (limite 255), **sauf si on a relevé `gif_maxframes`** |
| 8 Mo (hypothèse, jamais observée à ce jour) | 146 images, ce que le logiciel MSI accepte |

Sur le seul clavier abîmé documenté (forum MSI), `gif_maxframes` avait été porté à 10005 et des GIF
de plus de 255 images envoyés. Avec une puce de 16 Mo, celle du dump public :

- de 256 à 418 images, rien ne déborde, mais l'animation repart trop tôt : le logiciel MSI range le
  nombre d'images sur un seul octet, 300 images deviennent 44 ;
- à partir de 420 images, le GIF déborde sur les menus ;
- à partir de 474, il atteint aussi l'animation de démarrage.

C'est exactement l'évolution observée : d'abord les menus seuls, l'animation de démarrage marchant
encore, puis l'animation de démarrage elle aussi. Seul le dernier GIF envoyé fonctionne toujours.
Une puce de 8 Mo donnerait la même évolution avec des seuils plus bas (146 et 201 images) : la
taille de la puce reste inconnue, mais la réparation marche dans les deux cas.

### Pour ne pas abîmer ses menus

- **Ne relevez jamais `gif_maxframes`** dans `layouts\rgb-keyboard.xml` (255 d'origine) : c'est ce
  qui a abîmé le clavier documenté.
- Par prudence, tant que la taille de la puce n'est pas vérifiée sur d'autres exemplaires, **restez à
  145 images** par GIF (160 × 96). Le GIF d'origine MSI en a 125.

## Ce que fait l'outil

`gk600_restore.py` réécrit les menus d'origine par le câble USB, sans ouvrir le clavier. Il
emprunte exactement le chemin du logiciel MSI quand il envoie un GIF, à une commande près :

| Étape | Logiciel MSI (GIF) | `gk600_restore.py` |
|---|---|---|
| ouverture | `04 18` | `04 18` (identique) |
| écriture | `04 72` → à partir de `0x3C0000` | `04 38` → à partir de `0x000000` |
| données | pages de 4096 octets | pages de 4096 octets, chacune confirmée par le clavier (`01 5A 02`) |
| fermeture | `04 02` | `04 02` (identique) |

`restore` écrit 416 pages, soit `[0x000000, 0x1A0000)` : tous les menus et icônes, y compris
l'écran d'accueil (le dragon devant le PC portable, la batterie, la barre WIN/MAC, connexion et
verrous), en s'arrêtant juste avant l'animation de démarrage. Votre GIF n'est pas touché.

Les images d'origine viennent du dump public d'un GK600 sain, publié par Flonfli. L'outil ne les
contient pas : vous téléchargez le dump, l'outil vérifie son empreinte avant de s'en servir.

## Ce qu'il faut

- Windows 10 ou 11, le câble USB, le clavier en **mode filaire**.
- Python 3.8 ou plus récent, puis dans une invite de commandes : `pip install hidapi`
- `gk600_restore.py` (ce dossier).
- Le dump de référence : fichier `Forge gk600 tkl wireless.bin` du dépôt
  <https://github.com/Flonfli/Forge-gk600-tkl-wireless.bin>, à placer **à côté de** `gk600_restore.py`.
  Empreinte SHA-256 attendue :
  `d3a7359a69692e2d25994b8c886cdd87444342b509eaf505cb197664ab671b50`
- **Fermez le logiciel MSI**, y compris dans la zone de notification (il parle au clavier et
  mélangerait ses commandes aux nôtres). Idem pour OpenRGB ou SignalRGB.

**Avant chaque écriture** (étapes 1 et 2) : débranchez le câble, éteignez le clavier, attendez
10 secondes, rallumez-le, rebranchez le câble. **L'animation de démarrage doit se jouer** (si elle
est abîmée chez vous, l'écran reste noir : gardez simplement le clavier éteint 10 secondes). C'est
indispensable : un transfert interrompu auparavant peut laisser le clavier dans un état où les
données arriveraient décalées, sans qu'aucun message ne le signale. L'outil vous le rappelle.

Sans `--write`, aucune commande n'écrit quoi que ce soit : l'outil affiche ce qu'il ferait.

## Étape 0 — vérifier que le clavier répond (aucune écriture)

```
python gk600_restore.py check
```

Attendu : le nom du clavier, sa version de firmware, puis `Handshake OK`. Notez la version
affichée (par exemple `V1.20`) : elle sera utile si vous signalez un résultat.

## Étape 1 — la sonde (17 pages, réversible)

Validée le 18 novembre 2026 sur un GK600 en `V1.20` : les icônes se rayent, `unprobe` remet
l'écran d'origine et l'animation de démarrage n'est pas touchée. **Si `check` affiche `V1.04` ou
`V1.20`, cette étape est facultative** (réparation complète réussie en V1.04 le 19 novembre). Pour
toute autre version, faites-la.

```
python gk600_restore.py probe --write
```

Elle ne touche que les 68 premiers Ko de la puce. On y trouve le fond et toutes les icônes de
l'écran d'accueil, celui du dragon devant le PC portable :

- la batterie, en haut à droite ;
- la barre du bas : WIN/MAC, connexion (USB, 2,4 GHz, BT), verrouillage Windows, Verr. Maj et
  Verr. Num.

La sonde remplace toutes ces icônes par des rayures magenta et jaune, et met des bandes de couleurs
dans le fond noir. Le dragon, lui, n'est pas touché et peut cacher une partie du fond. Aperçu :
`images/probe_preview.png`.

- **Les icônes sont rayées** : la commande `04 38` de votre firmware écrit bien au début de la
  puce. Si l'écran d'accueil n'est pas affiché, appuyez sur Verr. Maj ou Verr. Num pour forcer le
  redessin. Remettez les icônes d'origine, puis passez à l'étape 2 :
  ```
  python gk600_restore.py unprobe --write
  ```
  Si vous enchaînez directement avec l'étape 2, `unprobe` est facultatif : la restauration
  réécrit aussi cette zone.
- **Rien n'a changé, ou autre chose a changé** : arrêtez-vous là et signalez-le
  (version de firmware, ce que vous voyez, fichier `gk600_restore.log`). Ne lancez pas l'étape 2.
  Si c'est votre GIF qui est abîmé, renvoyez-le avec le logiciel MSI.

## Étape 2 — la restauration (416 pages)

```
python gk600_restore.py restore --write
```

Comptez environ une minute (sur un GK600 réel, une page prend de 120 à 180 ms). Puis parcourez tous
les menus et comparez-les à la planche `images/reference_screens_0_1A0000.png` (les 41 écrans de
menus d'origine). Éteignez et rallumez le clavier, et vérifiez une seconde fois.

### Si l'animation de démarrage est abîmée elle aussi

Si le logo MSI du démarrage est remplacé ou cassé lui aussi, ajoutez `--with-boot` :

```
python gk600_restore.py restore --with-boot --write
```

L'outil réécrit alors `[0x000000, 0x3C0000)` : menus et animation de démarrage, 960 pages, 2 à 3
minutes. Il faut le dump complet de 16 Mo. Votre GIF n'est toujours pas touché.

Juste après la sonde ou la restauration, le clavier affiche son écran d'accueil plutôt que votre GIF :
c'est le comportement normal du firmware après ce type d'écriture. Éteignez puis rallumez le
clavier : il redémarre sur son écran habituel (Fn + flèche gauche / droite passe aussi du GIF à
l'écran d'accueil). Si votre GIF n'apparaît plus, renvoyez-le avec le logiciel MSI (145 images au
plus).

## Option : changer l'image de l'écran d'accueil

Le dragon devant le PC portable est une image de 160 px de large rangée en `0x17A1CE`, dessinée
depuis le coin haut-gauche de l'écran. Les lignes 0 à 64 sont affichées (160 × 65), au-dessus de
la barre du bas ; la batterie est dessinée par-dessus, en x 131–155, y 10–22.
`gk600_home_picture.py` la remplace par votre image. Le plus simple : glissez l'image sur
`GK600-Home-Picture.bat`, qui installe ce qu'il faut et montre un aperçu avant d'écrire. À la main :

```
python gk600_home_picture.py mon_image.png             # à blanc, rien n'est envoyé
python gk600_home_picture.py mon_image.png --write
```

- L'image : un fichier brut RGB565 petit-boutiste de 160 × 65 (20 800 octets), ou un PNG / JPG
  si Pillow est installé (`pip install pillow`). Une image d'exactement 160 × 65 est prise telle
  quelle ; sinon ses marges unies sont rognées, puis elle est réduite pour tenir dans 160 × 65,
  sur fond noir. Gardez le coin de la batterie vide. `--preview apercu.png` montre le résultat
  sans rien envoyer.
- `04 38` écrit toujours à partir de `0x000000` : l'outil réécrit `[0x000000, 0x180000)`,
  384 pages, environ une minute, avec le dump et votre image à la place du dragon. Votre GIF et
  l'animation de démarrage ne sont pas touchés. Mêmes précautions qu'à l'étape 2 : logiciel MSI
  fermé, clavier éteint puis rallumé avant l'écriture.
- Retour au dragon : `python gk600_restore.py restore --write`.
- Validé le 18 novembre 2026 sur un GK600 en `V1.20` : 384 pages accusées en 54 secondes, image
  entière et à sa place. En `V1.04`, la réparation a remis le dragon au même endroit : l'outil
  accepte aussi cette version, sans essai direct de l'image à ce jour.

## En cas d'erreur

L'outil s'arrête à la **première** anomalie et n'envoie plus rien.

| Message | Ce qu'il faut faire |
|---|---|
| `no GK600 / Frieren keyboard found` | câble branché, clavier en mode filaire, logiciel MSI fermé |
| `keyboard not idle` | éteindre puis rallumer le clavier (animation de démarrage), relancer |
| `04 38 refused` | **aucune page n'a été envoyée** : votre firmware n'accepte pas cette commande. Éteignez et rallumez le clavier, puis signalez-le |
| `page N/416: no ACK` | débrancher, éteindre, rallumer, puis relancer **la même commande** : elle réécrit tout depuis le début |

Après un transfert interrompu, l'éclairage ou certaines touches peuvent rester figés jusqu'au
redémarrage du clavier : c'est attendu.

## Ce qui est prouvé, et ce qui ne l'est pas

Prouvé, en exécutant le vrai code du firmware Frieren V1.17 en émulation avec l'outil lui-même :

- `04 38` écrit à partir de l'adresse `0x000000`, page après page, sans en-tête ajouté ;
- la restauration efface et réécrit exactement `[0x000000, 0x1A0000)` et rien d'autre ;
- la sonde ne touche que `[0x000000, 0x11000)`, et le code d'affichage de l'écran d'accueil lit
  toutes ses icônes dans cette zone, où le dump du GK600 contient exactement ces icônes ;
- partant de menus détruits, la puce entière redevient identique octet pour octet au dump de
  référence ;
- un GIF de 200 images détruit les menus d'une puce de 8 Mo en laissant l'animation de démarrage
  intacte, et l'outil les répare ;
- un GIF de 500 images détruit aussi l'animation de démarrage d'une puce de 16 Mo, et
  `--with-boot` la répare ;
- un transfert interrompu, ou un clavier pas redémarré, sont détectés ou rattrapables comme décrit
  plus haut.

Vérifié sur un vrai GK600 (`0DB0:EA47`, firmware `V1.20`, Windows 11), le 18 novembre 2026 :

- `check` trouve les collections `FF13` et `FF68` avec les tailles de rapports attendues
  (65 / 4097 / 65), et `04 18` répond `01` (au repos) ;
- `04 38` est acceptée et renvoie le nombre de pages annoncé ; les 17 pages de la sonde sont
  toutes accusées, en 2 secondes environ ;
- les icônes de l'écran d'accueil se rayent, l'animation de démarrage reste intacte, et `unprobe`
  remet l'écran d'origine.

Journal : `tests/real_gk600_V1.20_2026-11-18.log`.

Réparation complète réussie le 19 novembre 2026 sur un GK600 abîmé en firmware `V1.04` (menus et
animation de démarrage devenus noirs après de longs GIF) : avec `GK600-Repair.bat`, les menus
d'origine et l'animation MSI sont revenus, et le GIF en place n'a pas été touché.

Pas encore prouvé :

- le comportement de `04 38` sur les versions de firmware autres que `V1.04` et `V1.20` : c'est
  l'objet de l'étape 1. Ce qui le rend probable : les descripteurs USB, le filtre de commandes et
  les commandes `04 18` / `04 72` / `04 02` sont identiques sur toute la plateforme, le même chemin
  `04 38` existe dans un autre firmware de la famille (AULA F98 Pro V1.20), et les V1.04 et V1.20
  du GK600 se comportent comme le Frieren V1.17 ;
- la taille de la puce sur les claviers abîmés (8 ou 16 Mo).

Les tests rejouables sont dans `tests/` (émulateur, scénarios, résultats).

## Annexe technique

| Élément | Valeur |
|---|---|
| Interface commandes | MI_03, page d'usage `FF13`, rapports FEATURE 64 o (+ ID 0) |
| Interface données | MI_02, page d'usage `FF68`, sortie 4096 o, entrée 64 o (accusé) |
| Délai entre commandes | 35 ms, comme le pilote (`cmd_delaytime`) |
| `04 38` | `04 38 00 00 00 00 00 00 <pages LE> 00…` |
| Réponse attendue | octet 3 = `01` ; `00` ou `FF` = clavier occupé |
| Accusé par page | `01 5A 02 00…` sur l'entrée de `FF68` |
| Écran d'accueil : fond | `0x000000`, 160 × 96, RGB565 petit-boutiste, noir |
| Écran d'accueil : icônes | `0x007800` à `0x010806` (batterie, connexion, WIN/MAC, verrous) |
| Écran d'accueil : dragon | vers `0x17A1CE`, 160 px de large (propre au GK600) |
| Menus et icônes | de `0x007A8A` à `0x1868A2` (41 écrans pleins, icônes, jauges) |
| Animation de démarrage | en-tête `0x1A0000`, images `0x1A0100` |
| GIF utilisateur | en-tête `0x3C0000`, images `0x3C0100` |
