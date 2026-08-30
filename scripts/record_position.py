#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import websockets


DEFAULT_TIMEOUT = 300

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

HEARTBEAT_INTERVAL = 30

def database_path(mmsi):
    return Path("data") / f"{mmsi}.sqlite"

def utc_now():
    return datetime.now(timezone.utc)


def log(message, *, verbose=False):
    if verbose:
        timestamp = utc_now().strftime("%H:%M:%S")
        print(f"[{timestamp} UTC] {message}", flush=True)


def initialise_database(database):
    database.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id                    INTEGER PRIMARY KEY,

                received_at           TEXT NOT NULL,

                latitude              REAL NOT NULL,
                longitude             REAL NOT NULL,

                speed_over_ground     REAL,
                course_over_ground    REAL,
                true_heading          INTEGER,
                navigational_status   INTEGER,
                rate_of_turn          INTEGER,

                position_accuracy     INTEGER,
                raim                  INTEGER,
                ais_timestamp_second  INTEGER,

                special_manoeuvre     INTEGER,
                repeat_indicator      INTEGER,
                communication_state   INTEGER,

                message_id            INTEGER,
                valid                 INTEGER,

                ship_name             TEXT,
                mmsi                  TEXT NOT NULL,

                source                TEXT NOT NULL DEFAULT 'aisstream',

                raw_json              TEXT,

                UNIQUE (
                    received_at,
                    latitude,
                    longitude
                )
            )
        """)


def save_position(message, mmsi, database):
    metadata = message["MetaData"]
    report = message["Message"]["PositionReport"]

    received_at = utc_now().isoformat()

    row = {
        "received_at": received_at,

        "latitude": metadata.get("Latitude", report.get("Latitude")),
        "longitude": metadata.get("Longitude", report.get("Longitude")),

        "speed_over_ground": report.get("Sog"),
        "course_over_ground": report.get("Cog"),
        "true_heading": report.get("TrueHeading"),
        "navigational_status": report.get("NavigationalStatus"),
        "rate_of_turn": report.get("RateOfTurn"),

        "position_accuracy": report.get("PositionAccuracy"),
        "raim": report.get("Raim"),
        "ais_timestamp_second": report.get("Timestamp"),

        "special_manoeuvre": report.get("SpecialManoeuvreIndicator"),
        "repeat_indicator": report.get("RepeatIndicator"),
        "communication_state": report.get("CommunicationState"),

        "message_id": report.get("MessageID"),
        "valid": report.get("Valid"),

        "ship_name": metadata.get("ShipName"),
        "mmsi": str(metadata.get("MMSI", mmsi)),

        "source": "aisstream",

        # Keeping the complete message is cheap and gives us an escape
        # hatch if we realise later that there was another useful field.
        "raw_json": json.dumps(message, separators=(",", ":")),
    }

    with sqlite3.connect(database) as db:
        db.execute("""
            INSERT INTO positions (
                received_at,
                latitude,
                longitude,
                speed_over_ground,
                course_over_ground,
                true_heading,
                navigational_status,
                rate_of_turn,
                position_accuracy,
                raim,
                ais_timestamp_second,
                special_manoeuvre,
                repeat_indicator,
                communication_state,
                message_id,
                valid,
                ship_name,
                mmsi,
                source,
                raw_json
            )
            VALUES (
                :received_at,
                :latitude,
                :longitude,
                :speed_over_ground,
                :course_over_ground,
                :true_heading,
                :navigational_status,
                :rate_of_turn,
                :position_accuracy,
                :raim,
                :ais_timestamp_second,
                :special_manoeuvre,
                :repeat_indicator,
                :communication_state,
                :message_id,
                :valid,
                :ship_name,
                :mmsi,
                :source,
                :raw_json
            )
        """, row)

    return row


async def heartbeat(verbose, started):
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)

        elapsed = int(
            (utc_now() - started).total_seconds()
        )

        log(
            f"Still waiting for an AIS position report "
            f"({elapsed}s elapsed)...",
            verbose=verbose,
        )


async def get_position(mmsi, timeout, database, verbose=False):
    try:
        api_key = os.environ["AISSTREAM_API_KEY"]
    except KeyError:
        print(
            "Error: AISSTREAM_API_KEY is not set",
            file=sys.stderr,
        )
        return 2

    subscription = {
        "APIKey": api_key,

        # AISStream requires at least one bounding box. This covers
        # the whole world; the MMSI filter then limits the traffic
        # returned to Odyssey.
        "BoundingBoxes": [
            [
                [-90, -180],
                [90, 180],
            ]
        ],

        "FiltersShipMMSI": [mmsi],
        "FilterMessageTypes": ["PositionReport"],
    }

    log(
        f"Connecting to AISStream for MMSI {mmsi}...",
        verbose=verbose,
    )

    started = utc_now()

    try:
        async with websockets.connect(
            AISSTREAM_URL,
            compression="deflate",
        ) as websocket:

            log(
                "Connected. Sending subscription...",
                verbose=verbose,
            )

            await websocket.send(json.dumps(subscription))

            log(
                f"Waiting up to {timeout} seconds "
                "for a position report...",
                verbose=verbose,
            )

            heartbeat_task = asyncio.create_task(
                heartbeat(verbose, started)
            )

            try:
                async with asyncio.timeout(timeout):
                    async for raw_message in websocket:

                        if isinstance(raw_message, bytes):
                            raw_message = raw_message.decode("utf-8")

                        message = json.loads(raw_message)

                        if (
                            message.get("MessageType")
                            == "SubscriptionConfirmation"
                        ):
                            compression = (
                                message
                                .get("Message", {})
                                .get("CompressionEnabled")
                            )

                            log(
                                "Subscription confirmed "
                                f"(compression={compression}).",
                                verbose=verbose,
                            )
                            continue

                        if (
                            message.get("MessageType")
                            != "PositionReport"
                        ):
                            continue

                        metadata = message.get("MetaData", {})

                        if str(metadata.get("MMSI")) != mmsi:
                            continue

                        row = save_position(message, mmsi, database)

                        elapsed = int(
                            (
                                utc_now() - started
                            ).total_seconds()
                        )

                        print(
                            f"{row['received_at']} "
                            f"{row['latitude']:.6f} "
                            f"{row['longitude']:.6f} "
                            f"SOG={row['speed_over_ground']} "
                            f"COG={row['course_over_ground']} "
                            f"heading={row['true_heading']}"
                        )

                        log(
                            f"Position received after "
                            f"{elapsed}s and saved to {database}.",
                            verbose=verbose,
                        )

                        return 0

            finally:
                heartbeat_task.cancel()

                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    except TimeoutError:
        print(
            f"No position report received within "
            f"{timeout} seconds.",
            file=sys.stderr,
        )
        return 1

    except Exception as exc:
        print(
            f"AISStream error: {exc}",
            file=sys.stderr,
        )
        return 1


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record the current AIS position of a vessel."
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show connection status and waiting progress",
    )

    parser.add_argument(
        "-m",
        "--mmsi",
        default=os.environ.get("AIS_MMSI"),
        help="MMSI of vessel to track (or set $AIS_MMSI)",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=int(
            os.environ.get("AIS_TIMEOUT", DEFAULT_TIMEOUT)
        ),
        help=(
            "seconds to wait for a position report "
            f"(default: $AIS_TIMEOUT or {DEFAULT_TIMEOUT})"
        ),
    )

    args = parser.parse_args()

    if not args.mmsi:
        parser.error(
            "An MMSI is required. use --mmsi or set AIS_MMSI"
        )

    return parser.parse_args()


def main():
    args = parse_args()

    database = database_path(args.mmsi)

    initialise_database(database)

    return asyncio.run(
        get_position(
            mmsi=args.mmsi,
            timeout=args.timeout,
            database=database,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
