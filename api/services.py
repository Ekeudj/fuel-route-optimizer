import math
import os
import requests
from dotenv import load_dotenv
from .utils import lookup_city

load_dotenv()

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
MAX_RANGE = 500        # miles the truck can go on a full tank
MPG = 10               # miles per gallon
CORRIDOR_MILES = 10    # how far from the route a station can be


# standard formula for distance btn 2 lat and lon pts
#helps in finding closet station to the route
def miles_between(lat1, lon1, lat2, lon2):
    """Straight-line distance between two lat/lon points in miles haversine formula"""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(a))


class FuelOptimizer:
    def __init__(self, stations, city_index):
        self.stations = stations          # list of station dicts (with lat/lon)
        self.city_index = city_index      # {(city, state): (lat, lon)}
        self.api_key = os.getenv("ORS_API_KEY")

    # Turn "City,ST" into coordinates, i dont call any API
    def get_coordinates(self, text):
        if text and "," in text:
            city, state = text.rsplit(",", 1)
            found = lookup_city(self.city_index, city, state)
            if found:
                lat, lon = found
                return [lon, lat]         # ORS needs [longitude, latitude]
        return None

    # Only call to the routing API 
    def get_route(self, start, end):
        if not self.api_key:
            return None, "ORS_API_KEY missing, add it to your .env file."
        try:
            response = requests.post(
                ORS_URL,
                headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                json={"coordinates": [start, end],
                      "radiuses": [-1, -1],       # don't reject cities far from a road
                      "instructions": False},     # smaller, faster response
                timeout=30,
            )
        except Exception as e:
            return None, f"Routing request failed: {e}"

        if response.status_code != 200:
            return None, f"OpenRouteService error {response.status_code}: {response.text[:200]}"
        return response.json()["features"][0], None

    # Which stations are near the route
    def find_stations_on_route(self, route_coords, total_miles):
        # 3a. Walk along the route, keeping a point roughly every 3 miles,
        #     and remember how many miles from the start each point is.
        points = []                       # each item: (lat, lon, mile_from_start)
        miles_so_far = 0.0
        last_kept_mile = None
        previous = None
        for lon, lat in route_coords:
            if previous:
                miles_so_far += miles_between(previous[0], previous[1], lat, lon)
            previous = (lat, lon)
            if last_kept_mile is None or miles_so_far - last_kept_mile >= 3:
                points.append((lat, lon, miles_so_far))
                last_kept_mile = miles_so_far
        points.append((previous[0], previous[1], miles_so_far))

        # Our straight-line mileage differs slightly from ORS's road mileage,
        # so scale the mile markers to match ORS's official total.
        scale = total_miles / miles_so_far if miles_so_far else 1

        # 3b. Cheap filter: ignore stations outside the route's bounding box.
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        min_lat, max_lat = min(lats) - 0.5, max(lats) + 0.5
        min_lon, max_lon = min(lons) - 0.7, max(lons) + 0.7

        # 3c. For each remaining station, find the closest route point.
        #     If it's within the corridor, the station counts as "on the route".
        found = []
        for st in self.stations:
            if not (min_lat < st["lat"] < max_lat and min_lon < st["lon"] < max_lon):
                continue
            best_distance, best_mile = None, None
            for lat, lon, mile in points:
                if abs(st["lat"] - lat) > 0.3:      # too far north/south, skip the math
                    continue
                d = miles_between(st["lat"], st["lon"], lat, lon)
                if best_distance is None or d < best_distance:
                    best_distance, best_mile = d, mile
            if best_distance is not None and best_distance <= CORRIDOR_MILES:
                found.append({"mile": best_mile * scale, "price": st["price"], "station": st})

        found.sort(key=lambda s: s["mile"])
        return found

    # decide where to buy fuel,core alogorithm greedy apprroach 
    def plan_fuel_stops(self, stops, total_miles):
        # The truck starts with an empty tank. Price the first fill-up at the
        # average of stations within 50 miles of the start (or $3.50 if none).
        near_start = [s["price"] for s in stops if s["mile"] <= 50]
        start_price = sum(near_start) / len(near_start) if near_start else 3.50

        # A "node" is any place we could buy fuel: start, each station, and the end.
        nodes = [{"mile": 0.0, "price": start_price, "station": None}]
        nodes += stops
        nodes.append({"mile": total_miles, "price": 0.0, "station": None})
        last = len(nodes) - 1

        position = 0          # index of the node we're standing at
        fuel = 0.0            # miles of driving left in the tank
        purchases = []        # list of (node, miles_of_fuel_bought)

        while position < last:
            here = nodes[position]

            # Every node we can reach from here without running dry
            reachable = []
            j = position + 1
            while j <= last and nodes[j]["mile"] - here["mile"] <= MAX_RANGE:
                reachable.append(j)
                j += 1
            if not reachable:
                raise ValueError(f"No fuel station within {MAX_RANGE} miles after mile {here['mile']:.0f}.")

            # Is there a CHEAPER station within range?
            cheaper = None
            for j in reachable:
                if nodes[j]["price"] < here["price"]:
                    cheaper = j
                    break

            if cheaper is not None:
                # Yes: buy only enough fuel to reach it, then buy there instead.
                next_stop = cheaper
                distance = nodes[next_stop]["mile"] - here["mile"]
                buy = max(0.0, distance - fuel)
            else:
                # No: this is the cheapest around. Fill the tank, then
                # drive to the cheapest station we can reach.
                next_stop = min(reachable, key=lambda k: nodes[k]["price"])
                distance = nodes[next_stop]["mile"] - here["mile"]
                buy = MAX_RANGE - fuel

            fuel = fuel + buy - distance
            if buy > 0.000001:
                purchases.append((here, buy))
            position = next_stop

        # Turn the purchases into the final itinerary and total cost
        total_cost = 0.0
        itinerary = []
        for node, miles_bought in purchases:
            gallons = miles_bought / MPG
            cost = gallons * node["price"]
            total_cost += cost
            st = node["station"]
            if st:   # skip the imaginary "start" node
                itinerary.append({
                    "truckstop": st["name"],
                    "address": st["address"],
                    "city": st["city"],
                    "state": st["state"],
                    "price_per_gallon": round(st["price"], 3),
                    "mile_marker": round(node["mile"], 1),
                    "gallons_purchased": round(gallons, 2),
                    "cost_usd": round(cost, 2),
                    "location": {"lat": st["lat"], "lon": st["lon"]},
                })
        return itinerary, total_cost, start_price

    # main entry point called by the view
    def calculate_optimal_itinerary(self, start_loc, end_loc):
        start = self.get_coordinates(start_loc)
        end = self.get_coordinates(end_loc)
        if not start or not end:
            return {"error": f"Could not locate '{start_loc}' or '{end_loc}'. Use format City,ST (e.g. Daleville,IN)."}

        feature, error = self.get_route(start, end)
        if error:
            return {"error": error}

        total_miles = feature["properties"]["summary"]["distance"] * 0.000621371
        geometry = feature["geometry"]

        stops = self.find_stations_on_route(geometry["coordinates"], total_miles)
        try:
            itinerary, cost, start_price = self.plan_fuel_stops(stops, total_miles)
        except ValueError as e:
            return {"error": str(e)}

        return {
            "map_of_the_route": geometry,
            "start": {"query": start_loc, "lon": start[0], "lat": start[1]},
            "end": {"query": end_loc, "lon": end[0], "lat": end[1]},
            "total_miles": round(total_miles, 2),
            "total_gallons": round(total_miles / MPG, 2),
            "total_money_spent_on_fuel_usd": round(cost, 2),
            "optimal_fuel_stops_along_route": itinerary,
            "assumptions": {
                "mpg": MPG,
                "max_range_miles": MAX_RANGE,
                "station_search_corridor_miles": CORRIDOR_MILES,
                "start_fuel_price_estimate": round(start_price, 3),
                "note": "Trip starts with an empty tank; fuel at the start is priced at the average of stations within 50 miles of the start.",
            },
        }