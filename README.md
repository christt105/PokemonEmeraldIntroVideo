# Pokémon Esmeralda — sprites de la escena en bicicleta

Sprites limpios con canal alfa de la escena en la que el protagonista va en
bicicleta acompañado de Pokémon, listos para montar la animación en Aseprite
sobre un lienzo de 1280x640.

## De dónde salen

De `graphics/intro/scene_2` del proyecto de decompilación
[pret/pokeemerald](https://github.com/pret/pokeemerald) (clon disperso en
`decomp/`), copiados a `assets/`. Son los mismos datos que hay dentro de la
ROM, ya descomprimidos de LZ77 y con sus paletas, así que no hace falta
rippear del cartucho ni grabar el emulador.

La escena de bici es de **Esmeralda**, no de Ruby: sale en la intro (escena 2,
de día) y se reutiliza en los créditos con otras paletas y fondos. Ruby/Zafiro
usan Latios y Latias donde Esmeralda pone a Flygon; los tres están incluidos.

## Lo que hay en `sprites/`

`sprites/x4/` es el juego bueno: escala 4, que hace que los 160 px de alto de
la GBA den exactamente los 640 del lienzo. `sprites/x1/` es el tamaño original
por si prefieres escalar tú.

```
sprites/x4/
  characters/     ciclista y bicicleta
  pokemon/        Manectric, Torchic, Volbeat, Flygon, Latios, Latias
  pokemon_extra/  cualquier otro Pokémon que pidas
  backgrounds/    <escena>/{far,near,ground}.png + piezas de decorado
  aseprite/       .aseprite ya montados
  sprites.json    tamaños, duraciones y desplazamientos de cada cosa
```

Cada PNG es una **tira horizontal** de fotogramas del mismo tamaño, recortada
a la caja más ajustada que sigue conteniendo todos los fotogramas de esa
animación, de modo que no se descuadran entre sí. En Aseprite entran con
*File > Import Sprite Sheet* indicando el ancho de fotograma que dice
`sprites.json`.

### Los `.aseprite` ya montados

En `sprites/x4/aseprite/` tienes un archivo por animación, con un fotograma
por cada uno y **la duración exacta del juego** (los `ANIMCMD` de
`src/intro.c`): 67 ms el pedaleo y la carrera de Manectric, 83 ms el paseo de
Torchic, 33 ms el aleteo de Volbeat.

Y `scene_<escena>.aseprite`, un lienzo de 1280x640 de **64 fotogramas con el
escenario ya animado**, todo en capas separadas:

```
manectric / torchic / rider / volbeat / flygon
bg_ground          el suelo            64 px/fotograma
scenery_layer_1    decorado cercano    36 px/fotograma
scenery_layer_0    decorado lejano     18 px/fotograma
bg_near            arbolado o mar      16 px/fotograma
bg_far             montañas o cielo     0 (fondo lejano fijo)
backdrop           color plano
```

Hay uno por ambientación: `day`, `sunset`, `night`, `ocean`, `ocean_sunset`.

### Cómo se mueve

Todo va hacia la derecha, cada capa a su ritmo, con las velocidades reales del
juego escaladas x4. El loop dura 64 fotogramas a 67 ms — 4,3 segundos, que son
exactamente los 256 fotogramas de GBA del ciclo original.

Cierra sin costura por construcción, no por aproximación. Cada capa se exporta
como una tira **una periodo más ancha que el lienzo**, empieza colocada un
periodo a la izquierda y se desliza hasta 0, momento en el que el siguiente
periodo ya ocupa su lugar. Como el desplazamiento total (fotogramas x
velocidad) es un múltiplo exacto del periodo, el fotograma 65 cae encima del
primero. Los ciclos de los personajes (4, 4, 4 y 2 fotogramas) también dividen
64, así que empalman igual.

El periodo es el **repetido real** de cada capa, no los 256 px del tilemap:
casi todas se repiten cada 128 px, lo que hace las tiras más estrechas. Está
medido capa por capa y anotado en `sprites.json` y en el campo *data* de cada
capa de Aseprite.

Para otra duración, `--script-param frames=N`. Con menos de 64 las velocidades
se redondean a la más cercana que cierre el loop, y por debajo de 32 las dos
capas de decorado colapsan a la misma velocidad y se pierde su parallax.

Lo que **no** está animado es el vuelo de Flygon y el vaivén en ocho de
Volbeat: en el juego se mueven con curvas seno propias, y eso es composición,
no escenario. Los tienes pedaleando y aleteando en su sitio.

## Editor visual

```bash
python3 editor/serve.py
```

y abre `http://127.0.0.1:8777/editor/`. Es el mismo `scene.json`, pero con
una vista: la escena se reproduce en bucle mientras la editas.

- **Arrastra los sprites** por el lienzo para colocarlos. Si el actor tiene
  posiciones clave, arrastrar mueve la clave seleccionada (o la más cercana al
  fotograma en el que estés), no el actor entero.
- **La línea de tiempo** de abajo muestra las claves del actor elegido como
  rombos. Pinchas para moverte por el bucle, arrastras el rombo para
  seleccionarlo, y *+ Clave aquí* añade una en el fotograma actual con la
  posición que tenga en ese momento.
- **El panel de la derecha** lleva cámara (zoom, fondo, duración), la lista de
  actores y sus propiedades: sprite, retardo, profundidad, anclaje, volteo,
  orden de fotogramas y el vaivén.
- **Guardar** escribe `scenes/<nombre>.json` y **Renderizar GIF** lanza
  `compose.py` y te deja el enlace. El cuadro de JSON de abajo está siempre
  sincronizado en los dos sentidos: puedes pegar uno y darle a *Aplicar*.

El editor avisa en rojo cuando el ciclo de un actor no divide la duración del
bucle, que es el fallo fácil de cometer y difícil de ver.

El dibujado del editor y el de `compose.py` son la misma lógica escrita dos
veces, así que están comprobados uno contra otro: el mismo fotograma sale
idéntico píxel a píxel en los 1280x640. Lo que ves es lo que se renderiza.

Sirve el directorio del proyecto para poder leer los sprites, se ata a
localhost, y sus dos endpoints sólo escriben y leen dentro de `scenes/`.

## Componer la escena: `compose.py`

Aseprite es bueno dibujando sprites y malo componiendo: no tiene interpolación
entre posiciones clave, así que cualquier movimiento acaba siendo celdas
dibujadas una a una — 64 fotogramas por 10 capas de puntos en la línea de
tiempo. Por eso la composición vive en un archivo de datos:

```bash
python3 compose.py scenes/wide.json --format gif mp4
```

`scenes/wide.json` describe la escena entera. Cambiar cuánto te alejas, qué
Pokémon salen o por dónde pasan es editar ese archivo y volver a lanzarlo.

### Cámara

`zoom` es el aumento entero. Con el lienzo de 1280x640: `zoom: 4` enseña
320x160 px de GBA (personajes al tamaño de siempre), `zoom: 3` enseña 427x214
y los deja al 75%, `zoom: 2` al 50%.

El suelo queda **pegado a la base del lienzo**, así que alejarse añade cielo
por arriba y todo lo que pisa la hierba se queda donde está. Ese cielo extra
lo rellena la fila superior de la capa lejana: la GBA nunca enseña esa zona,
tiene el color de fondo sin asignar, y sale negro si no se hace nada.

### Actores

Coordenadas en píxeles de GBA, `y: 152` es la hierba.

```json
{
  "name": "mudkip",
  "sprite": "external/mudkip_walk.png",
  "frames": 3,
  "order": [0, 1, 2, 1],
  "delay": 8,
  "flip_x": true,
  "anchor": "bottom-center",
  "depth": 25,
  "keys": [
    { "f": 0,  "x": 300, "y": 150, "ease": "in-out" },
    { "f": 96, "x": 105, "y": 150, "ease": "in-out" }
  ],
  "motion": [ { "type": "sine", "axis": "y", "amp": 1, "period": 32 } ]
}
```

- **`keys`** son las posiciones clave. Se interpola entre ellas, con `ease`
  `linear`, `in`, `out` o `in-out`, y el último tramo vuelve solo al primer
  key para cerrar el bucle.
- **`motion`** se suma encima: `sine`, `cosine` o `wobble` (el temblor de 1 px
  que el juego sortea al azar, aquí periódico), sobre el eje `x` o `y`.
- **`order`** reordena los fotogramas del sprite. Un ping-pong `[0,1,2,1]`
  arregla los ciclos de 3 fotogramas, que no dividen los 256 del bucle.
- **`depth`** decide quién tapa a quién; **`anchor`** dice qué punto del sprite
  cae en la coordenada (`bottom-center` son los pies).

Si el ciclo de un actor (fotogramas x `delay`) no divide `loop_frames`, el
sprite pega un salto al reiniciarse. `compose.py` lo detecta y avisa por
consola diciendo qué actor y con qué número.

## Meter sprites de fuera

Las hojas sacadas de otros sitios traen los fotogramas a distancias
irregulares y cada uno con su propio desplazamiento, lo que hace que el sprite
tiemble al animarse. `import_sprite.py` los encuentra, les da una caja común y
los alinea:

```bash
python3 import_sprite.py out/Walk-Anim-export.png --name mudkip_walk
```

Por defecto los alinea por `bottom-center`, que es lo que quieren los ciclos de
andar: los pies se quedan clavados. Sale en `sprites/x*/external/`.

El Mudkip de Mystery Dungeon que ya está metido mide 22x22 frente a los 18x24
de Torchic, así que la escala pega casi exacta pese a ser otro estilo. Lleva
`flip_x` porque mira al lado contrario que el resto.

## Cambiar los Pokémon

Los seis de la escena están dibujados de perfil y en movimiento, que es lo que
encaja con la bici. Para cualquier otro:

```bash
python3 export_pokemon.py pikachu swampert rayquaza
```

Salen en `sprites/x4/pokemon_extra/`: `anim_front` (2 fotogramas), `back` e
`icon` (2 fotogramas), con `--shiny` si quieres la variocolor y `--list` para
ver los 400 y pico nombres disponibles. Son los sprites normales de combate,
no de perfil corriendo, así que quedan más de "posando al lado" que de
"corriendo junto a la bici" — es exactamente lo que hacen los créditos del
juego, que usan estos mismos sprites.

## Detalles que te van a hacer falta

**La bicicleta lleva sombra pintada.** Las dos filas inferiores del sprite son
una sombra de contacto en verde oliva, hecha para fundirse con el césped;
sobre cualquier otro fondo canta. Por defecto se separa a
`characters/bicycle_brendan_shadow.png` y el sprite sale limpio. Con
`--shadow keep` la dejo pegada y con `--shadow drop` la tiro.

**El ciclista y la bici son dos sprites.** El juego los dibuja por separado,
con la bici 8 px por debajo. Los tienes sueltos (`brendan_intro_bike.png`,
`bicycle_brendan_bike.png`) y ya compuestos (`brendan_on_bike.png`), que es lo
que normalmente querrás.

**Flygon, Latios y Latias ocupan dos sprites** de 64x64 en el juego porque no
caben en uno. Los devuelvo cosidos en una sola pieza de 128x64.

**El decorado viene en dos versiones.** Las piezas sueltas
(`scenery_tree_large.png` y compañía) por si quieres colocarlas a mano, y
`scenery_layer_0/1.png`, que son esas mismas piezas ya repartidas y tileables,
agrupadas por velocidad de parallax. Las plantillas usan las segundas.

**Las capas de fondo son tileables** y salen un periodo más anchas que el
lienzo para que puedas deslizarlas sin que asome hueco. Periodo y velocidad de
cada una están en `sprites.json` (`tile_period` y `scroll_px_per_gba_frame`).

## Regenerar

```bash
python3 export_sprites.py
aseprite -b --script-param root=sprites/x4 --script-param scene=day --script make_aseprite.lua
```

`export_sprites.py --scale 1 2 4 8` saca las escalas que quieras (siempre
nearest-neighbour, sin suavizado).

## Los otros dos caminos

`render_bike_loop.py` reproduce la escena tal cual sale en el juego, sin
parametrizar: sirve de referencia para comparar. `gba.py` es el
mini-renderizador que comparten los tres: tiles 4bpp, fondos con screenblocks
de 32x32 y OBJs con mapeo de tiles 1D.

Las plantillas `.aseprite` con el escenario ya animado siguen ahí y siguen
funcionando; para composición `compose.py` es más manejable, pero si prefieres
mover cosas a mano en Aseprite, ese camino no se ha roto.
