# Cover art brief: the seed packet (2026-09-27)

For an agent (or a person) building the album cover in Blender. The artist's direction: "a square image
with a close-up of the seed packet with all info on the front, QR code at the bottom with URL"; of the
mockups, the one they liked is the daisy sprouting through concrete.

## The idea

"Now It's by You" is a folk song passed between people and computers; the song file is also the program
that sings it, and it asks to be sown. A *volunteer* is a plant that comes up where nobody planted it. So
the cover is a **seed packet**: cream letterpress paper, a woodcut daisy pushing up through a crack in a
concrete slab, and the sowing address with a QR code. The packet is the whole cover: close up, filling the
square, photographed like a real object on a table, not illustrated flat.

## Deliverable

- One square image, **3000 x 3000 px**, sRGB PNG (and a JPEG at quality 92 for uploads). Also a 1500 px
  version. The QR must scan from the 1500 px version on a phone (test it).
- Optional: a second frame with the packet's back (sowing instructions) beside it, same set-up, for the
  seed page.
- Files to renders/review/artwork/cover-3000.png etc.; the .blend beside them.

## The packet's face (the texture: nothing but artist, title, picture, count, address)

Use `renders/review/artwork/packet-front-full.svg` as the packet's face, rasterised at 300 px/in (990 x
1440 px = 3.3 x 4.8 in). The artist wants no extraneous text: the face carries exactly this, top to bottom:

1. kicker, red small capitals, letterspaced: THE VOLUNTEERS
2. title, black serif, bold: Now It's by You
3. a seed count in small grey letterspaced capitals, as a real packet prints one: MIN. 1 SEED (one file is
   enough; alternatives if the artist prefers: MIN. 10 SEEDS for the ten who sang, MIN. 51 SEEDS for the
   verses in the bank)
4. the illustration, large: one daisy (white petals, yellow centre, two leaves), its stem down into a crack
   in a concrete slab
5. a thin-and-thick rule
6. bottom: the QR code at the left (it encodes https://now.itsby.you, error level M, made by `segno`) and
   beside it **now.itsby.you** in bold serif
7. a double-rule border (thick outside, thin inside) around the whole face.

No tagline, no instructions, no licence line, no date, no logo. Replace the daisy and the slab with a
proper **woodcut**: black line, hatching, the crack running into the slab, one flower only. The Gemini
mockups `gemini-packet-front.png` and `gemini-cover-square.png` show the look wanted for the illustration
(their text is wrong; ignore it). Keep the vector's type and layout.

## Materials, light, camera

- **Paper:** the artist's priority: it must read as real, handled paper. Cream, uncoated, toothy (a fine
  noise bump, not canvas), 0.3 mm thick with a visible edge, and **wrinkled**: a displacement map with a few
  soft creases across the face, a dog-eared corner, the edges very slightly frayed, a faint fold line where
  the flap was opened once; the wrinkles must catch the raking window light. The ink slightly **pressed in** (letterpress: a shallow displacement on the printed areas, darker in
  the recess), the red a printer's vermilion (#b8432e), the black a warm ink (#2b231d), never pure black.
  A glued back seam and a folded top flap, as a real seed envelope has (the flap closed).
- **Contents:** the envelope is slightly full: a few seeds' worth of bulge low in the packet; two or three
  loose seeds (small, brown, elongated) on the table by its foot.
- **Surface:** an old wooden table (oak, scuffed, matte) or dark worn linen; muted, warm, out of focus at
  the edges. Nothing else in frame.
- **Light:** one soft window light from the upper left, a gentle fill from the right, a soft shadow under
  the packet's lower edge. No rim light, no coloured light, no lens flare.
- **Camera:** 50 mm equivalent, straight on with a 2 to 4 degree tilt, the packet filling about 80 to 85% of
  the square's height, its top and bottom edges inside the frame; f/4-ish depth of field so the QR and the
  title are sharp and the table falls off. The bottom block (QR + address) must be fully sharp and
  unobstructed.
- **Render:** Cycles, 512+ samples with denoise, filmic/AgX with a slight warm grade; keep the paper's
  whites around 90% grey, not blown.

## What to avoid

Gradients as design, glossy paper, drop-shadow "3D" type, purple or teal, bokeh balls, a hero photograph
behind the packet, floating objects, extra props, emoji, anything that reads as a template.

## References in the repo

- `renders/review/artwork/packet-front-full.svg` / `.png`: the face (vector, real QR).
- `renders/review/artwork/cover-square.png`: the flat vector mockup of the square framing.
- `renders/review/artwork/gemini-cover-square.png`, `gemini-packet-front.png`: mood for paper, light and
  the woodcut (text in them is wrong).
- `docs/IDENTITY.md` (when it lands): the palette and type the pages use; the packet should match.
