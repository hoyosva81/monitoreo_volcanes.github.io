"""Actualiza los puntos del mapa general desde volcanes_lodo.kmz."""
import argparse
import json
import math
from pathlib import Path
import re
import unicodedata

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]


def leer_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def normalizar(value):
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    return "".join(char for char in text if char.isalnum() and not unicodedata.combining(char))


def crear_slug(value):
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def crear_geojson(puntos, catalogo, puntos_actuales, config):
    if puntos.crs is None:
        raise ValueError("El KMZ debe tener un sistema de coordenadas definido.")

    campo_nombre = config.get("campo_nombre_kmz", "Name")
    if campo_nombre not in puntos:
        raise ValueError(f"El KMZ debe tener el campo {campo_nombre!r}.")

    id_por_nombre = {}
    for feature in puntos_actuales.get("features", []):
        propiedades = feature.get("properties", {})
        nombre = propiedades.get("nombre")
        volcan_id = propiedades.get("id")
        if nombre and volcan_id:
            id_por_nombre[normalizar(nombre)] = volcan_id

    for volcan in catalogo.get("volcanes", []):
        if volcan.get("nombre") and volcan.get("id"):
            id_por_nombre.setdefault(normalizar(volcan["nombre"]), volcan["id"])

    for volcan in config.get("volcanes", []):
        volcan_id = volcan.get("id")
        if not volcan_id:
            continue
        for nombre in (volcan.get("nombre"), volcan.get("nombre_punto")):
            if nombre:
                id_por_nombre.setdefault(normalizar(nombre), volcan_id)

    puntos_wgs84 = puntos.to_crs("EPSG:4326")
    features = []
    ids_usados = set()

    for _, fila in puntos_wgs84.iterrows():
        nombre = str(fila[campo_nombre]).strip()
        geometria = fila.geometry
        if not nombre:
            raise ValueError("El KMZ contiene un punto sin nombre.")
        if geometria is None or geometria.is_empty or geometria.geom_type != "Point":
            raise ValueError(f"{nombre!r} no tiene una geometría Point válida.")
        if not math.isfinite(geometria.x) or not math.isfinite(geometria.y):
            raise ValueError(f"{nombre!r} tiene coordenadas no válidas.")

        volcan_id = id_por_nombre.get(normalizar(nombre)) or crear_slug(nombre)
        if not volcan_id:
            raise ValueError(f"No se pudo generar un ID para {nombre!r}.")
        if volcan_id in ids_usados:
            origen_id = crear_slug(fila.get("id", ""))
            volcan_id = f"{volcan_id}_{origen_id or len(features) + 1}"
        ids_usados.add(volcan_id)

        features.append({
            "type": "Feature",
            "properties": {"id": volcan_id, "nombre": nombre},
            "geometry": {
                "type": "Point",
                "coordinates": [geometria.x, geometria.y],
            },
        })

    if not features:
        raise ValueError("El KMZ no contiene puntos para publicar.")

    return {"type": "FeatureCollection", "name": "volcanes", "features": features}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "scripts/volcanes_config.json")
    parser.add_argument("--kmz", type=Path, help="KMZ alternativo; por defecto usa la configuración")
    parser.add_argument("--salida", type=Path, default=ROOT / "data/volcanes.geojson")
    args = parser.parse_args()

    config = leer_json(args.config, None)
    if config is None:
        parser.error(f"No existe el archivo de configuración: {args.config}")
    kmz = args.kmz or Path(config.get("puntos_kmz", ""))
    if not kmz.is_file():
        parser.error(f"No existe el KMZ: {kmz}")

    catalogo = leer_json(ROOT / "data/catalog.json", {"volcanes": []})
    puntos_actuales = leer_json(args.salida, {"features": []})
    puntos = gpd.read_file(kmz)
    geojson = crear_geojson(puntos, catalogo, puntos_actuales, config)

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = args.salida.with_suffix(args.salida.suffix + ".tmp")
    temporal.write_text(json.dumps(geojson, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporal.replace(args.salida)

    print(f"{len(geojson['features'])} puntos sincronizados en {args.salida}.")


if __name__ == "__main__":
    main()