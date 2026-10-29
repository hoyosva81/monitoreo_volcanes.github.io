"""Servidor local para editar la ficha del boletín de cada volcán.

Uso, desde la raíz del repositorio:
    py scripts/editor_boletin.py
    py scripts/editor_boletin.py --puerto 8080

Sirve el sitio en http://127.0.0.1:8000 y habilita el botón «Editar boletín» de la
vista del volcán. Los cambios se guardan en `data/boletin.json` (con copia
`boletin.json.bak`) y las imágenes en `assets/fotos/<id>/` y `assets/mapas/<id>/`,
comprimidas a WebP. Después se publican con el commit y push habituales.

Solo escucha en 127.0.0.1 y rechaza peticiones de escritura que no vengan de la propia
página (Host/Origin locales y cabecera X-Boletin-Editor). No usa dependencias salvo
Pillow, que ya requieren los demás scripts.
"""

import argparse
import json
import re
import shutil
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import boletin_comun as bc

HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}
LIMITE_JSON = 5 * 1024 * 1024
LIMITE_IMAGEN = 15 * 1024 * 1024
ROLES_MAPA = {
    "mapa_ubicacion": "ubicacion",
    "mapa_propagacion": "propagacion",
    "mapa_amenaza": "amenaza",
    "morfometria": "morfometria",
}
ROLES_FOTO = {"foto", "galeria"}
PATRON_ARCHIVO = re.compile(r"^\./assets/(fotos|mapas)/([a-z0-9_]+)/[A-Za-z0-9_.-]+\.webp$")


def host_sin_puerto(valor):
    valor = (valor or "").strip()
    if valor.startswith("["):
        return valor[1:].split("]")[0]
    return valor.rsplit(":", 1)[0] if ":" in valor else valor


class ErrorHttp(Exception):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def crear_manejador(raiz):
    raiz = Path(raiz).resolve()

    class Manejador(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(raiz), **kwargs)

        # ------------------------------------------------------------
        # Utilidades
        # ------------------------------------------------------------

        def log_message(self, formato, *args):
            if self.path.startswith("/api/") or "--verboso" in sys.argv:
                sys.stderr.write("%s - %s\n" % (self.address_string(), formato % args))

        def copyfile(self, origen, destino):
            # En Windows shutil usa bloques de 1 MB, y con respuestas grandes
            # (municipios, imágenes) la conexión local a veces se queda a medias.
            shutil.copyfileobj(origen, destino, 64 * 1024)

        def responder_json(self, datos, codigo=200):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def ids_validos(self):
            ruta = raiz / "data" / "volcanes.geojson"
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            return {f["properties"]["id"] for f in datos["features"]}

        def verificar_origen(self):
            """Evita escrituras desde otras páginas web o por DNS rebinding."""
            if host_sin_puerto(self.headers.get("Host")) not in HOSTS_LOCALES:
                raise ErrorHttp(403, "Host no permitido.")
            origen = self.headers.get("Origin")
            if origen and (urlparse(origen).hostname or "") not in HOSTS_LOCALES:
                raise ErrorHttp(403, "Origen no permitido.")
            if self.headers.get("X-Boletin-Editor") != "1":
                raise ErrorHttp(403, "Falta la cabecera del editor.")

        def leer_cuerpo(self, limite):
            try:
                longitud = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise ErrorHttp(411, "Se requiere Content-Length.")
            if longitud <= 0:
                raise ErrorHttp(400, "Cuerpo vacío.")
            if longitud > limite:
                raise ErrorHttp(413, "El archivo supera el tamaño permitido.")
            self.cuerpo_leido = True
            return self.rfile.read(longitud)

        def descartar_cuerpo(self):
            """Lee el cuerpo no usado: si el servidor responde y cierra con datos
            pendientes, Windows reinicia la conexión y el cliente pierde el error."""
            try:
                restante = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return

            if restante <= 0 or restante > LIMITE_IMAGEN:
                return

            while restante > 0:
                bloque = self.rfile.read(min(restante, 64 * 1024))

                if not bloque:
                    break

                restante -= len(bloque)

        def despachar(self, funcion):
            self.cuerpo_leido = False

            try:
                self.verificar_origen()
                funcion(urlparse(self.path))
            except ErrorHttp as error:
                if not self.cuerpo_leido:
                    self.descartar_cuerpo()

                self.responder_json({"error": error.mensaje}, error.codigo)
            except Exception as error:  # pragma: no cover - respuesta de último recurso
                self.responder_json({"error": f"Error interno: {error}"}, 500)

        # ------------------------------------------------------------
        # Métodos HTTP
        # ------------------------------------------------------------

        def do_GET(self):
            if urlparse(self.path).path == "/api/ping":
                self.responder_json({"editor": True})
                return
            super().do_GET()

        def do_PUT(self):
            self.despachar(self.guardar_boletin)

        def do_POST(self):
            self.despachar(self.subir_imagen)

        def do_DELETE(self):
            self.despachar(self.borrar_imagen)

        # ------------------------------------------------------------
        # Acciones
        # ------------------------------------------------------------

        def guardar_boletin(self, url):
            if url.path != "/api/boletin":
                raise ErrorHttp(404, "Ruta desconocida.")
            try:
                datos = json.loads(self.leer_cuerpo(LIMITE_JSON).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ErrorHttp(400, "El cuerpo no es un JSON válido.")
            if (
                not isinstance(datos, dict)
                or not isinstance(datos.get("general"), dict)
                or not isinstance(datos.get("volcanes"), dict)
            ):
                raise ErrorHttp(400, "Se esperaba un objeto con «general» y «volcanes».")
            desconocidos = sorted(set(datos["volcanes"]) - self.ids_validos())
            if desconocidos:
                raise ErrorHttp(400, f"Volcanes desconocidos: {', '.join(desconocidos)}")
            for id_volcan, ficha in datos["volcanes"].items():
                if not isinstance(ficha, dict):
                    raise ErrorHttp(400, f"La ficha de {id_volcan} debe ser un objeto.")

            destino = raiz / "data" / "boletin.json"
            if destino.exists():
                shutil.copyfile(destino, destino.with_name(destino.name + ".bak"))
            bc.guardar_json(destino, datos)
            self.responder_json({"guardado": True})

        def subir_imagen(self, url):
            if url.path != "/api/imagen":
                raise ErrorHttp(404, "Ruta desconocida.")
            consulta = parse_qs(url.query)
            id_volcan = (consulta.get("volcan") or [""])[0]
            rol = (consulta.get("rol") or [""])[0]
            if id_volcan not in self.ids_validos():
                raise ErrorHttp(400, "Volcán desconocido.")
            if rol not in ROLES_MAPA and rol not in ROLES_FOTO:
                raise ErrorHttp(400, "Rol de imagen no válido.")

            cuerpo = self.leer_cuerpo(LIMITE_IMAGEN)
            # Cada subida usa un nombre nuevo: el navegador nunca muestra una versión en caché.
            marca = time.strftime("%Y%m%d%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
            if rol in ROLES_MAPA:
                archivo = raiz / "assets" / "mapas" / id_volcan / f"{ROLES_MAPA[rol]}-{marca}.webp"
            else:
                prefijo = "principal" if rol == "foto" else "galeria"
                archivo = raiz / "assets" / "fotos" / id_volcan / f"{prefijo}-{marca}.webp"
            try:
                bc.guardar_imagen(cuerpo, archivo)
            except Exception:
                raise ErrorHttp(400, "El archivo no es una imagen válida (JPG, PNG o WebP).")
            ruta = "./" + archivo.relative_to(raiz).as_posix()
            self.responder_json({"archivo": ruta})

        def borrar_imagen(self, url):
            if url.path != "/api/imagen":
                raise ErrorHttp(404, "Ruta desconocida.")
            ruta = (parse_qs(url.query).get("archivo") or [""])[0]
            if not PATRON_ARCHIVO.match(ruta):
                raise ErrorHttp(400, "Ruta de imagen no permitida.")
            archivo = (raiz / ruta).resolve()
            if raiz / "assets" not in archivo.parents:
                raise ErrorHttp(400, "Ruta de imagen no permitida.")
            if archivo.exists():
                archivo.unlink()
            self.responder_json({"borrado": True})

    return Manejador


class Servidor(ThreadingHTTPServer):
    # La cola por defecto (5 conexiones) hace que en Windows la página, que pide
    # decenas de archivos a la vez, sufra esperas y conexiones reiniciadas.
    request_queue_size = 128


def crear_servidor(raiz, puerto=8000):
    return Servidor(("127.0.0.1", puerto), crear_manejador(raiz))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--puerto", type=int, default=8000, help="Puerto local (por defecto 8000)")
    args = parser.parse_args(argv)

    servidor = crear_servidor(bc.RAIZ, args.puerto)
    # Se anuncia 127.0.0.1 porque «localhost» se resuelve primero a IPv6 (::1), donde
    # este servidor no escucha, y cada conexión espera a fallar antes de usar IPv4.
    print(f"Editor del boletín en http://127.0.0.1:{args.puerto}/  (Ctrl+C para salir)")
    print("Los cambios se guardan en data/boletin.json y assets/. Publica con commit y push.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEditor detenido.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
