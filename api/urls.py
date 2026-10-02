# api/urls.py (The Specific Route)
from django.urls import path
from .views import calculate_fuel

urlpatterns = [
    # This maps the actual endpoint. 
    # When the user hits /api/calculate-fuel/, this function is triggered.
    path('calculate-fuel/', calculate_fuel, name='calculate_fuel'),
]