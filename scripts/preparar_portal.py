from pathlib import Path
import json
import shutil

import geopandas as gpd
import numpy as np


# ============================================================
# CONFIGURACION
# ============================================================

VOLCAN = "Palmares_Cenizosa"
VOLCAN_ID = "palmares_cenizosa"
VOLCAN_CARPETA = "Palmares_Cenizosa"

FECHA = "20260911"

BASE = Path(
    "/run/media/spinedas1/Seagate/"
    "Diapiros/Desarrollos/InSAR/SBAS"
)

PIPELINE = BASE / "Geoportal"
GEOPORTAL = BASE / "Geoportal"

RESULTADOS = (
    PIPELINE
    / "data/rasters"
    / VOLCAN
    / FECHA
)

DATA = GEOPORTAL / "data"


# ============================================================
# ARCHIVOS PRODUCIDOS POR generar_mapas.py
# ============================================================

RASTER_ORIGEN = (
    RESULTADOS
    / f"{FECHA}.tif"
)

GPKG_ORIGEN = (
    RESULTADOS
    / f"{VOLCAN}_{FECHA}.gpkg"
)


# ============================================================
# DESTINOS WEB
# ============================================================

RASTER_DESTINO = (
    DATA
    / "rasters"
    / VOLCAN_CARPETA
    / f"{FECHA}.tif"
)

AREA_DESTINO = (
    DATA
    / "areas"
    / f"{VOLCAN_CARPETA}.geojson"
)

FLUJOS_DESTINO = (
    DATA
    / "flujos"
    / f"{VOLCAN_CARPETA}.geojson"
)

ESTADISTICAS_DESTINO = (
    DATA
    / "estadisticas"
    / VOLCAN_CARPETA
    / f"{FECHA}.json"
)

METADATA_DESTINO = (
    DATA
    / "metadata"
    / f"{VOLCAN_CARPETA}.json"
)

CATALOGO = DATA / "catalog.json"
VOLCANES_GEOJSON = DATA / "volcanes.geojson"
PUNTOS_VOLCANICOS = Path(
    "/run/media/spinedas1/Seagate/Diapiros/Desarrollos/QGIS/"
    "volcanes-lodo/Volcanes_flujos/volcanes_lodo_pt.shp"
)


# ============================================================
# CREAR CARPETAS
# ============================================================

for carpeta in [
    RASTER_DESTINO.parent,
    AREA_DESTINO.parent,
    FLUJOS_DESTINO.parent,
    ESTADISTICAS_DESTINO.parent,
    METADATA_DESTINO.parent,
]:

    carpeta.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# COPIAR RASTER
# ============================================================

if not RASTER_ORIGEN.exists():
    raise FileNotFoundError(
        f"No existe:\n{RASTER_ORIGEN}"
    )

shutil.copy2(
    RASTER_ORIGEN,
    RASTER_DESTINO
)

print("Raster:", RASTER_DESTINO)


# ============================================================
# LEER CAPAS DEL GEOPACKAGE
# ============================================================

desplazamiento = gpd.read_file(
    GPKG_ORIGEN,
    layer="desplazamiento"
)

area = gpd.read_file(
    GPKG_ORIGEN,
    layer="area_estudio"
)

area = area.to_crs("EPSG:4326")

area.to_file(
    AREA_DESTINO,
    driver="GeoJSON"
)


# ============================================================
# FLUJOS HISTORICOS
# ============================================================

try:

    flujos = gpd.read_file(
        GPKG_ORIGEN,
        layer="flujos_historicos"
    )

    flujos = flujos.to_crs("EPSG:4326")

    flujos.to_file(
        FLUJOS_DESTINO,
        driver="GeoJSON"
    )

except Exception:

    print(
        "No se encontro capa "
        "flujos_historicos."
    )


# ============================================================
# ESTADISTICAS GENERALES
# ============================================================

valores = (
    desplazamiento["disp_cm"]
    .replace([np.inf, -np.inf], np.nan)
    .dropna()
)

categorias = (
    desplazamiento
    .groupby(
        ["clase", "categoria"]
    )
    .size()
    .reset_index(
        name="pixeles"
    )
    .sort_values("clase")
)


estadisticas = {

    "fecha": FECHA,

    "unidad": "cm",

    "pixeles_validos":
        int(len(valores)),

    "minimo_cm":
        float(valores.min()),

    "maximo_cm":
        float(valores.max()),

    "promedio_cm":
        float(valores.mean()),

    "mediana_cm":
        float(valores.median()),

    "desviacion_cm":
        float(valores.std()),

    "categorias": [
        {
            "nombre":
                str(fila["categoria"]),

            "pixeles":
                int(fila["pixeles"])
        }

        for _, fila
        in categorias.iterrows()
    ]
}


with open(
    ESTADISTICAS_DESTINO,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        estadisticas,
        archivo,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# METADATA
# ============================================================

metadata = {

    "id":
        VOLCAN_ID,

    "nombre":
        VOLCAN,

    "descripcion":
        (
            "Sitio de monitoreo de cambios "
            "en la superficie mediante "
            "observaciones satelitales."
        ),

    "sensor":
        "SAOCOM",

    "metodo":
        "InSAR",

    "procesamiento":
        "ISCE + MintPy",

    "geometria":
        "Ascendente 463",

    "variable_tecnica":
        "Desplazamiento LOS",

    "variable_publica":
        "Cambio observado en la superficie",

    "unidad_raster":
        "m",

    "unidad_visualizacion":
        "cm",

    "crs":
        "EPSG:4326",

    "nota":
        (
            "La información presentada "
            "tiene carácter informativo."
        )
}


with open(
    METADATA_DESTINO,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        metadata,
        archivo,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# PUNTO OFICIAL DEL VOLCAN
# ============================================================

puntos = gpd.read_file(PUNTOS_VOLCANICOS)
if puntos.crs is None or "name" not in puntos:
    raise ValueError("La capa oficial debe tener CRS y campo 'name'.")

nombre_punto = VOLCAN.replace("_", " ").strip().casefold()
puntos_volcan = puntos[
    puntos["name"].astype(str).str.strip().str.casefold() == nombre_punto
]
if len(puntos_volcan) != 1 or puntos_volcan.geometry.iloc[0].geom_type != "Point":
    raise ValueError(f"No se encontró un único punto oficial para {VOLCAN!r}.")

punto = puntos_volcan.to_crs(4326).geometry.iloc[0]

feature = {

    "type": "Feature",

    "properties": {
        "id": VOLCAN_ID,
        "nombre": VOLCAN
    },

    "geometry": {
        "type": "Point",

        "coordinates": [
            punto.x,
            punto.y
        ]
    }
}


volcanes_geojson = {
    "type": "FeatureCollection",
    "features": [
        feature
    ]
}


with open(
    VOLCANES_GEOJSON,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        volcanes_geojson,
        archivo,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# CATALOGO
# ============================================================

catalogo = {

    "version": 1,

    "volcanes": [

        {
            "id":
                VOLCAN_ID,

            "nombre":
                VOLCAN,

            "metadata":
                (
                    "./data/metadata/"
                    f"{VOLCAN_CARPETA}.json"
                ),

            "area":
                (
                    "./data/areas/"
                    f"{VOLCAN_CARPETA}.geojson"
                ),

            "flujos":
                (
                    "./data/flujos/"
                    f"{VOLCAN_CARPETA}.geojson"
                ),

            "fechas": [

                {
                    "fecha":
                        FECHA,

                    "raster":
                        (
                            "./data/rasters/"
                            f"{VOLCAN_CARPETA}/"
                            f"{FECHA}.tif"
                        ),

                    "estadisticas":
                        (
                            "./data/estadisticas/"
                            f"{VOLCAN_CARPETA}/"
                            f"{FECHA}.json"
                        )
                }
            ]
        }
    ]
}


with open(
    CATALOGO,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        catalogo,
        archivo,
        indent=2,
        ensure_ascii=False
    )


print()
print("==============================")
print("PORTAL PREPARADO")
print("==============================")
print("Volcan:", VOLCAN)
print("Fecha :", FECHA)
print()
