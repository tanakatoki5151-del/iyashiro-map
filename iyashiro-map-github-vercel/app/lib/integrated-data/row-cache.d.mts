export class RowPromiseLruCache<Key, Value> {
  constructor(limit: number);
  readonly size: number;
  get(key: Key): Promise<Value> | undefined;
  set(key: Key, value: Promise<Value>): void;
  deleteIfSame(key: Key, value: Promise<Value>): boolean;
  clear(): void;
}
