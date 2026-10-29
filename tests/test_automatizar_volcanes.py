"""Pruebas con HDF5 sintético: unidades, recorte y conservación del catálogo."""
import json
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import geopandas as gpd
import h5py
import numpy as np
import rasterio
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from automatizar_volcanes import carpeta_origen, integrar, informacion, main, procesar, seleccionar_area


class ExportacionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.h5 = self.root / 'timeseries.h5'
        with h5py.File(self.h5, 'w') as f:
            f.create_dataset('date', data=np.array(['20260101', '20260201'], dtype='S8'))
            f.create_dataset('timeseries', data=np.array([np.zeros((3, 4)),
                [[.01, .02, .03, .04], [.05, .06, np.nan, .08], [.09, .10, .11, .12]]], dtype='float32'))
            f.attrs.update(UNIT='m', X_FIRST=0, X_STEP=1, Y_FIRST=3, Y_STEP=-1, REF_DATE='20260101', EPSG=4326)
        self.area = gpd.GeoDataFrame({'nombre': ['Sitio']}, geometry=[box(0, 1, 2, 3)], crs=4326)
        self.site = dict(id='sitio', nombre='Sitio', carpeta_salida='Sitio', geometria='Ascendente 463')

    def test_exportacion_metros_serie_centimetros_y_fecha_referencia(self):
        entry, feature, count = procesar(self.site, self.h5, self.area, None, 'ultima', self.root / 'stage')
        self.assertEqual(count, 2)
        self.assertEqual(len(entry['fechas']), 1)
        series = json.loads((self.root / 'stage/series/Sitio.json').read_text())['serie']
        self.assertEqual(series[0]['promedio_cm'], 0)
        self.assertAlmostEqual(series[1]['promedio_cm'], 3.5, places=5)
        with rasterio.open(self.root / 'stage/rasters/Sitio/20260201.tif') as r:
            self.assertEqual(r.shape, (2, 2))
            self.assertAlmostEqual(float(r.read(1)[0, 0]), .01, places=6)
            self.assertTrue(np.isnan(r.nodata))
        self.assertEqual(feature['properties']['id'], 'sitio')

    def test_catalogo_conserva_sitios_y_fechas_sin_duplicacion(self):
        output = self.root / 'output'
        output.mkdir()
        (output / 'catalog.json').write_text(json.dumps(dict(version=1, volcanes=[
            dict(id='otro', nombre='Otro', fechas=[]),
            dict(id='sitio', nombre='Sitio', fechas=[dict(fecha='20251201')])
        ])))
        (output / 'volcanes.geojson').write_text(json.dumps(dict(type='FeatureCollection', features=[
            dict(type='Feature', properties=dict(id='otro'), geometry=None)
        ])))
        stage = self.root / 'stage'
        entry, feature, _ = procesar(self.site, self.h5, self.area, None, 'todas', stage)
        integrar(output, stage, entry, feature)
        integrar(output, stage, entry, feature)
        catalog = json.loads((output / 'catalog.json').read_text())
        self.assertEqual(len(catalog['volcanes']), 2)
        self.assertEqual(next(v for v in catalog['volcanes'] if v['id']=='sitio')['fechas'],
                         [entry['fechas'][1], entry['fechas'][0], dict(fecha='20251201')])
        self.assertEqual(len(json.loads((output/'volcanes.geojson').read_text())['features']), 2)

    def test_rechaza_fecha_ausente_y_mascara_sin_solape(self):
        with self.assertRaisesRegex(ValueError, 'no disponible'):
            procesar(self.site, self.h5, self.area, None, '20260301', self.root / 'stage')
        outside = gpd.GeoDataFrame(geometry=[box(40, 40, 41, 41)], crs=4326)
        with self.assertRaises(rasterio.errors.WindowError):
            procesar(self.site, self.h5, outside, None, 'ultima', self.root / 'stage')

    def test_marcador_usa_punto_oficial_y_reproyecta_a_wgs84(self):
        site = {**self.site, 'nombre_punto': 'Sitio Boca'}
        points = gpd.GeoDataFrame(
            {'name': ['Sitio Boca']},
            geometry=[Point(5000000, 2000000)],
            crs=9377
        )
        expected = points.to_crs(4326).geometry.iloc[0]
        _, feature, _ = procesar(
            site, self.h5, self.area, None, 'ultima', self.root / 'stage', points
        )
        longitude, latitude = feature['geometry']['coordinates']
        self.assertAlmostEqual(longitude, expected.x, places=8)
        self.assertAlmostEqual(latitude, expected.y, places=8)

    def test_validacion_unidad_y_nombres(self):
        self.area['nombre'] = ['Sítio de Lodo']
        self.assertEqual(len(seleccionar_area(self.area, 'nombre', 'sitio_de_lodo')), 1)
        with h5py.File(self.h5, 'a') as f:
            f.attrs['UNIT'] = 'cm'
        with self.assertRaisesRegex(ValueError, 'metros'):
            informacion(self.h5)


class RetiroTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'saocom'
        self.orbit = self.base / 'asc463'
        self.orbit.mkdir(parents=True)
        self.output = self.root / 'data'
        self.output.mkdir()
        self.sites = [dict(id=name, nombre=name, carpeta=name, orbita='asc463',
                           carpeta_salida=name, nombre_mascara='Sitio', geometria='Ascendente 463')
                      for name in ('eliminado', 'activo')]
        (self.orbit / 'activo').mkdir()
        catalog = dict(version=1, volcanes=[dict(id=name, fechas=[])
                                           for name in ('eliminado', 'activo', 'otro')])
        points = dict(type='FeatureCollection', features=[dict(type='Feature', properties=dict(id=name),
                                                              geometry=None)
                                                        for name in ('eliminado', 'activo', 'otro')])
        (self.output / 'catalog.json').write_text(json.dumps(catalog))
        (self.output / 'volcanes.geojson').write_text(json.dumps(points))
        (self.output / 'series').mkdir()
        self.backup = self.output / 'series/eliminado.json'
        self.backup.write_text('{"serie": []}')
        config = dict(base_saocom=str(self.base), archivo_h5='timeseries.h5', mascara='mascara.shp',
                      campo_mascara='nombre', flujos=None, volcanes=self.sites)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(config))
        self.area = gpd.GeoDataFrame({'nombre': ['Sitio']}, geometry=[box(0, 1, 2, 3)], crs=4326)

    def run_main(self, *arguments):
        argv = ['automatizar_volcanes.py', '--config', str(self.config), '--salida', str(self.output),
                *arguments]
        with patch.object(sys, 'argv', argv), patch('automatizar_volcanes.gpd.read_file', return_value=self.area), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main()

    def ids(self, file):
        value = json.loads((self.output / file).read_text())
        return ([v['id'] for v in value['volcanes']] if file == 'catalog.json'
                else [v['properties']['id'] for v in value['features']])

    def test_retira_carpeta_eliminada_de_ambos_indices_y_conserva_productos(self):
        self.assertEqual(self.run_main('--volcan', 'eliminado'), 0)
        for file in ('catalog.json', 'volcanes.geojson'):
            self.assertEqual(self.ids(file), ['activo', 'otro'])
        self.assertEqual(self.backup.read_text(), '{"serie": []}')
        report = json.loads((self.output / 'reporte_generacion.json').read_text())
        self.assertEqual(report['resultados'][0]['estado'], 'retirado')
        self.assertEqual(self.run_main('--volcan', 'eliminado'), 0)
        self.assertEqual(self.ids('catalog.json'), ['activo', 'otro'])

    def test_simulacion_no_escribe_y_filtro_no_retira_otros_volcanes(self):
        previous = {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        self.assertEqual(self.run_main('--simular', '--volcan', 'eliminado'), 0)
        self.assertEqual(previous, {p: p.read_bytes() for p in self.output.rglob('*') if p.is_file()})
        self.assertEqual(self.run_main('--volcan', 'activo'), 1)  # No tiene HDF5.
        self.assertEqual(self.ids('catalog.json'), ['eliminado', 'activo', 'otro'])

    def test_lote_retira_eliminado_pero_conserva_carpeta_activa_sin_hdf5(self):
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.ids('catalog.json'), ['activo', 'otro'])
        self.assertEqual(self.ids('volcanes.geojson'), ['activo', 'otro'])
        report = json.loads((self.output / 'reporte_generacion.json').read_text())
        self.assertEqual([v['estado'] for v in report['resultados']], ['retirado', 'error'])

    def test_orbita_ausente_o_inaccesible_no_provoca_retiro(self):
        self.orbit.rename(self.base / 'asc463-respaldo')
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.ids('catalog.json'), ['eliminado', 'activo', 'otro'])
        (self.base / 'asc463-respaldo').rename(self.orbit)
        with patch.object(Path, 'iterdir', side_effect=PermissionError('Sin acceso')):
            self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.ids('volcanes.geojson'), ['eliminado', 'activo', 'otro'])

    def test_enlace_roto_no_equivale_a_eliminacion(self):
        (self.orbit / 'eliminado').symlink_to(self.root / 'disco-ausente', target_is_directory=True)
        with self.assertRaises(FileNotFoundError):
            carpeta_origen(self.base, self.sites[0])
        self.assertEqual(self.run_main('--volcan', 'eliminado'), 1)
        self.assertEqual(self.ids('catalog.json'), ['eliminado', 'activo', 'otro'])


if __name__ == '__main__':
    unittest.main()
