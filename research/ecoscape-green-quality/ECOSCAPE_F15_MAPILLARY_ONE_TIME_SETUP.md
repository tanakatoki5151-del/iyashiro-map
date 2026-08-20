# ECOSCAPE F15 Mapillary one-time setup

F15 is fully automated. Do not paste the token into ChatGPT, issues, commits, or logs.

## One-time account step

1. Create or obtain a Mapillary developer access token through the official Mapillary developer console.
2. Open the GitHub repository `tanakatoki5151-del/iyashiro-map`.
3. Go to `Settings → Secrets and variables → Actions → New repository secret`.
4. Name the secret `MAPILLARY_ACCESS_TOKEN`.
5. Paste the token and save it.
6. Run the GitHub Actions workflow `ECOSCAPE F15 Open Imagery Fallback`.

## Automatic processing

- Wikimedia Commons is queried whether or not the token exists.
- Mapillary is added only when the secret is present.
- Only images with source and license records are admitted.
- Images are downloaded to temporary storage, analyzed, and deleted.
- The artifact retains only numerical features, source links, attribution and license.
- Google imagery is never fetched or analyzed.
- Canonical ranks, scores and candidates are never changed.

## Security and decision locks

- The workflow logs only whether the token exists, never its value.
- Image bytes in the release artifact must equal zero.
- `rankingEffect=none`.
- `scoringEffect=none`.
- `candidateOverride=0`.

If open imagery is still insufficient, maintenance and cleanliness remain `UNKNOWN`. Missing imagery never means clean or safe.
