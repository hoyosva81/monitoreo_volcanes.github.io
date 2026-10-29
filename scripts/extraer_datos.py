import geopandas as gpd

gpkg = (
    "/run/media/spinedas1/Seagate/Diapiros/"
    "Desarrollos/InSAR/SBAS/Geoportal/data/rasters/"
    "Las Changas/20260911/"
    "Las Changas_20260911.gpkg"
)

salida = (
    "/run/media/spinedas1/Seagate/Diapiros/"
    "Desarrollos/InSAR/SBAS/Geoportal/"
    "data/flujos/Las_Changas.geojson"
)

flujos = gpd.read_file(
    gpkg,
    layer="flujos_historicos"
)

flujos = flujos.to_crs("EPSG:4326")

flujos.to_file(
    salida,
    driver="GeoJSON"
)

print("Generado:", salida)