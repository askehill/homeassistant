# Device Reference

Hardware inventory for this Home Assistant installation. See [README.md](README.md) for architecture and configuration overview.

---

## Zigbee device map (zbbridge)

All devices communicate via `tele/zbbridge/SENSOR` → `ZbReceived[hex_id]`. Commands go to `cmnd/zbbridge/ZbSend`.

| Hex ID | Device | Type |
|---|---|---|
| `0x167A` | Office | Temp / Humidity / Pressure sensor |
| `0x99E2` | Master Bedroom | Temp / Humidity / Pressure sensor |
| `0x0807` | Kitchen | Temp / Humidity / Pressure sensor |
| `0xA076` | Living Room | Temp / Humidity / Pressure sensor |
| `0x2645` | 1st Floor | Temp / Humidity sensor |
| `0x0195` | Kitchen Corner | Smart plug (floor lamp) |
| `0x80F8` | Office Socket | Smart plug |
| `0xF884` | Power Monitoring Socket 1 | Smart plug with power metering |
| `0x6C50` | Extra Socket | Smart plug |
| `0x357A` | Living Room Extra Socket | Smart plug |
| `0xEC18` | Extra Socket No5 | Smart plug (spare) |
| `0x1102` | Bedroom 2 Light | Zigbee light |
| `0xACE9` | Bedroom 3 Light | Zigbee light |
| `0x3FAB` | Pantry Door | Door/contact sensor |
| `0x1CDB` | Kitchen Door | Door/contact sensor |
| `0x1C57` | Living Room | PIR motion sensor |
| `0xEA86` | Pantry | PIR motion sensor |
| `0xB515` | Outdoor Valve 1 | Sonoff Zigbee water valve |

---

## RF device map (rfbridge)

RF devices use `tele/rfbridge/RESULT` → `RfReceived.Data`.

| RF Code | Device | Type |
|---|---|---|
| `E6BC6E` | Landing | PIR motion sensor |
| `E6AA3E` | Playroom | PIR motion sensor |
| `84A794` | Hotpress | RF light switch |

---

## Shelly device map

| Entity prefix | MAC suffix | Model | Location / Purpose |
|---|---|---|---|
| `shellyem_c7faf3` | c7:fa:f3 | Shelly EM | Mains consumer unit — Ch1 = solar/generation, Ch2 = house import energy |
| `shellyplus1pm_e465b8faef78` | e4:65:b8:fa:ef:78 | Plus 1 PM | Hot press — hot water relay; temperature sensors for cylinder top/mid/bottom |
| `shellyplus1pm_c82e180640c4` | c8:2e:18:06:40:c4 | Plus 1 PM | Immersion heater switch |
| `shellypmmini_543204b7d0c0` | 54:32:04:b7:d0:c0 | PM Mini | Utility room — single clamp shared by dishwasher & hot water tap |
| `shellyplus1_7c87ce638b24` | 7c:87:ce:63:8b:24 | Plus 1 | Heater socket (garage/shed) |
| `shellyplus1_a8032abd23b8` | a8:03:2a:bd:23:b8 | Plus 1 | Lower landing lights |
| `shellyht_9551e9` | 95:51:e9 | H&T | Playroom — temperature & humidity |
| `shellyht_1a9705` | 1a:97:05 | H&T | Study — temperature & humidity |
| `shellyflood_485519ee13b7` | 48:55:19:ee:13:b7 | Flood | Utility room — flood detection + ambient temperature |
| `shelly_dimmer_2_d8bfc019cb69` | d8:bf:c0:19:cb:69 | Dimmer 2 | Light dimmer — location TBC |
| `shellydw2_a4cf12f437d2` | a4:cf:12:f4:37:d2 | Door/Window 2 | Front door open/close sensor |
| `shellyrgbw2_a8e75d` | a8:e7:5d | RGBW2 | Study — accent LED controller |
| `shellyuni_c45bbe5f76f8` | c4:5b:be:5f:76:f8 | Uni | Garden — water butt level (ADC input) |
| *(laundry clamp)* | — | — | Utility room — single clamp shared by washing machine & tumble dryer |
| `shellyplus1_a8032aba4d24` | a8:03:2a:ba:4d:24 | Plus 1 | **Unidentified** |
| `shellyplus1_a8032abc68d0` | a8:03:2a:bc:68:d0 | Plus 1 | **Unidentified** |
| `shellyplus1pm_c4d8d5429a64` | c4:d8:d5:42:9a:64 | Plus 1 PM | **Unidentified** |
| `shellyplus1pm_e465b8b7d2e0` | e4:65:b8:b7:d2:e0 | Plus 1 PM | **Unidentified** |
| `shellypmmini_543204bb41a0` | 54:32:04:bb:41:a0 | PM Mini | **Unidentified** |
| `shellyrgbw2_49f8c6` | 49:f8:c6 | RGBW2 | **Unidentified** |
| `shellyswitch25_c45bbe75cfba` | c4:5b:be:75:cf:ba | Switch 2.5 | **Unidentified** |
| `shellyswitch25_c45bbe75e6eb` | c4:5b:be:75:e6:eb | Switch 2.5 | **Unidentified** |
| `shellyplus2pm_10061cced2f0` | 10:06:1c:ce:d2:f0 | Plus 2 PM | **Unidentified** |
| `shellyplus2pm_e465b8f39bc0` | e4:65:b8:f3:9b:c0 | Plus 2 PM | **Unidentified** |
