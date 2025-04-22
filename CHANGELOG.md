# Changelog

# [3.11.0](https://github.com/Aohzan/ipx800/compare/3.10.1...3.11.0) (2025-04-22)


### Features

* add release ([#69](https://github.com/Aohzan/ipx800/issues/69)) ([f04127f](https://github.com/Aohzan/ipx800/commit/f04127fef103787af7ad00c00588c72d684156a8))

## 3.10.1

- Fix change on climate feature

## 3.10.0

- Add capacity to disable check host on push

## 3.9.1

- Fix translation key and json files

## 3.9.0

- Add icon for climate custom preset_mode

## 3.8.4

- Bump pypx800 to 2.5.1

## 3.8.3

- Fix regression introduced in 3.8.2

## 3.8.2

- Fix deprecated code

## 3.8.1

- Fix bulk update API endpoint introduced in previous version with the invert_value option for binary sensor introduced in version 3.6.1

## 3.8.0

- Add new API endpoint to push all states at once from the IPX800 (bulk update). See README for more information
- Add extra_url for each API endpoint with the IPX name to support push from multiple IPX entries

## 3.7.0

- Add support for analog X-ENO sensors

## 3.6.1

- Add an option to invert the value read from a binary sensor

## 3.6.0

- Add number entity for VA and counter

## 3.5.0

- Update code according to deprecations
- Set type for sensor values

## 3.4.2

- Fix global push

## 3.4.1

- Fix API auth check method

## 3.4.0

- Fix global refresh from push. Update your URL by: `/api/ipx800v4_refresh/on`

## 3.3.0

- Replace deprecated `async_get_registry` method

## 3.2.0

- Add API to ask a full state refresh
- Code improvements

## 3.1.0

- Add counter support

## 3.0.0

- /!\ Entities uniqueid different, remove old entry before restart
- Add options flow to set update interval
- Add configuration url
- Fix XTHL device

## 2.8.0

- Add cover tilt (BSO)

## 2.7.0

- Lights fixes and enhancements

## 2.6.0

- /!\ Home-Assistant >= 2021.9.0 required
- Une new native value sensor for X-THL
- Simplify code

## 2.5.0

- Set X-THL as statistics sensors
- Optimizations

## 2.4.1

- Fix API authentication verification

## 2.4.0

- BREAKING CHANGE: Authentication now needed to PUSH data from IPX800. See README for more information
- Check source IP for PUSH call to check if the call is made by the IPX800 IP

## 2.3.0

- Use new color mode for lights
- Add `default_brightness` for XPWM lights, to turn on the light to a defined brightness instead of 100%

## 2.2.0

- Add Virtual Analog Input

## 2.1.2

- Fix climate value

## 2.1.1

- Fix async related issues
- Use climate presets

## 2.1.0

- Use async request
- Optimize request
- Fix devices issues

## 2.0.0

- Major rewrite: remove old entry and entities before upgrade
- Rename to ipx800v4 to avoid conflict with others ipx800 versions
- Added in integration panel (just for information, no settings)
- Add Devices
- Fix request error and related issues (thanks @guigeek38)
- Add light toggle
- Add logo
- Add API url to push multiple data at once

## 1.8.2

- Fix polling key for VirtualOut switch

## 1.8.1

- Remove the wrong climate setup error

## 1.8

- Add X-4FP support
- Add Fil Pilote through relay support <https://www.gce-electronics.com/fr/nos-produits/314-module-diode-fil-pilote-.html>
- Fix user/password as optional parameters

## 1.7

- Fix Python import missing in 0.115

## 1.6

- Bump pypx800: fix cover id with many extensions

## 1.5

- Add Stop for cover
- Bump pypx800

## 1.4

- Round X-THL values

## 1.3

- Fix pypx800 library classes names
- Comments normalization

## 1.2

- Fix set cover position

## 1.1

- Fix transition for XDimmer and XPWM lights
- Fix cover position
- Fix async error

## 1.0

- Initial finalrelease
