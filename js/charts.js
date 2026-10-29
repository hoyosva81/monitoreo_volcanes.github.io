let graficaEvolucion = null;

// ============================================================
// SERIE TEMPORAL
// ============================================================

export function crearGraficaEvolucion(
    canvasId,
    serie
) {
    const canvas = document.getElementById(canvasId);

    if (!canvas) {
        console.error(`No existe el canvas #${canvasId}`);
        return false;
    }

    if (
        !Array.isArray(serie) ||
        serie.length === 0
    ) {
        console.error("La serie temporal está vacía.");
        return false;
    }

    const datos = serie
        .map(
            item => ({
                fecha: String(item.fecha ?? ""),
                promedio_cm: Number(item.promedio_cm)
            })
        )
        .filter(
            item =>
                item.fecha.length === 8 &&
                Number.isFinite(item.promedio_cm)
        )
        .sort(
            (a, b) => a.fecha.localeCompare(b.fecha)
        );

    if (datos.length === 0) {
        console.error(
            "La serie temporal no contiene puntos válidos para graficar."
        );
        return false;
    }

    if (graficaEvolucion) {
        graficaEvolucion.destroy();
        graficaEvolucion = null;
    }

    const etiquetas = datos.map(
        item => formatearFechaGrafica(item.fecha)
    );

    const valores = datos.map(
        item => item.promedio_cm
    );

    Chart.defaults.font.family = getComputedStyle(canvas).fontFamily;
    Chart.defaults.color = "#002040";

    graficaEvolucion = new Chart(
        canvas,
        {
            type: "line",

            data: {
                labels: etiquetas,
                datasets: [
                    {
                        label: "Deformación promedio acumulada (cm)",
                        data: valores,
                        borderColor: "#1f7a8c",
                        backgroundColor: "#A8D4EA",
                        pointBackgroundColor: "#002040",
                        borderWidth: 2,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        tension: 0.15,
                        fill: false
                    }
                ]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                interaction: {
                    mode: "index",
                    intersect: false
                },

                plugins: {
                    legend: {
                        display: true
                    },

                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return (
                                    "Deformación: " +
                                    context.parsed.y.toFixed(2) +
                                    " cm"
                                );
                            }
                        }
                    }
                },

                scales: {
                    x: {
                        title: {
                            display: true,
                            text: "Fecha"
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 12
                        }
                    },

                    y: {
                        title: {
                            display: true,
                            text: "Deformación promedio (cm)"
                        },
                        ticks: {
                            callback: function (valor) {
                                const valorRedondeado = Number(
                                    Number(valor).toFixed(2)
                                );

                                return `${valorRedondeado} cm`;
                            }
                        }
                    }
                }
            }
        }
    );

    return true;
}

function formatearFechaGrafica(fecha) {
    if (
        !fecha ||
        fecha.length !== 8
    ) {
        return fecha;
    }

    const anio = fecha.slice(0, 4);
    const mes = fecha.slice(4, 6);
    const dia = fecha.slice(6, 8);

    return `${dia}/${mes}/${anio}`;
}
