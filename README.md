# Odyssey Tracker

A small project to track the position of the cruise ship **Villa Vie Odyssey**
and build a historical record of its travels.

## What is this?

[Villa Vie Odyssey](https://villa-vie.com/odyssey/) is a residential cruise
ship operated by Villa Vie Residences. Rather than offering conventional
cruises lasting a few days or weeks, Odyssey travels continuously around the
world, with passengers able to live aboard for extended periods.

This repository records the ship's position at regular intervals and stores
the resulting data in an SQLite database.

Villa Vie Odyssey is identified by:

* **IMO:** 9000699
* **MMSI:** 311541000

## Why?

Mostly because the data might be interesting.

Sites such as [CruiseMapper](https://www.cruisemapper.com/?imo=9000699) show
Odyssey's current position, but I wanted to collect my own historical data
that could later be used to examine and visualise the ship's travels.

The initial aim is deliberately modest: collect some data and see what it
looks like.

Once enough has accumulated, possible questions include:

* Where has Odyssey travelled?
* How long does it spend in particular ports?
* How fast does it travel between destinations?
* What route does it take between ports?
* How closely does its actual progress match its published itinerary?

But for now, this repository is primarily about **collecting the data before
deciding exactly what to do with it**.

## How does it work?

The project uses [AISStream](https://aisstream.io/) to receive AIS
(Automatic Identification System) messages transmitted by the ship.

The script:

```text
scripts/record_position.py
```

connects to the AISStream WebSocket service and subscribes to position reports
for a particular MMSI.

By default that is Villa Vie Odyssey:

```text
311541000
```

When a position report is received, useful information from the AIS message
is written to:

```text
data/odyssey.sqlite
```

The stored information includes:

* latitude and longitude
* speed over ground
* course over ground
* true heading
* navigational status
* rate of turn
* position accuracy
* AIS timestamp information
* MMSI and ship name
* the complete original AIS message as JSON

Keeping the raw AIS message means that information which turns out to be
interesting later hasn't been discarded simply because I didn't think to
use it at the start.

## Automatic collection

A GitHub Actions workflow runs the recorder every six hours.

Each run connects to AISStream and waits for a position report from Odyssey.
AIS is a live, event-driven system, so a position isn't necessarily available
immediately. The recorder can therefore be configured to wait for a specified
period before giving up.

The workflow runs the script in verbose mode so that the Actions log shows
connection and progress information while it waits.

A typical run looks like:

```text
[09:34:52 UTC] Connecting to AISStream for MMSI 311541000...
[09:34:52 UTC] Connected. Sending subscription...
[09:34:52 UTC] Waiting up to 300 seconds for a position report...
[09:34:53 UTC] Subscription confirmed (compression=True).
[09:35:22 UTC] Still waiting for an AIS position report (30s elapsed)...
[09:35:52 UTC] Still waiting for an AIS position report (60s elapsed)...
[09:36:22 UTC] Still waiting for an AIS position report (90s elapsed)...
[09:36:52 UTC] Still waiting for an AIS position report (120s elapsed)...
[09:37:22 UTC] Still waiting for an AIS position report (150s elapsed)...
2026-08-30T09:37:41.169167+00:00 22.295400 114.166650 SOG=0 COG=168.2 heading=78
[09:37:41 UTC] Position received after 169s and saved to data/odyssey.sqlite.
```

The updated SQLite database is then committed back to this repository.

At four observations per day, this should produce roughly 1,460 observations
per year.

## Running it locally

The recorder requires Python and the `websockets` package.

Install the dependency with:

```bash
pip install websockets
```

An AISStream API key is required and should be supplied in the environment:

```bash
export AISSTREAM_API_KEY="..."
```

Then run:

```bash
./scripts/record_position.py
```

For progress information while waiting:

```bash
./scripts/record_position.py --verbose
```

The MMSI and timeout can also be configured, making the script usable for
ships other than Odyssey:

```bash
./scripts/record_position.py \
    --mmsi 311541000 \
    --timeout 900 \
    --verbose
```

They can alternatively be supplied using environment variables:

```bash
export AIS_MMSI=311541000
export AIS_TIMEOUT=900

./scripts/record_position.py --verbose
```

Command-line options take precedence over environment settings.

## The database

The database is deliberately committed to the repository.

Normally committing a database file to Git would be questionable, but this
one is small, append-only and is itself one of the outputs of the project.

It also means that anyone cloning the repository immediately gets the
complete dataset collected so far.

For example:

```bash
sqlite3 data/odyssey.sqlite
```

and:

```sql
SELECT
    received_at,
    latitude,
    longitude,
    speed_over_ground,
    course_over_ground,
    true_heading
FROM positions
ORDER BY received_at;
```

## What's next?

The first goal is simply to **collect at least a week's worth of data**.

After that, there are several directions the project could take.

The obvious one is a web-based map showing Odyssey's route. A static site
hosted using GitHub Pages could export the SQLite data to JSON and display it
using something like Leaflet and OpenStreetMap.

With enough data it should also be possible to identify port visits, calculate
distances travelled, distinguish time at sea from time in port, and build a
timeline of the ship's journey.

Another possibility is to obtain historical AIS data and backfill the
database with Odyssey's positions from before this project started.

For now, though, the plan is simple:

**Collect first. Work out what to do with it later.**

## Data source

Live AIS data is provided by [AISStream](https://aisstream.io/).

AIS data should not be treated as a perfect historical record. Reports may be
missing because of reception coverage, transmission intervals or other
factors, and some fields are manually configured aboard the vessel.

This project therefore records observations received from AISStream rather
than claiming to provide an authoritative record of Odyssey's movements.

## Licence

The software in this repository is licensed under the
[MIT Licence](LICENSE).

The vessel position data stored in `data/odyssey.sqlite` is obtained from
AISStream and is **not** covered by the MIT Licence. Rights in the underlying
AIS data remain subject to the terms of the relevant data providers.

AISStream does not currently publish clear licensing terms covering the
redistribution of accumulated historical AIS data. Until that is clarified,
no separate licence is asserted for the contents of the SQLite database.

The intention is to make both the software and, where licensing permits, the
collected dataset as freely reusable as possible.

