const SECRET_QUERY_KEY = /^(?:access_?token|auth(?:orization)?|api_?key|session(?:_?id)?|token|secret|signature|sig|password|passwd)$/i;

export function containsReflectedUrlSecret(url: URL): boolean {
  if (url.username || url.password || url.hash) return true;
  return [...url.searchParams.keys()].some((key) =>
    SECRET_QUERY_KEY.test(key.replace(/[.\-]/g, "_")),
  );
}
