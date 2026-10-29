// Editor local de la ficha del boletín.
//
// Solo se carga cuando la página se abre con scripts/editor_boletin.py (que
// responde en /api/ping). Los cambios se ven en la ficha mientras se escribe y se
// guardan en data/boletin.json; las imágenes se suben a assets/ ya comprimidas.

const ROLES_IMAGEN = [
    ["foto", "Foto del volcán"],
    ["mapa_ubicacion", "Mapa de ubicación"],
    ["mapa_propagacion", "Modelo de propagación"],
    ["mapa_amenaza", "Mapa de amenaza"],
    ["morfometria", "Figura de morfometría"]
];

const NIVELES = [
    ["", "Sin definir"],
    ["base", "Actividad base"],
    ["moderada", "Actividad moderada"],
    ["alta", "Actividad alta"]
];

const CABECERAS = {
    "X-Boletin-Editor": "1"
};

let contadorIds = 0;


// ============================================================
// UTILIDADES
// ============================================================

function elemento(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);

    if (clase) {
        nodo.className = clase;
    }

    if (texto !== undefined) {
        nodo.textContent = texto;
    }

    return nodo;
}

function leer(objeto, ruta) {
    return ruta.split(".").reduce(
        (actual, clave) => (actual === null || actual === undefined ? undefined : actual[clave]),
        objeto
    );
}

function escribir(objeto, ruta, valor) {
    const claves = ruta.split(".");
    let actual = objeto;

    for (const clave of claves.slice(0, -1)) {
        if (typeof actual[clave] !== "object" || actual[clave] === null) {
            actual[clave] = {};
        }

        actual = actual[clave];
    }

    actual[claves[claves.length - 1]] = valor;
}

function precisionDe(fecha) {
    const texto = String(fecha || "").trim();

    if (/^\d{4}$/.test(texto)) {
        return "anio";
    }

    if (/^\d{4}-\d{2}$/.test(texto)) {
        return "mes";
    }

    return "dia";
}

function hoyIso() {
    const ahora = new Date();
    const dos = n => String(n).padStart(2, "0");

    return `${ahora.getFullYear()}-${dos(ahora.getMonth() + 1)}-${dos(ahora.getDate())}`;
}

function archivosReferenciados(ficha) {
    const archivos = new Set();

    for (const imagen of Object.values(ficha.imagenes || {})) {
        if (imagen?.archivo) {
            archivos.add(imagen.archivo);
        }
    }

    for (const foto of ficha.galeria || []) {
        if (foto?.archivo) {
            archivos.add(foto.archivo);
        }
    }

    return archivos;
}


// ============================================================
// EDITOR
// ============================================================

export function iniciarEditor({ boletin, contexto, renderizar, botonEditar, panel }) {
    const { id, general } = contexto;

    if (!boletin.volcanes[id]) {
        boletin.volcanes[id] = contexto.ficha;
    }

    const ficha = boletin.volcanes[id];
    let original = null;
    let abierto = false;
    let cambios = false;
    let temporizador = null;
    let archivosNuevos = new Set();
    let archivosPorBorrar = new Set();

    botonEditar.hidden = false;
    botonEditar.addEventListener("click", abrir);

    window.addEventListener("beforeunload", evento => {
        if (abierto && cambios) {
            evento.preventDefault();
            evento.returnValue = "";
        }
    });

    // ----------------------------------------------------------
    // Estado
    // ----------------------------------------------------------

    function marcarCambio() {
        cambios = true;
        window.clearTimeout(temporizador);
        temporizador = window.setTimeout(renderizar, 120);
        mostrarEstado("Cambios sin guardar");
    }

    function mostrarEstado(texto, error = false) {
        const estado = panel.querySelector(".estado-guardado");

        if (estado) {
            estado.textContent = texto;
            estado.classList.toggle("error", error);
        }
    }

    function restaurar(destino, copia) {
        for (const clave of Object.keys(destino)) {
            delete destino[clave];
        }

        Object.assign(destino, structuredClone(copia));
    }

    // ----------------------------------------------------------
    // Campos
    // ----------------------------------------------------------

    function campo(etiqueta, ruta, objeto, tipo = "texto", opciones = {}) {
        const contenedor = elemento("div", "editor-campo");
        const identificador = `ed-${++contadorIds}`;
        const rotulo = elemento("label", "", etiqueta);
        rotulo.htmlFor = identificador;

        let control;

        if (tipo === "area") {
            control = document.createElement("textarea");
        } else if (tipo === "seleccion") {
            control = document.createElement("select");

            for (const [valor, texto] of opciones.valores) {
                const opcion = elemento("option", "", texto);
                opcion.value = valor;
                control.append(opcion);
            }
        } else {
            control = document.createElement("input");
            control.type = tipo === "numero" ? "number" : tipo === "fecha" ? "date" : "text";

            if (tipo === "numero") {
                control.min = "0";
                control.step = "any";
            }
        }

        control.id = identificador;

        if (opciones.ayuda) {
            control.placeholder = opciones.ayuda;
        }

        const actual = leer(objeto, ruta);
        control.value = actual === null || actual === undefined ? "" : String(actual);

        control.addEventListener("input", () => {
            let valor = control.value;

            if (tipo === "numero") {
                valor = valor === "" ? null : Number(valor);
            }

            escribir(objeto, ruta, valor);
            marcarCambio();
        });

        contenedor.append(rotulo, control);
        return contenedor;
    }

    function seccion(titulo, ...contenido) {
        const bloque = elemento("section", "editor-seccion");
        bloque.append(elemento("h3", "", titulo), ...contenido);
        return bloque;
    }

    function ayuda(texto) {
        return elemento("p", "editor-ayuda", texto);
    }

    function boton(texto, clase, accion) {
        const control = elemento("button", `editor-boton ${clase || ""}`.trim(), texto);
        control.type = "button";
        control.addEventListener("click", accion);
        return control;
    }

    function doble(...campos) {
        const fila = elemento("div", "editor-doble");
        fila.append(...campos);
        return fila;
    }

    // ----------------------------------------------------------
    // Erupciones
    // ----------------------------------------------------------

    function seccionErupciones() {
        const lista = elemento("div", "editor-lista");

        function dibujar() {
            lista.replaceChildren();
            ficha.erupciones = ficha.erupciones || [];

            ficha.erupciones.forEach((evento, indice) => {
                const item = elemento("div", "editor-item");
                const fecha = campo("Fecha", "fecha", evento, "texto", { ayuda: "AAAA-MM-DD, AAAA-MM o AAAA" });
                const descripcion = campo("Descripción (opcional)", "descripcion", evento);

                fecha.querySelector("input").addEventListener("input", () => {
                    evento.precision = precisionDe(evento.fecha);
                });

                const quitar = boton("Quitar", "peligro", () => {
                    ficha.erupciones.splice(indice, 1);
                    marcarCambio();
                    dibujar();
                });

                item.append(doble(fecha, descripcion), quitar);
                lista.append(item);
            });
        }

        dibujar();

        return seccion(
            "Actividad histórica",
            ayuda("La ficha muestra las cuatro erupciones más recientes."),
            lista,
            boton("+ Añadir erupción", "", () => {
                ficha.erupciones = ficha.erupciones || [];
                ficha.erupciones.push({ fecha: "", precision: "dia", descripcion: "" });
                marcarCambio();
                dibujar();
            }),
            campo("Estado de actividad", "estado_actividad", ficha, "area"),
            campo(
                "Última erupción conocida (se muestra en «Fuentes y notas»)",
                "ultima_erupcion_texto",
                ficha,
                "area"
            )
        );
    }

    // ----------------------------------------------------------
    // Imágenes
    // ----------------------------------------------------------

    async function subir(archivo, rol) {
        const respuesta = await fetch(
            `./api/imagen?volcan=${encodeURIComponent(id)}&rol=${encodeURIComponent(rol)}`,
            {
                method: "POST",
                headers: { ...CABECERAS, "Content-Type": archivo.type || "application/octet-stream" },
                body: archivo
            }
        );
        const datos = await respuesta.json().catch(() => ({}));

        if (!respuesta.ok) {
            throw new Error(datos.error || `Error ${respuesta.status}`);
        }

        archivosNuevos.add(datos.archivo);
        return datos.archivo;
    }

    function elegirArchivo(alElegir) {
        const entrada = document.createElement("input");
        entrada.type = "file";
        entrada.accept = "image/jpeg,image/png,image/webp";
        entrada.addEventListener("change", () => {
            if (entrada.files[0]) {
                alElegir(entrada.files[0]);
            }
        });
        entrada.click();
    }

    function miniatura(imagen) {
        if (!imagen?.archivo) {
            return elemento("span", "editor-imagen-vacia", "Sin imagen");
        }

        const img = document.createElement("img");
        img.src = imagen.archivo;
        img.alt = "";
        img.loading = "lazy";
        return img;
    }

    function seccionImagenes() {
        const lista = elemento("div");

        function dibujar() {
            lista.replaceChildren();
            ficha.imagenes = ficha.imagenes || {};

            for (const [rol, nombre] of ROLES_IMAGEN) {
                const imagen = ficha.imagenes[rol];
                const fila = elemento("div", "editor-imagen");
                const detalle = elemento("div");
                const acciones = elemento("div", "editor-imagen-acciones");
                const subirBoton = boton(imagen?.archivo ? "Reemplazar" : "Subir", "", () => {
                    elegirArchivo(async archivo => {
                        subirBoton.disabled = true;
                        mostrarEstado("Subiendo imagen…");

                        try {
                            const ruta = await subir(archivo, rol);

                            if (imagen?.archivo) {
                                archivosPorBorrar.add(imagen.archivo);
                            }

                            ficha.imagenes[rol] = { archivo: ruta, pie: imagen?.pie || "" };
                            marcarCambio();
                        } catch (error) {
                            mostrarEstado(error.message, true);
                        }

                        dibujar();
                    });
                });

                acciones.append(subirBoton);

                if (imagen?.archivo) {
                    acciones.append(
                        boton("Quitar", "peligro", () => {
                            archivosPorBorrar.add(imagen.archivo);
                            delete ficha.imagenes[rol];
                            marcarCambio();
                            dibujar();
                        })
                    );
                }

                detalle.append(elemento("strong", "", nombre), acciones);
                fila.append(miniatura(imagen), detalle);
                lista.append(fila);

                if (imagen?.archivo) {
                    lista.append(
                        campo("Pie de imagen", "pie", imagen)
                    );
                }
            }
        }

        dibujar();

        return seccion(
            "Imágenes",
            ayuda("Se aceptan JPG, PNG o WebP; se comprimen a WebP al subirlas."),
            lista
        );
    }

    function seccionGaleria() {
        const lista = elemento("div");

        function dibujar() {
            lista.replaceChildren();
            ficha.galeria = ficha.galeria || [];

            ficha.galeria.forEach((foto, indice) => {
                const fila = elemento("div", "editor-imagen");
                const detalle = elemento("div");
                const acciones = elemento("div", "editor-imagen-acciones");

                acciones.append(
                    boton("Foto principal", "", () => {
                        ficha.imagenes = ficha.imagenes || {};

                        if (ficha.imagenes.foto?.archivo) {
                            archivosPorBorrar.add(ficha.imagenes.foto.archivo);
                        }

                        ficha.imagenes.foto = { archivo: foto.archivo, pie: foto.pie || "" };
                        marcarCambio();
                        panelCuerpo();
                    }),
                    boton("Quitar", "peligro", () => {
                        archivosPorBorrar.add(foto.archivo);
                        ficha.galeria.splice(indice, 1);
                        marcarCambio();
                        dibujar();
                    })
                );
                detalle.append(elemento("strong", "", `Foto ${indice + 1}`), acciones);
                fila.append(miniatura(foto), detalle);
                lista.append(fila, campo("Pie de foto", "pie", foto));
            });
        }

        dibujar();

        return seccion(
            "Galería de fotos",
            ayuda("Las fotos de la galería se ven en «Fuentes y notas». Cualquiera puede pasar a ser la foto principal."),
            lista,
            boton("+ Añadir foto", "", () => {
                elegirArchivo(async archivo => {
                    mostrarEstado("Subiendo foto…");

                    try {
                        const ruta = await subir(archivo, "galeria");
                        ficha.galeria = ficha.galeria || [];
                        ficha.galeria.push({ archivo: ruta, pie: "" });
                        marcarCambio();
                    } catch (error) {
                        mostrarEstado(error.message, true);
                    }

                    dibujar();
                });
            })
        );
    }

    // ----------------------------------------------------------
    // Panel
    // ----------------------------------------------------------

    function panelCuerpo() {
        const cuerpo = panel.querySelector(".editor-cuerpo");
        cuerpo.replaceChildren();
        ficha.afectaciones = ficha.afectaciones || {};

        const secciones = [
            seccion(
                "Boletín (todos los volcanes)",
                doble(
                    campo("Número de boletín", "numero_boletin", general),
                    campo("Fecha del boletín", "fecha_boletin", general, "fecha")
                ),
                campo("Red social", "red_social", general)
            ),
            seccion(
                "Identificación",
                campo("Nombre principal", "nombre_principal", ficha),
                doble(
                    campo("Municipio", "municipio", ficha),
                    campo("Altitud (m s. n. m.)", "altitud_msnm", ficha, "numero")
                ),
                doble(
                    campo("Vereda", "vereda", ficha),
                    campo("Corregimiento", "corregimiento", ficha)
                ),
                campo("Descripción de la ubicación", "ubicacion_texto", ficha, "area")
            ),
            seccion(
                "Clasificación y estado",
                campo("Tipo de diapiro", "tipo", ficha, "texto", { ayuda: "Tipo I, Tipo II…" }),
                campo("Nivel de actividad vigente", "nivel_actividad", ficha, "seleccion", {
                    valores: NIVELES
                })
            ),
            seccionErupciones(),
            seccion(
                "Morfología y flujo",
                campo(
                    "Morfología (vacío = texto regional)",
                    "morfologia",
                    ficha,
                    "area"
                ),
                campo("Comportamiento del flujo", "comportamiento_flujo", ficha, "area")
            ),
            seccion(
                "Gestión del riesgo (afectaciones)",
                campo("Población en el área de influencia", "afectaciones.poblacion", ficha, "area"),
                doble(
                    campo("Construcciones a 500 m", "afectaciones.construcciones_500m", ficha, "numero"),
                    campo("Construcciones a 1 km", "afectaciones.construcciones_1km", ficha, "numero")
                ),
                campo("Infraestructura crítica expuesta", "afectaciones.infraestructura_critica", ficha),
                campo("Amenaza (texto)", "afectaciones.amenaza_texto", ficha, "area")
            ),
            seccion(
                "Red de monitoreo",
                ayuda("Las estaciones sísmicas y el monitoreo InSAR del portal se añaden automáticamente."),
                campo("Descripción de la red", "red_monitoreo", ficha, "area")
            )
        ];

        if (ficha.morfometria) {
            secciones.push(
                seccion(
                    "Morfometría",
                    doble(
                        campo("Clase", "morfometria.clase", ficha, "seleccion", {
                            valores: [["", "Sin definir"], ["Cono", "Cono"], ["Pastel", "Pastel"], ["Domo", "Domo"]]
                        }),
                        campo("Tamaño", "morfometria.tamano", ficha, "seleccion", {
                            valores: [["", "Sin definir"], ["Pequeño", "Pequeño"], ["Mediano", "Mediano"], ["Grande", "Grande"]]
                        })
                    )
                )
            );
        }

        secciones.push(
            seccionImagenes(),
            seccionGaleria(),
            seccion(
                "Notas internas",
                ayuda("No se muestran en el sitio; son solo para el equipo."),
                campo("Notas", "notas_internas", ficha, "area")
            )
        );

        cuerpo.append(...secciones);
    }

    function construirPanel() {
        panel.replaceChildren();

        const cabecera = elemento("div", "editor-cabecera");
        const titulo = elemento("h2", "", "Editar boletín");
        titulo.append(elemento("small", "", contexto.nombre));
        cabecera.append(titulo, boton("Cerrar", "", cerrar));

        const pie = elemento("div", "editor-pie");
        pie.append(
            elemento("span", "estado-guardado", ""),
            boton("Cancelar", "", cerrar),
            boton("Guardar", "primario", guardar)
        );

        panel.append(cabecera, elemento("div", "editor-cuerpo"), pie);
        panelCuerpo();
    }

    // ----------------------------------------------------------
    // Abrir, cerrar y guardar
    // ----------------------------------------------------------

    function abrir() {
        if (abierto) {
            return;
        }

        abierto = true;
        cambios = false;
        original = structuredClone({ general, ficha });
        archivosNuevos = new Set();
        archivosPorBorrar = new Set();

        contexto.editando = true;
        document.body.classList.add("editando");
        construirPanel();
        panel.hidden = false;
        botonEditar.hidden = true;
        renderizar();
    }

    async function cerrar() {
        if (cambios && !window.confirm("Hay cambios sin guardar. ¿Descartarlos?")) {
            return;
        }

        if (cambios) {
            restaurar(general, original.general);
            restaurar(ficha, original.ficha);

            for (const archivo of archivosNuevos) {
                await borrarArchivo(archivo);
            }
        }

        salir();
    }

    function salir() {
        abierto = false;
        cambios = false;
        contexto.editando = false;
        document.body.classList.remove("editando");
        panel.hidden = true;
        panel.replaceChildren();
        botonEditar.hidden = false;
        renderizar();
    }

    async function borrarArchivo(archivo) {
        try {
            await fetch(`./api/imagen?archivo=${encodeURIComponent(archivo)}`, {
                method: "DELETE",
                headers: CABECERAS
            });
        } catch (error) {
            console.warn("No se pudo borrar la imagen:", archivo, error);
        }
    }

    async function guardar() {
        const botones = panel.querySelectorAll(".editor-pie button");
        botones.forEach(control => { control.disabled = true; });
        mostrarEstado("Guardando…");

        ficha.actualizado = hoyIso();

        try {
            const respuesta = await fetch("./api/boletin", {
                method: "PUT",
                headers: { ...CABECERAS, "Content-Type": "application/json" },
                body: JSON.stringify({
                    general,
                    volcanes: boletin.volcanes
                })
            });
            const datos = await respuesta.json().catch(() => ({}));

            if (!respuesta.ok) {
                throw new Error(datos.error || `Error ${respuesta.status}`);
            }

            const vigentes = archivosReferenciados(ficha);

            for (const archivo of archivosPorBorrar) {
                if (!vigentes.has(archivo)) {
                    await borrarArchivo(archivo);
                }
            }

            archivosPorBorrar = new Set();
            archivosNuevos = new Set();
            original = structuredClone({ general, ficha });
            cambios = false;
            renderizar();
            mostrarEstado("Guardado. Recuerde publicar los cambios con commit y push.");
        } catch (error) {
            mostrarEstado(`No se pudo guardar: ${error.message}`, true);
        }

        botones.forEach(control => { control.disabled = false; });
    }
}
