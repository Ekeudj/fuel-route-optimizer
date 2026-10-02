import os
import traceback
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .services import FuelOptimizer
from .utils import load_city_index, load_stations
from .mapview import render_map_html, simplify

# These run ONCE when the server starts, not on every request this keeps it fast!!
DATA_DIR = os.path.join(settings.BASE_DIR, "data")
CITY_INDEX = load_city_index(os.path.join(DATA_DIR, "city_coords.csv"))
STATIONS = load_stations(os.path.join(DATA_DIR, "fuel_data.csv"), CITY_INDEX)


def calculate_fuel(request):
    if not STATIONS:
        return JsonResponse({"status": "error", "message": "Fuel data failed to load at startup."}, status=500)

    start_loc = request.GET.get("start")
    end_loc = request.GET.get("end")
    if not start_loc or not end_loc:
        return JsonResponse({"status": "error", "message": "Use format: ?start=City,ST&end=City,ST"}, status=400)

    try:
        result = FuelOptimizer(STATIONS, CITY_INDEX).calculate_optimal_itinerary(start_loc, end_loc)
        if "error" in result:
            return JsonResponse({"status": "error", "message": result["error"]}, status=400)

        # Visual map page depending on what user calls
        if request.GET.get("format") == "map":
            return HttpResponse(render_map_html(result))

        # Default: JSON, with the route shrunk to 300 points so it's not huge
        result["map_of_the_route"]["coordinates"] = simplify(result["map_of_the_route"]["coordinates"], 300)
        result["map_view_url"] = request.build_absolute_uri().split("&format")[0] + "&format=map"
        return JsonResponse({"status": "success", "data": result})

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"status": "error", "message": f"Internal error: {e}"}, status=500)