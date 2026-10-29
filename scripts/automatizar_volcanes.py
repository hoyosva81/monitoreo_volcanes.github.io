"""Exportación por lotes de MintPy al formato del Geoportal (sin modificar HDF5)."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unicodedata
import warnings

import geopandas as gpd
import h5py
import numpy as np
import rasterio
from rasterio.features import geometry_mask, geometry_window
from rasterio.io import MemoryFile
from rasterio.transform import Affine

ROOT = Path(__file__).resolve().parents[1]
LIMITES = [-6, -4, -2, -1, 1, 2, 4, 6]
CATEGORIAS = ['< -6 cm', '-6 a -4 cm', '-4 a -2 cm', '-2 a -1 cm',
              '-1 a +1 cm', '+1 a +2 cm', '+2 a +4 cm', '+4 a +6 cm', '>= +6 cm']


def normalizar(value):
    text = unicodedata.normalize('NFKD', str(value)).casefold()
    return ''.join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def leer_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def guardar_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def seleccionar_area(frame, field, name):
    if field not in frame or frame.crs is None:
        raise ValueError(f'La capa debe tener CRS y campo {field!r}.')
    area = frame[frame[field].map(normalizar) == normalizar(name)].copy()
    area = area[area.geometry.notna() & ~area.geometry.is_empty].copy()
    if area.empty:
        raise ValueError(f'No hay geometría para {name!r} en {field!r}.')
    area.geometry = area.geometry.make_valid()
    return area


def seleccionar_punto(frame, field, name):
    if frame is None:
        return None
    if field not in frame or frame.crs is None:
        raise ValueError(f'La capa de puntos debe tener CRS y campo {field!r}.')
    points = frame[frame[field].map(normalizar) == normalizar(name)].copy()
    points = points[points.geometry.notna() & ~points.geometry.is_empty].copy()
    if points.empty:
        return None
    if len(points) != 1 or points.geometry.iloc[0].geom_type != 'Point':
        raise ValueError(f'Se esperaba un único punto para {name!r} en {field!r}.')
    return points.to_crs(4326).geometry.iloc[0]


def informacion(path):
    with h5py.File(path, 'r') as source:
        attrs = source.attrs
        if str(attrs.get('UNIT', '')) != 'm':
            raise ValueError(f'{path}: se esperaba desplazamiento en metros (UNIT=m).')
        transform = Affine(float(attrs['X_STEP']), 0, float(attrs['X_FIRST']),
                           0, float(attrs['Y_STEP']), float(attrs['Y_FIRST']))
        if transform.a <= 0 or transform.e >= 0:
            raise ValueError(f'{path}: se esperaba una grilla geocodificada orientada al norte.')
        if 'UTM_ZONE' in attrs and 'EPSG' not in attrs:
            raise ValueError(f'{path}: indique EPSG en el HDF5 para una grilla UTM.')
        crs = rasterio.crs.CRS.from_epsg(int(attrs.get('EPSG', 4326)))
        dates = [v.decode() if isinstance(v, bytes) else str(v) for v in source['date'][:]]
        for date in dates:
            datetime.strptime(date, '%Y%m%d')
        shape = source['timeseries'].shape
        if len(shape) != 3 or shape[0] != len(dates) or len(set(dates)) != len(dates):
            raise ValueError(f'{path}: dimensiones/fechas inconsistentes.')
        return dates, shape, transform, crs, str(attrs.get('REF_DATE', ''))


def estadisticas(values, date):
    cm = values.astype('float64') * 100
    classes = np.digitize(cm, LIMITES)
    return dict(fecha=date, unidad='cm', pixeles_validos=int(cm.size),
                minimo_cm=float(cm.min()), maximo_cm=float(cm.max()),
                promedio_cm=float(cm.mean()), mediana_cm=float(np.median(cm)),
                desviacion_cm=float(cm.std(ddof=1)) if cm.size > 1 else 0.0,
                categorias=[dict(nombre=name, pixeles=int((classes == i).sum()))
                            for i, name in enumerate(CATEGORIAS)])


def procesar(site, path, area, flows, requested, stage, points=None, point_field='name'):
    dates, shape, transform, crs, reference = informacion(path)
    chosen = sorted(dates) if requested == 'todas' else [max(dates) if requested == 'ultima' else requested]
    if any(date not in dates for date in chosen):
        raise ValueError(f'{site["nombre"]}: fecha {requested} no disponible.')
    geometries = list(area.to_crs(crs).geometry)
    # La transformación coincide con save_gdal.py: X/Y_FIRST es la esquina de la grilla.
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', height=shape[1], width=shape[2], count=1,
                         dtype='float32', crs=crs, transform=transform) as grid:
            window = geometry_window(grid, geometries)
            cropped_transform = grid.window_transform(window)
    rows, cols = window.toslices()
    inside = geometry_mask(geometries, (int(window.height), int(window.width)),
                           cropped_transform, invert=True, all_touched=False)
    folder = site['carpeta_salida']
    observations, series = [], []
    with h5py.File(path, 'r') as source:
        for index, date in sorted(enumerate(dates), key=lambda item: item[1]):
            data = source['timeseries'][index, rows, cols].astype('float32')
            valid = inside & np.isfinite(data)
            if not valid.any():
                raise ValueError(f'{site["nombre"]}: sin píxeles válidos para {date}.')
            stats = estadisticas(data[valid], date)
            series.append({k: stats[k] for k in ('fecha', 'promedio_cm', 'minimo_cm', 'maximo_cm')})
            if date not in chosen:
                continue
            raster_relative = Path('rasters') / folder / f'{date}.tif'
            target = stage / raster_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data[~valid] = np.nan
            with rasterio.open(target, 'w', driver='GTiff', height=data.shape[0],
                               width=data.shape[1], count=1, dtype='float32', crs=crs,
                               transform=cropped_transform, nodata=np.nan, compress='deflate') as dst:
                dst.write(data, 1)
                dst.update_tags(unidad='m', fecha=date, referencia=reference)
            stats_relative = Path('estadisticas') / folder / f'{date}.json'
            guardar_json(stage / stats_relative, stats)
            observations.append(dict(fecha=date, raster='./data/' + raster_relative.as_posix(),
                                     estadisticas='./data/' + stats_relative.as_posix()))
    area_web = area.to_crs(4326)
    guardar_json(stage / 'areas' / f'{folder}.geojson', json.loads(area_web.to_json()))
    guardar_json(stage / 'series' / f'{folder}.json', dict(id=site['id'], nombre=site['nombre'],
                 unidad='cm', variable='desplazamiento_LOS_promedio', serie=series))
    metadata = dict(id=site['id'], nombre=site['nombre'], sensor='SAOCOM', metodo='InSAR',
                    procesamiento='ISCE + MintPy', geometria=site['geometria'],
                    unidad_raster='m', unidad_visualizacion='cm', crs=crs.to_string(),
                    fecha_referencia=reference,
                    nota='Desplazamiento acumulado LOS respecto a la fecha de referencia de MintPy.')
    guardar_json(stage / 'metadata' / f'{folder}.json', metadata)
    entry = dict(id=site['id'], nombre=site['nombre'], fechas=observations)
    for key, suffix in [('metadata', 'json'), ('area', 'geojson'), ('serie', 'json')]:
        directory = {'metadata': 'metadata', 'area': 'areas', 'serie': 'series'}[key]
        entry[key] = f'./data/{directory}/{folder}.{suffix}'
    if flows is not None:
        matched = flows[flows['Nombre'].map(normalizar) == normalizar(site['nombre'])].copy()
        matched = matched[matched.geometry.notna() & ~matched.geometry.is_empty].copy()
        if not matched.empty:
            matched.geometry = matched.geometry.make_valid()
            guardar_json(stage / 'flujos' / f'{folder}.geojson', json.loads(matched.to_crs(4326).to_json()))
            entry['flujos'] = f'./data/flujos/{folder}.geojson'
    point = seleccionar_punto(
        points,
        point_field,
        site.get('nombre_punto', site['nombre'])
    )
    if point is None:
        if points is not None:
            warnings.warn(
                f'{site["nombre"]}: no hay punto oficial; se usará un punto del área de influencia.',
                stacklevel=2
            )
        point = area_web.geometry.union_all().representative_point()
    feature = dict(type='Feature', properties=dict(id=site['id'], nombre=site['nombre']),
                   geometry=dict(type='Point', coordinates=[point.x, point.y]))
    return entry, feature, len(series)


def integrar(output, stage, entry, feature):
    catalog = leer_json(output / 'catalog.json', dict(version=1, volcanes=[]))
    points = leer_json(output / 'volcanes.geojson', dict(type='FeatureCollection', features=[]))
    existing = next((v for v in catalog['volcanes'] if v['id'] == entry['id']), {})
    dates = {v['fecha']: v for v in existing.get('fechas', [])}
    dates.update({v['fecha']: v for v in entry['fechas']})
    merged = {**existing, **entry, 'fechas': sorted(dates.values(), key=lambda v: v['fecha'], reverse=True)}
    catalog['volcanes'] = [v for v in catalog['volcanes'] if v['id'] != entry['id']] + [merged]
    points['features'] = [v for v in points['features'] if v.get('properties', {}).get('id') != entry['id']] + [feature]
    # Primero productos; los índices sólo se actualizan cuando todos se copiaron.
    for source in stage.rglob('*'):
        if source.is_file():
            destination = output / source.relative_to(stage)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + '.tmp')
            shutil.copy2(source, temporary)
            temporary.replace(destination)
    guardar_json(output / 'catalog.json', catalog)
    guardar_json(output / 'volcanes.geojson', points)


def carpeta_origen(base, site):
    """Devuelve None sólo si falta el sitio dentro de una órbita accesible."""
    orbit = base / site['orbita']
    for directory in (base, orbit):
        if not stat.S_ISDIR(directory.stat().st_mode):
            raise ValueError(f'La ruta de origen no es una carpeta: {directory}')
    # Un disco desmontado o una órbita sin acceso no equivale a eliminar un sitio.
    list(orbit.iterdir())
    folder = orbit / site['carpeta']
    try:
        mode = folder.lstat().st_mode
    except FileNotFoundError:
        # Comprobar otra vez la órbita por si desapareció durante la consulta.
        if not stat.S_ISDIR(orbit.stat().st_mode):
            raise ValueError(f'La órbita dejó de estar disponible: {orbit}')
        list(orbit.iterdir())
        return None
    if stat.S_ISLNK(mode):
        mode = folder.stat().st_mode  # Un enlace roto se reporta como error.
    if not stat.S_ISDIR(mode):
        raise ValueError(f'El origen del volcán no es una carpeta: {folder}')
    list(folder.iterdir())
    return folder


def retirar_volcan(output, volcan_id, simular=False):
    """Retira el ID de los índices web; conserva los productos como respaldo."""
    catalog_path = output / 'catalog.json'
    points_path = output / 'volcanes.geojson'
    catalog = leer_json(catalog_path, dict(version=1, volcanes=[]))
    points = leer_json(points_path, dict(type='FeatureCollection', features=[]))
    remaining = [v for v in catalog['volcanes'] if v['id'] != volcan_id]
    features = [v for v in points['features'] if v.get('properties', {}).get('id') != volcan_id]
    catalog_changed = len(remaining) != len(catalog['volcanes'])
    points_changed = len(features) != len(points['features'])
    if not simular:
        if catalog_changed:
            catalog['volcanes'] = remaining
            guardar_json(catalog_path, catalog)
        if points_changed:
            points['features'] = features
            guardar_json(points_path, points)
    return catalog_changed or points_changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'scripts/volcanes_config.json')
    parser.add_argument('--salida', type=Path, default=ROOT / 'data', help='Carpeta data de destino')
    parser.add_argument('--fecha', default='ultima', help='ultima, todas o AAAAMMDD (serie siempre completa)')
    parser.add_argument('--volcan', action='append', help='ID de volcán; repetible')
    parser.add_argument('--orbita', choices=['asc463', 'desc137'])
    parser.add_argument('--simular', action='store_true', help='Valida entradas y muestra el plan sin escribir')
    args = parser.parse_args()
    if args.fecha not in ('ultima', 'todas'):
        datetime.strptime(args.fecha, '%Y%m%d')
    config = leer_json(args.config, None)
    if config is None:
        parser.error(f'No existe {args.config}')
    sites = config['volcanes']
    if args.volcan:
        unknown = set(args.volcan) - {s['id'] for s in sites}
        if unknown:
            parser.error(f'IDs desconocidos: {sorted(unknown)}')
    sites = [s for s in sites if (not args.volcan or s['id'] in args.volcan)
             and (not args.orbita or s['orbita'] == args.orbita)]
    if not sites:
        parser.error('La selección no contiene volcanes.')
    if len({s['id'] for s in sites}) != len(sites) or len({s['carpeta_salida'] for s in sites}) != len(sites):
        parser.error('IDs o carpetas de salida duplicados; cada geometría debe tener un ID distinto.')
    masks = flows = volcano_points = None
    point_field = config.get('campo_punto', 'name')
    layers_loaded = False
    results = []
    for site in sites:
        try:
            folder = carpeta_origen(Path(config['base_saocom']), site)
            if folder is None:
                changed = retirar_volcan(args.salida, site['id'], simular=args.simular)
                status = ('por_retirar' if args.simular else 'retirado') if changed else 'ausente'
                print(f'{site["id"]}: {status}; carpeta de origen eliminada.', flush=True)
                results.append(dict(id=site['id'], estado=status, motivo='carpeta_origen_eliminada'))
                continue
            path = folder / 'geo' / config['archivo_h5']
            if not layers_loaded:
                masks = gpd.read_file(config['mascara'])
                flows = gpd.read_file(config['flujos']) if config.get('flujos') else None
                if flows is not None and (flows.crs is None or 'Nombre' not in flows):
                    raise ValueError('Los flujos deben tener CRS y campo Nombre.')
                volcano_points = gpd.read_file(config['puntos']) if config.get('puntos') else None
                if volcano_points is not None and (
                    volcano_points.crs is None or point_field not in volcano_points
                ):
                    raise ValueError(f'La capa de puntos debe tener CRS y campo {point_field!r}.')
                layers_loaded = True
            area = seleccionar_area(masks, config['campo_mascara'], site['nombre_mascara'])
            if args.simular and volcano_points is not None and seleccionar_punto(
                volcano_points,
                point_field,
                site.get('nombre_punto', site['nombre'])
            ) is None:
                warnings.warn(
                    f'{site["nombre"]}: no hay punto oficial; se usará un punto del área de influencia.',
                    stacklevel=2
                )
            dates, _, _, _, _ = informacion(path)
            print(f'{site["id"]}: {len(dates)} fechas, última {max(dates)}, {site["geometria"]}', flush=True)
            if args.fecha not in ('ultima', 'todas') and args.fecha not in dates:
                raise ValueError(f'Fecha {args.fecha} no disponible.')
            if not args.simular:
                with tempfile.TemporaryDirectory(prefix='geoportal-lote-') as temporary:
                    stage = Path(temporary)
                    entry, feature, count = procesar(
                        site, path, area, flows, args.fecha, stage,
                        volcano_points, point_field
                    )
                    integrar(args.salida, stage, entry, feature)
                print(f'  OK: {len(entry["fechas"])} GeoTIFF, {count} puntos temporales.', flush=True)
            results.append(dict(id=site['id'], estado='validado' if args.simular else 'generado'))
        except Exception as error:
            print(f'  ERROR: {error}', file=sys.stderr, flush=True)
            results.append(dict(id=site['id'], estado='error', error=str(error)))
    if not args.simular:
        guardar_json(args.salida / 'reporte_generacion.json', dict(fecha_ejecucion=datetime.now().astimezone().isoformat(),
                                                                resultados=results))
    errors = sum(v['estado'] == 'error' for v in results)
    removed = sum(v['estado'] in ('retirado', 'por_retirar') for v in results)
    print(f'Terminado: {len(results) - errors} correctos, {errors} errores; {removed} retiros'
          + (' previstos.' if args.simular else '.'))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
