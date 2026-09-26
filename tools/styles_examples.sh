#!/bin/sh
# Styles: a genre tour, four full songs, and a lineage that wanders genres (renders/production/styles/README.txt).
# From the repository root, once the styles branch is merged into main:
#     sh tools/styles_examples.sh                       (writes renders/production/styles/)
#     OUT=/some/folder sh tools/styles_examples.sh      (writes there)
#     SONGBIRD=/path/to/checkout sh tools/styles_examples.sh   (renders with that checkout's code)
# One render at a time, niced, two threads each: the machine is shared.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="${SONGBIRD:-$HERE}"
OUT="${OUT:-$ROOT/renders/production/styles}"
mkdir -p "$OUT/tour" "$OUT/songs" "$OUT/lineage"
cd "$ROOT"
export OMP_NUM_THREADS=2 NUMBA_NUM_THREADS=2
H=songs/h-now-its-by-you.json
render() { nice -n 10 uv run --no-sync songbird render "$H" "$@"; }
excerpt() { nice -n 10 uv run --no-sync python tools/excerpt.py "$1"; }
PART="${1:-all}"

# 1. The genre tour: one made-up machine (ada) on one day, in every style, round the ring from the seed's
#    ballad; a verse and a refrain (with its intro, where the three fit in about a minute). Three lineage
#    voices (as if ada sang a third-generation parent), so the backing voices can be heard.
if [ "$PART" = all ] || [ "$PART" = tour ]; then
M="--machine fictional:ada --date 2026-09-27 --choir 3"
render $M --style ballad     --form intro verse refrain --out "$OUT/tour/01-ballad.flac"
render $M --style shanty     --form intro verse refrain --out "$OUT/tour/02-shanty.flac"
render $M --style stringband --form intro verse refrain --out "$OUT/tour/03-stringband.flac"
render $M --style country    --form intro verse refrain --out "$OUT/tour/04-country.flac"
render $M --style blues      --form verse refrain       --out "$OUT/tour/05-blues.flac"
render $M --style gospel     --form verse refrain       --out "$OUT/tour/06-gospel.flac"
render $M --style indie      --form intro verse refrain --out "$OUT/tour/07-indie.flac"
render $M --style synthfolk  --form intro verse refrain --out "$OUT/tour/08-synthfolk.flac"
render $M --style lofi       --form verse refrain       --out "$OUT/tour/09-lofi.flac"
render $M --style ambient    --form verse refrain       --out "$OUT/tour/10-ambient.flac"
render $M --style lullaby    --form verse refrain       --out "$OUT/tour/11-lullaby.flac"
render $M --style songwriter --form intro verse refrain --out "$OUT/tour/12-songwriter.flac"
render $M --style chamber    --form verse refrain       --out "$OUT/tour/13-chamber.flac"
fi

# 2. Full songs: the same machine on another day, four styles, the whole song (its own form).
if [ "$PART" = all ] || [ "$PART" = songs ]; then
M="--machine fictional:ada --date 2026-11-01 --choir 3"
render $M --style stringband                     --out "$OUT/songs/stringband.flac"
render $M --style gospel                         --out "$OUT/songs/gospel.flac"
render $M --style country --arrange feel=waltz   --out "$OUT/songs/country-waltz.flac"
render $M --style synthfolk                      --out "$OUT/songs/synthfolk.flac"
fi

# 3. A lineage that wanders: the seed, then six generations, each sung by another made-up machine a few
#    months after its parent and inheriting from it; every style here is the one the ring chose (nothing
#    forced). The machines were picked to show a lineage that wanders (README.txt has the usual rates).
if [ "$PART" = all ] || [ "$PART" = lineage ]; then
L="$OUT/lineage"
render --out "$L/0-seed.flac"
render --machine fictional:bo   --date 2026-09-26 --parent "$L/0-seed.json" --out "$L/1-bo.flac"
render --machine fictional:cy   --date 2027-01-15 --parent "$L/1-bo.json"   --out "$L/2-cy.flac"
render --machine fictional:dee  --date 2027-05-02 --parent "$L/2-cy.json"   --out "$L/3-dee.flac"
render --machine fictional:hana --date 2027-09-20 --parent "$L/3-dee.json"  --out "$L/4-hana.flac"
render --machine fictional:jun  --date 2028-01-10 --parent "$L/4-hana.json" --out "$L/5-jun.flac"
render --machine fictional:lu   --date 2028-05-18 --parent "$L/5-jun.json"  --out "$L/6-lu.flac"
for f in "$L"/[0-9]-*.flac; do
    case "$f" in *.verse-refrain.flac) ;; *) excerpt "$f" ;; esac
done
fi
