# Architecture

## Overview

The integration is organized around one Home Assistant config entry per account, with one or more selected HomGar/RainPoint homes (`hid`) stored inside that entry.

Main layers:
- `config_flow.py` validates credentials, selects homes, and stores account data
- `api/client.py` handles cloud authentication and REST calls
- `coordinator.py` fetches hubs and device status on a polling interval
- `mqtt_client.py` and `coordinator_mqtt.py` overlay real-time updates on top of the REST snapshot
- `decoder.py` is the shared decoding layer for both REST and MQTT payloads
- entity platforms (`sensor.py`, `valve.py`, `number.py`) stay thin and read from coordinator state

## Account Model

One config entry stores:
- account credentials
- app type (`homgar` or `rainpoint`)
- selected home IDs (`hids`)
- cached token and MQTT credential state

The integration supports multiple accounts. Each account can include multiple selected homes.

## Polling Flow

`HomGarCoordinator` performs the periodic full refresh.

High-level flow:
1. Fetch selected homes and home names
2. Fetch hubs/devices for each selected `hid`
3. Fetch device status, preferring `multipleDeviceStatus`
4. Decode raw payloads with `decode_payload(model, payload)`
5. Normalize the result into `coordinator.data`

Coordinator data is keyed primarily as:
- `hubs`
- `status`
- `sensors`
- `mqtt_diagnostics`

## MQTT Flow

MQTT is a real-time overlay, not a separate source of truth.

High-level flow:
1. Initial setup discovers hubs via REST
2. `subscribeStatus` returns fresh per-session MQTT credentials
3. `HomGarMQTTClient` subscribes to the five `/sys/` topics
4. Incoming messages are parsed into `hub_mid`, `device_key`, and payload
5. `coordinator_mqtt.py` decodes the payload and updates coordinator state

Important rules:
- runtime MQTT credentials come from `subscribeStatus`
- reconnects regenerate the Aliyun HMAC timestamp
- REST remains the fallback reconciliation path

## Decoder Contract

`decode_payload(model, payload)` is the shared decode API used by both REST and MQTT paths.

Design expectations:
- decoding is data-driven via `product_models.json`
- new model support should usually start in `product_models.json`
- only add custom decoder logic when a model truly requires it

Decoder output is normalized into field names like:
- `temperature`
- `humidity`
- `soil_moisture`
- `battery_level`
- `signal_strength`
- `port_1`, `port_2`, etc. for multi-port devices

## Entity Creation

Entity platforms build from the normalized coordinator snapshot.

Patterns:
- hub diagnostic entities come from `hubs`
- generic sensors come from decoded fields plus `sensor_defs.py`
- valve entities are created from `get_valve_ports(model)`
- duration number entities are created per valve zone

Entity identity rules:
- preserve entity unique IDs once published
- preserve device unique IDs once published
- avoid changing display names unless the user-facing benefit is clear

## REST vs MQTT Responsibilities

REST is responsible for:
- authentication
- home and hub discovery
- periodic full-state reconciliation
- control endpoints

MQTT is responsible for:
- fast real-time state propagation
- live updates between poll intervals

Both paths must continue to share the same decoder and normalized field model.
