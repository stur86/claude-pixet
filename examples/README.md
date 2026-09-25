# Examples

PNG images made with pixet.

File names use the format `XX_<description>.png`:

- `XX` is a two-digit sequence number (`01`, `02`, ...). Use the next free number.
- `<description>` is short, lowercase, with words joined by underscores.

Example: `01_red_mushroom.png`

An example can also be a folder `XX_<description>/` when it keeps the
intermediate steps (made with `new_image(..., record_frames=True)`):

- `03_anime_girl_portrait/`: 64x64 portrait. `portrait.png` is the final
  image, `portrait_0001.png` ... `portrait_0075.png` are the steps (undone
  attempts included), `portrait_x8.png` is an 8x scaled copy and
  `timelapse.gif` replays the steps.
- `04_sailing_ship_port/`: 128x128 scene. `scene.png` is the final image,
  `scene_0001.png` ... `scene_0132.png` are the steps, `scene_x6.png` is a
  6x scaled copy and `timelapse.gif` replays the steps.
