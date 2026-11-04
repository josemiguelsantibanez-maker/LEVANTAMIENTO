# Levantamiento → Revit 2025 (Dynamo)

1. En la app: ☰ → Exportar → **🏗 Para Revit**. Guarda el `..._revit.json` en el computador.
2. En Revit 2025 abre un proyecto con **familias de puertas y ventanas cargadas**.
3. Gestionar → **Dynamo** → Abrir → `Levantamiento_a_Revit.dyn`.
4. Deja Dynamo en modo **Manual**.
5. En el nodo **1) Archivo** elige el `.json`. Los nodos 2–4 son opcionales:
   - **Nivel ±0,00**: nivel de Revit que corresponde al ±0,00 del levantamiento (vacío = el más bajo). Cada nivel del levantamiento usa el nivel de Revit a su cota o crea uno nuevo con su vista de planta.
   - **Familia de puertas / ventanas contiene…**: parte del nombre de la familia que quieres usar.
6. Presiona **Ejecutar una sola vez**. Cada ejecución vuelve a crear los elementos.

Crea:
- Tipos de muro "Levantamiento NN cm" (una capa, según el espesor).
- Muros por su eje, con la altura del muro, la del recinto o la del proyecto.
- Puertas, ventanas y ventanales (antepecho 0) con tipos "Lev ANCHOxALTO" duplicados de la familia elegida.
- Vanos vacíos como aberturas en el muro.
- Habitaciones con nombre y altura.
- Ejes de referencia como Rejillas (Grids) con su nombre.
- Pilares como columnas estructurales (o arquitectónicas), tipo "Lev ANCHOxLARGO", con altura y giro. Nodo 5) opcional para elegir la familia.

Si el `.dyn` no abre: crea un nodo **Python Script** (motor CPython3), pega
`levantamiento_a_revit.py` y conecta un nodo **File Path** a IN[0].
