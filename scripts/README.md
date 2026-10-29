# Generación por lotes del Geoportal

`automatizar_volcanes.py` reemplaza la edición manual de volcán, fecha y órbita
para generar los productos web. Los scripts anteriores siguen disponibles.

## Entorno

Usa el entorno `mintpy` que ya está instalado en este equipo:

```bash
conda activate mintpy
```

El nuevo script requiere `numpy`, `h5py`, `geopandas`, `rasterio` y `shapely`.
Lee directamente `geo/geo_timeseries_ERA5_ramp_demErr.h5`, sin ejecutar
`save_gdal.py` ni `info.py`. No hace procesamiento ISCE/MintPy: los HDF5
geocodificados y corregidos deben existir antes de ejecutar el lote.

## Configuración

`scripts/volcanes_config.json` contiene las rutas a `asc463`, `desc137`, el
shapefile de radios de influencia, los puntos oficiales de las bocas volcánicas
y los edificios/flujo históricos. Define 19 sitios:
7 ascendentes y 12 descendentes. Las carpetas `ifgm` y `stamps_psi` no son sitios.

Cada sitio tiene un ID, nombre de carpeta fuente, nombre de máscara, carpeta de
salida y geometría. Los nombres se comparan sin espacios, acentos ni diferencias
entre mayúsculas y minúsculas. Las equivalencias no obvias están explícitas:
`Aburrido` → `El Aburrido`, `AltoMulatos` → `Alto de Mulatos`, `MellitoAlto` →
`Melito Alto`, `Las_Mercedes` → `Finca Las Mercedes`, `LasPlatasI` → `Las Platas`
y `SantaRosaPalmares` → `Santa Rosa de los Palmares`.

Los marcadores del mapa se toman de `puntos` usando el campo `campo_punto`
(`name` en la capa oficial), no del interior del radio de influencia. Si un
sitio no tiene un punto fuente coincidente, se avisa y se conserva como fallback
un punto representativo de su área. `nombre_punto` permite declarar alias de la
capa; por ejemplo, Melito Alto se enlaza con `Mellito AltoT`.

Revisa esas correspondencias al añadir o renombrar sitios. Si se añade otra
órbita para el mismo volcán, asigna otro ID y carpeta de salida: las series LOS
de geometrías distintas no deben combinarse. Para omitir flujos históricos,
pon `"flujos": null` en el archivo de configuración.

## Puntos del KMZ

El mapa general y el contador de edificios usan `data/volcanes.geojson`. Para
actualizar ambos después de agregar o mover puntos, sincroniza el KMZ indicado
en `puntos_kmz` dentro de `volcanes_config.json`:

```bash
python scripts/sincronizar_puntos_kmz.py
```

El sincronizador conserva los IDs de los volcanes que ya tienen boletín y asigna
IDs basados en el nombre a los demás. Los puntos nuevos aparecen en el mapa sin
necesitar datos InSAR; al hacer clic, solo los volcanes presentes en el catálogo
abren un boletín. Vuelve a publicar el portal para reflejar los cambios.

## Ejecución desde la carpeta Geoportal

Validar los archivos y las fechas, y mostrar los retiros previstos, sin escribir:

```bash
python scripts/automatizar_volcanes.py --simular
```

Generar un GeoTIFF de la última fecha de **cada** volcán y su serie temporal
completa, e integrarlos en `data/catalog.json` y `data/volcanes.geojson`:

```bash
python scripts/automatizar_volcanes.py
```

Probar primero en otra carpeta, conservando los productos del portal:

```bash
python scripts/automatizar_volcanes.py --salida /tmp/geoportal-prueba
```

Generar todos los GeoTIFF de todas las fechas, además de las series:

```bash
python scripts/automatizar_volcanes.py --fecha todas
```

Seleccionar una órbita, un volcán o una fecha:

```bash
python scripts/automatizar_volcanes.py --orbita asc463
python scripts/automatizar_volcanes.py --volcan el_aburrido --volcan las_changas
python scripts/automatizar_volcanes.py --volcan las_changas --fecha 20260911
```

`--fecha` controla los mapas; la serie siempre incluye todas las fechas del HDF5.
Una fecha no disponible se registra como error para ese sitio; se continúa con
los demás y el comando termina con código 1. No se sustituye por otra fecha.

## Productos y actualización

Por cada sitio se generan:

- `data/rasters/<carpeta>/<AAAAMMDD>.tif`: desplazamiento LOS en **metros**, float32,
  compresión DEFLATE, CRS del HDF5 y NaN fuera de la máscara.
- `data/estadisticas/<carpeta>/<AAAAMMDD>.json`: valores en **centímetros**,
  píxeles válidos y clases compatibles con la leyenda actual.
- `data/series/<carpeta>.json`: promedio, mínimo y máximo en cm por fecha.
- `data/areas/<carpeta>.geojson`, `data/metadata/<carpeta>.json` y, cuando existen
  flujos coincidentes, `data/flujos/<carpeta>.geojson`.
- Catálogo y puntos del mapa: actualiza las entradas sin duplicarlas, conserva
  las fechas anteriores y retira los sitios seleccionados cuya carpeta ya no existe.
- `data/reporte_generacion.json`: generación, retiros y errores de la última ejecución.

Las fechas se leen del dataset `date`. La grilla usa X/Y_FIRST y X/Y_STEP con
la misma transformación de `save_gdal.py`. Se conserva la referencia temporal
del HDF5; no se aplica otra resta ni se mezclan órbitas. Los píxeles se seleccionan
por su centro, igual que el recorte actual. No se añade un filtro de coherencia:
los datos de origen deben tener las correcciones y filtros científicos deseados.
Los ceros son datos válidos, incluyendo la fecha de referencia.

Volver a ejecutar regenera los productos seleccionados y la serie completa:
esto incorpora fechas nuevas y correcciones de fechas antiguas. No modifica los
HDF5. Para los sitios que siguen presentes, no elimina observaciones históricas
del catálogo. Si el HDF5 elimina una
fecha antigua, revisa manualmente esa observación conservada en el catálogo.
Los productos de cada sitio se preparan en una carpeta temporal antes de copiarse;
no ejecutes dos lotes simultáneamente sobre la misma carpeta de salida.

No genera GeoPackage ni CSV de puntos; para esos productos de análisis siguen
estando los scripts originales. Tampoco publica en GitHub. Después de revisar
los resultados, usa el flujo habitual de commit y push para actualizar Pages.

## Carpetas de volcanes eliminadas

Al ejecutar el lote, si ya no existe la carpeta de origen de un volcán configurado
(por ejemplo, `asc463/Cacahual`), se retira su ID de `data/catalog.json` y de
`data/volcanes.geojson`. Así deja de aparecer en el mapa y en el catálogo del portal.
Los GeoTIFF, series, estadísticas y demás archivos generados se conservan como
respaldo. El retiro se registra como `retirado`; si no figuraba en los índices,
se registra como `ausente`. Si vuelve a crearse la carpeta con datos válidos,
la siguiente ejecución vuelve a incorporar el volcán.

La comprobación usa las correspondencias de `volcanes_config.json`: mantén la
entrada del volcán en esa configuración hasta ejecutar el retiro. Quitar sólo
la entrada de la configuración no retira un volcán ya publicado.

Si la carpeta del volcán existe pero falta `geo` o el HDF5, se conserva el volcán
y se reporta un error. También se conserva si el disco, la carpeta de órbita o
un enlace simbólico están inaccesibles. Una órbita accesible y vacía sí permite
retirar todos sus volcanes configurados.

`--simular` muestra `por_retirar` sin modificar archivos. Los filtros `--orbita`
y `--volcan` restringen tanto la generación como los retiros. Estos cambios se
aplican al ejecutar el script; para reflejarlos en GitHub Pages, publica después
los JSON actualizados.

## Uso recurrente

Después de actualizar los HDF5 de MintPy, ejecuta el mismo comando por lotes.
Desde la raíz del repositorio, con el entorno que contiene las dependencias:

```bash
python scripts/automatizar_volcanes.py
```

En un clon nuevo, copia `scripts/volcanes_config.example.json` a
`scripts/volcanes_config.json` y actualiza sus rutas locales antes de ejecutar.
La configuración local no se versiona. Este comando no instala una tarea
programada ni realiza publicación automática.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Comprueban unidades, fecha de referencia, recorte, conservación de sitios y
fechas al repetir la integración, rechazo de fechas o máscaras incompatibles,
retiros, simulación, filtros y conservación ante orígenes inaccesibles.
