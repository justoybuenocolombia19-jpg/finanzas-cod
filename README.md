# Finanzas COD · Rayzen + Dropshipping

App local (Streamlit + SQLite) para subir cada semana los reportes de pedidos de Dropi/Globaltradecol
y ver la **utilidad neta real** (después de fletes de devolución y gastos), Pareto 80/20, tendencias
semanales y la lista de llamadas de pedidos en riesgo. Todo en español, COP y fechas dd-mm-aaaa.

## Abrir la app
- **Mac:** doble clic en `iniciar.command` (la primera vez instala todo, 1-2 min).
- **Terminal:** `cd ~/finanzas-cod && . .venv/bin/activate && streamlit run app.py`

Se abre en http://localhost:8501. Tus datos quedan en `data/finanzas.db` (haz copia de ese archivo para respaldar).

## Flujo semanal
1. **Cargar archivos:** arrastra todos los .xlsx de la semana juntos. La app detecta el estado por `ESTATUS`,
   evita duplicados por `ID` (un pedido que cambió de estado se actualiza) y asigna la semana.
2. **Gastos:** registra publicidad (Meta/TikTok), empaques y otros de la semana. Los gastos fijos
   (apps, nómina, administrativos, arriendo) se configuran una vez y se prorratean por días.
3. **Tablero / Pareto / Semanas:** KPIs, 80/20, transportadoras, tendencias, precio y costo por producto.
   Filtra por marca y semanas (rango continuo o **la selección de semanas que quieras**, ver abajo).
4. **Lista de llamadas:** pedidos en oficina/novedad por prioridad; marca "llamado" y "resultado".
5. **Exportar** a Excel o PDF desde el Tablero.

**Primera vez:** en *Catálogo y marcas* nombra cada producto (se crea uno por precio de venta) y asígnalo
a Rayzen o Dropshipping. Sin eso, los pedidos quedan "Sin asignar" y solo aparecen en Consolidado.

## Paneles: un espacio por negocio (o personal)
Arriba de cada pantalla eliges el **panel**. Cada panel es totalmente independiente (sus propios pedidos, gastos,
catálogo y notas, en su propio archivo dentro de `data/paneles/`). Créalos con **➕ Panel**:
- **Negocio con pedidos:** todo lo de arriba (cargar reportes, tablero, Pareto, historial, llamadas…). Un panel nuevo
  tiene una sola marca (su nombre): todos sus pedidos cuentan para ella. Puedes renombrar o agregar marcas en *Catálogo*.
- **Finanzas personales:** ingresos y gastos por categoría, balance, historial por semana y mes, y notas.
Tus datos de antes quedaron en el primer panel, «Mi negocio» (renómbralo en *Paneles*). Eliminar un panel lo quita del
menú y mueve su archivo a `data/papelera/`; no se borra. Cada panel tiene su propia copia de seguridad.

## Comparativos a tu gusto: elige las semanas que quieras
En el menú de la izquierda, «Semanas a analizar» tiene dos modos:
- **Rango continuo:** el de siempre, semana desde / semana hasta.
- **Elegir semanas:** picas cualquier combinación de semanas, no tienen que ser seguidas. Por ejemplo, comparar
  la semana 20 contra la 35 sin las que quedan en medio. Todo el resto de la app (Tablero, Pareto, tendencias,
  gastos, exportes) responde a esa selección igual que a un rango.

## Precio y costo por producto (cuando el proveedor cambia precios)
En **Pareto y rentabilidad → Precio y costo**, eliges un producto y ves su precio de venta y costo de proveedor
**promedio por semana**, uno junto al otro, con una línea punteada en las semanas donde alguno cambió más de 1 %
frente a la anterior. Así detectas rápido cuándo el proveedor subió el costo o cuándo ajustaste el precio de venta,
y qué le pasó al margen. Combínalo con «Elegir semanas» para comparar justo antes/después de un cambio.

## Historial: volver a una semana o mes
La pantalla **Historial** lista todas las semanas (o meses) con sus números clave. Abre cualquiera para ver el
resumen, los pedidos, los gastos y los archivos de ese período, y **complétalo**: sube más reportes (quedan asignados
a esa semana), agrega o corrige gastos, y deja **notas** (campañas, problemas, cambios). Avisa las semanas donde
faltan reportes. Un mes incluye las semanas cuyo jueves cae en él.

**Respaldo:** *Cargar archivos → Ajustes → Copia de seguridad* descarga todo (pedidos, gastos, catálogo, notas)
en un archivo `.db`. Tu información vive en `data/finanzas.db`; copiar ese archivo también sirve de respaldo.

## Fórmulas
- Tasa de entrega = entregados / (entregados + devueltos); tasa de devolución = devueltos / (entregados + devueltos)
- Recaudo = suma de `VALOR DE COMPRA EN PRODUCTOS` de entregados
- Utilidad bruta = suma de `GANANCIA` de entregados (Dropi ya descuenta el flete de ida)
- Flete perdido = `PRECIO FLETE` + `COSTO DEVOLUCION FLETE` de devueltos
- **Utilidad neta real = utilidad bruta − flete perdido − gastos**; margen = neta / recaudo
- ROAS = recaudo / publicidad; CAC = publicidad / entregados
- Gastos sin marca ("Compartido") se reparten entre marcas según su recaudo.

## Decisiones que puedes cambiar (Cargar archivos → Ajustes)
- **Semana de cada pedido:** por defecto, la semana del reporte en que llegó a su estado final. Un reporte
  exportado un lunes cuenta en la semana anterior. Alternativas: fecha del pedido o último movimiento.
- **Estatus desconocidos:** al cargar, la app te pregunta a qué estado equivalen y lo recuerda.

## Modo demo
Interruptor en el menú izquierdo: base aparte con datos ficticios; no toca tus datos reales.

## Pruebas
`. .venv/bin/activate && python -m pytest tests -q`
