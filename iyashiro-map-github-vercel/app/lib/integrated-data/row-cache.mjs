export class RowPromiseLruCache {
  #limit;
  #entries = new Map();

  constructor(limit) {
    if (!Number.isInteger(limit) || limit < 1) {
      throw new TypeError("LRU limit must be a positive integer.");
    }
    this.#limit = limit;
  }

  get size() {
    return this.#entries.size;
  }

  get(key) {
    const value = this.#entries.get(key);
    if (value === undefined) return undefined;
    this.#entries.delete(key);
    this.#entries.set(key, value);
    return value;
  }

  set(key, value) {
    this.#entries.delete(key);
    this.#entries.set(key, value);
    while (this.#entries.size > this.#limit) {
      const oldest = this.#entries.keys().next().value;
      this.#entries.delete(oldest);
    }
  }

  deleteIfSame(key, value) {
    if (this.#entries.get(key) === value) {
      this.#entries.delete(key);
      return true;
    }
    return false;
  }

  clear() {
    this.#entries.clear();
  }
}
