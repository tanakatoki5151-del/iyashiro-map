# ECOSCAPE B122 preview gate

This marker requests one fresh Vercel preview after the earlier account-level build-rate-limit rejection.

Required readback before merge:

- `/api/profile?lat=35.723007&lng=139.694672` returns canonical cell `g130-240`.
- `layers.ecoscape.availability` is `available`.
- P25 state is `CAUTION`, known pillars 4, favorable 1, caution 2.
- `scoringEffect` remains `none` and `candidateOverride` remains `false`.
- Legacy scores remain 50 / 75 / 75.
- `/profile` renders the ECOSCAPE card without mobile or runtime regression.

Do not merge PR #15 if the preview is not built and read back.
