![GitHub Downloads](https://img.shields.io/github/downloads/schizza/SWS-12500-custom-component/total?label=downloads%20%28all%20releases%29)
![Latest release downloads](https://img.shields.io/github/downloads/schizza/SWS-12500-custom-component/latest/total?label=downloads%20%28latest%29)

# Integrates your Sencor SWS 12500, SWS16600, SWS 10500, GARNI, BRESSER weather stations seamlessly into Home Assistant

This integration will listen for data from your station and passes them to respective sensors. It also provides the ability to push data to `Windy API` or `Pocasi Meteo`.

### In the next major release, I there will be support for Ecowitt stations as well

---

### In the next major release, I plan to rename the integration, as its current name no longer reflects its original purpose. The integration was initially developed primarily for the SWS12500 station, but it already supports other weather stations as well (e.g., Bresser, Garni, and others). Support for Ecowitt stations will also be added in the future, so the current name has become misleading. This information will be provided via an update, and I’m also planning to offer a full data migration from the existing integration to the new one, so will not lose any of historical data.

- The transition date hasn’t been set yet, but it’s currently expected to happen within the next ~2–3 months. At the moment, I’m working on a full refactor and general code cleanup. Looking further ahead, the goal is to have the integration fully incorporated into Home Assistant as a native component—meaning it won’t need to be installed via HACS, but will become part of the official Home Assistant distribution.

- I’m also looking for someone who owns an Ecowitt weather station and would be willing to help with testing the integration for these devices.

---

## Warning - WSLink APP (applies also for SWS 12500 with firmware >3.0)

For stations that are using WSLink app to setup station and WSLink API for resending data (also SWS 12500 manufactured in 2024 and later). You will need to install [WSLink SSL proxy addon](https://github.com/schizza/wslink-addon) to your Home Assistant if you are not running your Home Assistant instance in SSL mode or you do not have SSL proxy for your Home Assistant.

## Requirements

- Weather station that supports sending data to custom server in their API [(list of supported stations.)](#list-of-supported-stations)
- Configure station to send data directly to Home Assistant.
- If you want to push data to Windy, you have to create an account at [Windy](https://stations.windy.com).
- If you want to resend data to `Pocasi Meteo`, you have to create accout at [Pocasi Meteo](https://pocasimeteo.cz)

## Example of supported stations

- [Sencor SWS 12500 Weather Station](https://www.sencor.cz/profesionalni-meteorologicka-stanice/sws-12500)
- [Sencor SWS 16600 WiFi SH](https://www.sencor.cz/meteorologicka-stanice/sws-16600)
- SWS 10500 (newer releases are also supported with [WSLink SSL proxy addon](https://github.com/schizza/wslink-addon))
- Bresser stations that support custom server upload. [for example, this is known to work](https://www.bresser.com/p/bresser-wi-fi-clearview-weather-station-with-7-in-1-sensor-7002586)
- Garni stations with WSLink support or custom server support.

## Installation

### For stations that send data through WSLink API

Make sure you have your Home Assistant cofigured in SSL mode or use [WSLink SSL proxy addon](https://github.com/schizza/wslink-addon) to bypass SSL configuration of whole Home Assistant.

### HACS installation

For installation with HACS, you have to first add a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/).
You will need to enter the URL of this repository when prompted: `https://github.com/schizza/SWS-12500-custom-component`.

After adding this repository to HACS:

- Go to HACS -> Integrations
- Search for the integration `Sencor SWS 12500 Weather station` and download the integration.
- Restart Home Assistant
- Now go to `Integrations` and add new integration. Search for `Sencor SWS 12500 Weather station` and select it.

### Manual installation

For manual installation you must have an access to your Home Assistant's `/config` folder.

- Clone this repository or download [latest release here](https://github.com/schizza/SWS-12500-custom-component/releases/latest).

- Copy the `custom_components/sws12500-custom-component` folder to your `config/custom_components` folder in Home Assistant.
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

If you upgrade your station, that was previously sending data in PWS protocol, to station with WSLink protocol, you have to remove the integration a reinstall it. WSLink protocol is using metric scale instead of imperial used in PWS protocol.
So, deleteing integration and reinstalling will make sure, that sensors will be avare of change of the measurement scale. 

- as sensors unique IDs are the same, you will not loose any of historical data

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

## WSLink notes

While your station is using WSLink you have to have Home Assistant in SSL mode or behind SSL proxy server.
You can bypass whole SSL settings by using [WSLink SSL proxy addon](https://github.com/schizza/wslink-addon) which is made exactly for this integration to support WSLink on unsecured installations of Home Assistant.

### Configuration

- Set your station as [mentioned above](#configure-your-station-in-ap-mode) while changing `HA port` to be the port number you set in the addon (443 for example) not port of your Home Assistant instance. And that will do the trick!

```plain
HomeAssistant is at 192.0.0.2:8123
WSLink proxy addon listening on port 4443

you will set URL in station to: 192.0.0.2:4443
```

- Your station will be sending data to this SSL proxy and addon will handle the rest.

_Most of the stations does not care about self-signed certificates on the server side._
