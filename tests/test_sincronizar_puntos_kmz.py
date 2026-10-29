import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sincronizar_puntos_kmz import crear_geojson


class SincronizarPuntosKmzTest(unittest.TestCase):
    def test_incluye_puntos_sin_insar_y_conserva_ids_reconocidos(self):
        puntos = gpd.GeoDataFrame(
            {"Name": ["Sitio monitoreado", "Alias KMZ", "Nuevo Volcán"]},
            geometry=[Point(-76.5, 8.3), Point(-76.4, 8.4), Point(-76.3, 8.5)],
            crs="EPSG:4326",
        )
        catalogo = {"volcanes": [{"id": "sitio_monitoreado", "nombre": "Sitio monitoreado"}]}
        actuales = {
            "features": [
                {"type": "Feature", "properties": {"id": "sitio_monitoreado", "nombre": "Sitio monitoreado"}}
            ]
        }
        config = {
            "volcanes": [
                {"id": "sitio_monitoreado", "nombre": "Sitio monitoreado"},
                {"id": "melito_alto", "nombre": "Melito Alto", "nombre_punto": "Alias KMZ"},
            ]
        }

        geojson = crear_geojson(puntos, catalogo, actuales, config)

        self.assertEqual(len(geojson["features"]), 3)
        self.assertEqual(
            [feature["properties"]["id"] for feature in geojson["features"]],
            ["sitio_monitoreado", "melito_alto", "nuevo_volcan"],
        )
        self.assertEqual(geojson["features"][2]["geometry"]["coordinates"], [-76.3, 8.5])


if __name__ == "__main__":
    unittest.main()