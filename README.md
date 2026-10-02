# Fuel Route Optimizer API

A Django API that takes a start and finish location in the USA and returns:

- the driving route (GeoJSON) and an optional visual map page
- the cheapest fuel stops along the route, based on the supplied fuel price file
- the total money spent on fuel

Assumptions from the brief: the vehicle has a **500-mile range** and gets **10 miles per gallon**.

## Quick start

```bash
git clone <your-repo-url>
cd <repo-folder>
python -m venv venv
venv\Scripts\activate          # Windows  (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

Create a `.env` file next to `manage.py` (see `.env.example`):

```
ORS_API_KEY=your_openrouteservice_key
```

Get a free key at https://openrouteservice.org/dev/signup

Put the fuel price file at `data/fuel_data.csv`, then run:

```bash
python manage.py runserver
```

On first start the app builds a US city-coordinates table from the free GeoNames dataset and caches it at `data/city_coords.csv` (this is committed, so you can skip the download).

## Usage

```
GET /api/calculate-fuel/?start=Los Angeles,CA&end=New York,NY
```

| Parameter | Description |
|---|---|
| `start` | Start location as `City,ST` |
| `end` | End location as `City,ST` |
| `format` | Optional. `map` returns a visual HTML map instead of JSON |

### Example response (shortened)

```json
{
  "status": "success",
  "data": {
    "map_of_the_route": { "type": "LineString", "coordinates": [[-118.24, 34.05], "..."] },
    "total_miles": 2790.4,
    "total_gallons": 279.04,
    "total_money_spent_on_fuel_usd": 912.35,
    "optimal_fuel_stops_along_route": [
      {
        "truckstop": "PILOT TRAVEL CENTER #1243",
        "city": "Gila Bend",
        "state": "AZ",
        "price_per_gallon": 3.899,
        "mile_marker": 358.2,
        "gallons_purchased": 50.0,
        "cost_usd": 194.95
      }
    ]
  }
}
```

Errors return `{"status": "error", "message": "..."}` with a 400 (bad input) or 500 (server error).

## How it works

1. **Startup (once):** the fuel CSV is loaded into memory. Each station is given coordinates from a local city lookup table, so no geocoding API is needed.
2. **Per request, one external API call:** start and end are resolved locally, then a single request to OpenRouteService returns the route and total distance.
3. **Stations near the route:** stations within 10 miles of the route are kept, each with a mile marker (distance from the start).
4. **Fuel planning (greedy algorithm):** at each stop, look at everything reachable within 500 miles. If a cheaper station is ahead, buy only enough fuel to reach it. If none is, fill the tank here and continue to the cheapest reachable station.
5. **Cost:** gallons bought at each stop multiplied by that stop's price, summed.

## Project structure

```
api/
  utils.py      loads the city table and fuel stations (runs once at startup)
  views.py      the endpoint: validation and JSON/map responses
  services.py   routing call, station filtering, fuel planning
  mapview.py    optional SVG map page (no external calls)
  urls.py       route definition
data/
  fuel_data.csv
  city_coords.csv
```

## Performance

- 1 call to the routing API per request (geocoding is done locally)
- Station data is held in memory, so there are no database or file reads per request
- The JSON route is downsampled to about 300 points to keep responses small

## Assumptions and limitations

- The fuel data has no coordinates, so stations are placed at their **city center**. A 10-mile search corridor around the route compensates for this.
- The vehicle starts with an **empty tank**. The first fill-up is priced at the average of stations within 50 miles of the start.
- Locations must be given as `City,ST`.

## Possible improvements

- Store exact station coordinates and use a spatial index
- Cache routes for repeated trips
- Add a maximum-detour limit and unit tests
