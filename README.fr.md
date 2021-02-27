# Component ipx800 pour Home Assistant

Il s'agit d'un _custom component_ pour [Home Assistant](https://www.home-assistant.io/).
L'intégration `ipx800` vous permet de contrôler et d'obtenir des informations de votre [IPX800 v4 et de ses extensions](http://gce-electronics.com/).

## Installation

Copier le dossier `custom_components/ipx800` dans `config/custom_components` de votre installation Home Assistant.
Ajouter l'entrée `ipx800` dans votre fichier `configuration.yml` (voir l'exemple ci-dessous).

L'IPX800 doit être disponible pendant le démarrage d'Home Assistant.
Si vous avez un autre système domotique qui communiquer avec l'IPX800, comme Jeedom, désactivez le pendant le démarrage d'Home Assistant, afin d'être sûr qu'il puisse répondre aux requêtes.

## Dépendances

[pypix800 python package](https://github.com/Aohzan/pypx800) (installé par Home-Assistant directement, rien à faire de votre côté)

## Description

Vous pouvez contrôller ces types d'appareil :

- `relay` en tant que switch, light ou climate (avec https://www.gce-electronics.com/fr/nos-produits/314-module-diode-fil-pilote-.html)
- `virtualout` en tant que switch et binarysensor
- `virtualin` en tant que switch
- `digitalin` en tant que binarysensor
- `analogin` en tant que sensor
- `xdimmer` en tant que light
- `xpwm` en tant que light
- `xpwm_rgb` en tant que light (utilise 3 canaux xpwm)
- `xpwm_rgbw` en tant que light (utilise 4 canaux xpwm)
- `x4vr` en tant que cover
- `xthl` en tant que sensors
- `x4fp` en tant que climate

Vous pouvez mettre à jour la valeur d'une entité en définissant une commande Push dans l'IPX800 via un scénario.
Utile pour mettre à jour directement un binary_sensor ou un  switch sans attendre la prochaine récupération d'état.
Dans `URL ON` et `URL_OFF` mettre `/api/ipx800/entity_id/state`:

![PUSH configuration example](ipx800_push_configuration_example.png)

## Exemple et paramètres de configuration
![Sur le README original](README.md)

