![GitHub Downloads](https://img.shields.io/github/downloads/schizza/SWS-12500-custom-component/total?label=downloads%20%28all%20releases%29)
![Latest release downloads](https://img.shields.io/github/downloads/schizza/SWS-12500-custom-component/latest/total?label=downloads%20%28latest%29)

# Integrates your Sencor SWS 12500, SWS16600, SWS 10500, GARNI, BRESSER weather stations seamlessly into Home Assistant

This integration will listen for data from your station and passes them to respective sensors. It also provides the ability to push data to `Windy API` or `Pocasi Meteo`.

### Ecowitt support is coming in the next major release

As of April 11, 2026, Ecowitt stations are supported in the pre-release version
[v2.0.0pre1](https://github.com/schizza/SWS-12500-custom-component/releases/tag/v2.0.0pre1).
You can download this pre-release in HACS under `target version`, where you can pick the exact
version of the integration. Please be aware that this pre-release is really for testing
purposes only.

---

### Integration rename is planned for the next major release

The current name no longer reflects what the integration does. It was initially developed
primarily for the SWS 12500 station, but it already supports other weather stations as well
(Bresser, Garni and others), and Ecowitt support is on the way — so the current name has
become misleading. The transition will be announced via an update, and I'm also planning to
offer a full data migration from the existing integration to the new one, so you won't lose
any of your historical data.

- The transition date hasn't been set yet, but it's currently expected to happen within the
  next ~2–3 months. At the moment, I'm working on a full refactor and general code cleanup.
  Looking further ahead, the goal is to have the integration fully incorporated into Home
  Assistant as a native component — meaning it won't need to be installed via HACS but will
  become part of the official Home Assistant distribution.

- I'm also looking for someone who owns an Ecowitt weather station and would be willing to
  help with testing the integration for these devices.

---

## Warning — WSLink app (applies also to SWS 12500 with firmware > 3.0)

Please read the **IMPORTANT** note below.

For stations that use the WSLink app to set up the station and the WSLink API for resending
data (also SWS 12500 stations manufactured in 2024 or later), you will need to install the
[WSLink SSL proxy add-on](https://github.com/schizza/wslink-addon) into your Home Assistant
— unless you are already running Home Assistant in SSL mode or you have your own SSL proxy
in front of Home Assistant.

---

> [!IMPORTANT]
> The recommendation above does not apply to all stations. As is known by now, some stations
> — even when configured via the `WSLink App` — do not use the `WSLink protocol` to send
> data to custom servers. It can therefore be confusing how to configure your station, and
> for that case I made a simple debugging server (see below).

## Not Sure How Your Station Sends Data?

If you are struggling with configuration and don't know which protocol your station uses (`WSLink` or `PWS/WU`), or whether it sends data over SSL or plain HTTP — use our public test server:

**<https://test-station.schizza.cz>**

1. Open the link above and create a new session.
2. Point your weather station to the generated subdomain address.
3. Within a few seconds the server will show you:
   - the **protocol** your station is using (`WSLink` or `PWS/WU`)
   - whether the request arrived over **SSL** or **non-SSL**
   - the full query string, headers, and payload your station sent

This information tells you exactly how to configure the integration in Home Assistant.

### Quick Recommendations

| Station sends via | Protocol | Recommended Setup |
|---|---|--- |
| **plain HTTP** | PWS/WU | Point the station directly at Home Assistant — no proxy needed. Keep `WSLink API` unchecked (disabled). |
| **plain HTTP** | WSLink | Point the station directly at Home Assistant — no proxy needed. Enable `WSLink API` in settings. |
| **HTTPS (SSL)** | PWS/WU | Install the [WSLink Proxy Add-on](https://github.com/schizza/wslink-addon) — it terminates TLS and forwards plain HTTP to Home Assistant. Keep `WSLink API` unchecked (disabled). |
| **HTTPS (SSL)** | WSLink | Install the [WSLink Proxy Add-on](https://github.com/schizza/wslink-addon) — it terminates TLS and forwards plain HTTP to Home Assistant, and enable `WSLink API`. |

— If the test server shows your station is sending over SSL, you need the [WSLink Proxy Add-on](https://github.com/schizza/wslink-addon). If it sends plain HTTP, you can connect directly.

Web server repo is reachable here: <https://github.com/schizza/test-station-server>

## Requirements

- Weather station that supports sending data to custom server in their API [(list of supported stations.)](#list-of-supported-stations)
- Configure station to send data directly to Home Assistant.
- If you want to push data to Windy, you have to create an account at [Windy](https://stations.windy.com).
- If you want to resend data to `Pocasi Meteo`, you have to create accout at [Pocasi Meteo](https://pocasimeteo.cz)

## Examples of supported stations

- [Sencor SWS 12500 Weather Station](https://www.sencor.cz/profesionalni-meteorologicka-stanice/sws-12500)
- [Sencor SWS 16600 WiFi SH](https://www.sencor.cz/meteorologicka-stanice/sws-16600)
- SWS 10500 (newer firmware revisions are also supported via the [WSLink SSL proxy add-on](https://github.com/schizza/wslink-addon))
- Bresser stations that support custom server upload — [this model is known to work](https://www.bresser.com/p/bresser-wi-fi-clearview-weather-station-with-7-in-1-sensor-7002586), for example
- Garni stations with WSLink support or custom server support
- and a bunch of other models that aren't listed here are also supported

## Supported sensors

The integration auto-creates sensors as soon as the station first sends data for them — new
sensors trigger a notification in Home Assistant and are added to the entity list
automatically.

Beyond the standard set (outdoor / indoor temperature and humidity, barometric pressure,
wind speed / direction / gust, rain rate and daily / weekly / monthly / yearly totals, dew
point, UV index, solar irradiance) the WSLink protocol also exposes:

- additional channels **CH2** and **CH3** for temperature and humidity
- **WBGT** index, **heat index**, **wind chill**
- sensor battery levels (outdoor, indoor, CH2)
- **Formaldehyde (HCHO)** in ppb and **VOC level** as a 1–5 air-quality index
  (1 = worst, 5 = best) from the WH46 / 7-in-1 air-quality combo sensor
- **HCHO/VOC sensor battery** reported as a percentage

HCHO / VOC entities are only created when the station reports the air-quality module as
connected (`t9cn = 1`), so they don't clutter the device when no such sensor is attached.

## Installation

### For stations that send data through WSLink API

Make sure you have your Home Assistant configured in SSL mode or use [WSLink SSL proxy addon](https://github.com/schizza/wslink-addon) to bypass SSL configuration of whole Home Assistant.

### HACS installation

For installation with HACS, you have to first add a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/).
You will need to enter the URL of this repository when prompted: `https://github.com/schizza/SWS-12500-custom-component`.

After adding this repository to HACS:

- Go to HACS -> Integrations
- Search for the integration `Sencor SWS 12500 Weather station` and download the integration.
- Restart Home Assistant
- Now go to `Integrations` and add new integration. Search for `Sencor SWS 12500 Weather station` and select it.

### Manual installation

For manual installation you must have access to your Home Assistant's `/config` folder.

- Clone this repository or download the [latest release here](https://github.com/schizza/SWS-12500-custom-component/releases/latest).

- Copy the `custom_components/sws12500` folder to your `config/custom_components` folder in Home Assistant.
- Restart Home Assistant.
- Now go to `Integrations` and add new integration `Sencor SWS 12500 Weather station`

## Configure your station in AP mode

> This configuration example is for Sencor SWS12500 with FW < 3.0

> For WSLink read [this notes.](#wslink-notes)

1. Hold the Wi-Fi button on the back of the station for 6 seconds until the AP will flash on the display.
2. Select your station from available APs on your computer.
3. Connect to the station's setup page: `http://192.168.1.1` from your browser.
4. In the third URL section fill in the address to your local Home Assistant installation.
5. Create new `ID` and `KEY`. You can use [online tool](https://randomkeygen.com) to generate random keys. _(you will need them to configure integration to Home Assistant)_
6. Save your configuration.
   ![station_setup](README/station_hint.png)

Once integration is added to Home Assistant, configuration dialog will ask you for `API_ID` and `API_KEY` as you set them in your station:

```plain
API_ID: ID in station's config
API_KEY: PASSWORD in station's config
```

![config dialog](README/cfg_dialog.png)

If you change `API ID` or `API KEY` in the station, you have to reconfigure integration to accept data from your station.

- In `Settings` -> `Devices & services` find SWS12500 and click `Configure`.
- In dialog box choose `Basic - Configure credentials`

![reconfigure dialog](README/reconfigure.png)

As soon as the integration is added into Home Assistant it will listen for incoming data from the station and starts to fill sensors as soon as data will first arrive.

## Upgrading from PWS to WSLink

If you upgrade your station — which was previously sending data in the PWS protocol — to a
station that uses the WSLink protocol, you have to remove the integration and reinstall it.
The WSLink protocol uses the metric scale instead of the imperial scale used in PWS, and
deleting and reinstalling the integration makes sure the sensors are aware of the change of
measurement scale.

- because sensor unique IDs stay the same, you will not lose any of your historical data

## Resending data to Windy API

- First of all you need to create account at [Windy stations](https://stations.windy.com).
- Once you have an account created, copy your Windy API Key.
  ![windy api key](README/windy_key.png)

- In `Settings` -> `Devices & services` find SWS12500 and click `Configure`.
- In dialog box choose `Windy configuration`.
  ![config dialog](README/cfg.png)

- Fill in `Key` you were provided at `Windy stations`.
- Tick `Enable` checkbox.
  ![enable windy](README/windy_cfg.png)

- You are done.

## Resending data to Pocasi Meteo

- If you are willing to use [Pocasi Meteo Application](https://pocasimeteo.cz) you can enable resending your data to their servers
- You must have account at Pocasi Meteo, where you will recieve `ID` and `KEY`, which are needed to connect to server
- In `Settings` -> `Devices & services` find SWS12500 and click `Configure`.
- In dialog box choose `Pocasi Meteo configuration`.
- Fill in `ID` and `KEY` you were provided at `Pocasi Meteo`.
- Tick `Enable` checkbox.

- You are done.

## Multi-channel sensor support (CH2-CH8)

This integration supports up to 8 external sensor channels for temperature, humidity, and battery monitoring.

### Supported channels

- **CH2-CH3**: Enabled by default
- **CH4-CH8**: Available but disabled by default (enable manually in Home Assistant)

### Available sensors per channel

Each channel provides:
- **Temperature sensor** (with configurable unit conversion)
- **Humidity sensor** (percentage)
- **Battery level sensor** (percentage)
- **Connection status** (connected/disconnected)

### Enabling additional channels

By default, channels 4-8 are disabled to avoid cluttering your interface. To enable them:

1. Go to **Settings** → **Devices & Services**
2. Find **Sencor SWS 12500** and click on it
3. You'll see all available entities, including disabled ones
4. Click on any disabled channel sensor (e.g., "Channel 5 Temperature")
5. Click the settings icon and enable the entity
6. Repeat for other sensors you want to use

### Station configuration

Your weather station must be configured to send data for these channels. Refer to your station's manual on how to pair and configure external sensors to specific channels.

**Note**: The integration automatically detects incoming data from any channel. If you don't see data for a channel you've enabled, verify that:
- The external sensor is properly paired with your station
- The sensor is sending data (check battery level)
- Your station firmware supports the channel you're trying to use

## WSLink notes

If your station sends WSLink data over SSL (see the
[Quick Recommendations](#quick-recommendations) table above), Home Assistant has to be
reachable over SSL too — either by running Home Assistant in SSL mode, or by putting it
behind an SSL proxy. You can bypass whole-system SSL setup by using the
[WSLink SSL proxy add-on](https://github.com/schizza/wslink-addon), which is made exactly
for this integration to support WSLink on non-SSL installations of Home Assistant.

### Configuration

- Set your station up as [described above](#configure-your-station-in-ap-mode), but for
  `HA port` use the port the add-on is listening on (4443 by default) — **not** the port
  of your Home Assistant instance.

```plain
Home Assistant is at 192.168.0.2:8123
WSLink proxy add-on is listening on port 4443

→ set the station URL to: 192.168.0.2:4443
```

- Your station will send data to the SSL proxy and the add-on will handle the rest.

_Most stations do not care about self-signed certificates on the server side._
