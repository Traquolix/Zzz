/**
 * Fixed-capacity ring buffer — O(1) push, O(1) random access.
 *
 * Designed for high-frequency streaming data (DAS detections at 10-50Hz).
 * Unlike array-based boundedAppend which copies on every push, CircularBuffer
 * overwrites the oldest slot in place — zero allocations, zero GC pressure.
 *
 * Usage:
 *   const buf = new CircularBuffer<DataPoint>(2000)
 *   buf.push(point)            // O(1), overwrites oldest when full
 *   buf.pushMany(points)       // batch push
 *   const arr = buf.toArray()  // newest-last ordered snapshot
 *   buf.drain(cutoff, ts => ts.timestamp)  // evict items older than cutoff
 */
export class CircularBuffer<T> {
  private buffer: (T | undefined)[]
  private head = 0 // next write index
  private _size = 0
  private readonly capacity: number

  constructor(capacity: number) {
    if (capacity <= 0) throw new Error('CircularBuffer capacity must be > 0')
    this.capacity = capacity
    this.buffer = new Array(capacity)
  }

  get size(): number {
    return this._size
  }

  get isFull(): boolean {
    return this._size === this.capacity
  }

  /** Push a single item. O(1). */
  push(item: T): void {
    this.buffer[this.head] = item
    this.head = (this.head + 1) % this.capacity
    if (this._size < this.capacity) this._size++
  }

  /** Push multiple items. O(n) where n = items.length. */
  pushMany(items: T[]): void {
    // If items exceed capacity, only keep the last `capacity` items
    if (items.length >= this.capacity) {
      const start = items.length - this.capacity
      for (let i = 0; i < this.capacity; i++) {
        this.buffer[i] = items[start + i]
      }
      this.head = 0
      this._size = this.capacity
      return
    }

    for (let i = 0; i < items.length; i++) {
      this.buffer[this.head] = items[i]
      this.head = (this.head + 1) % this.capacity
    }
    this._size = Math.min(this._size + items.length, this.capacity)
  }

  /** Return items in insertion order (oldest first, newest last). */
  toArray(): T[] {
    if (this._size === 0) return []
    const result = new Array<T>(this._size)
    const start = this._size < this.capacity ? 0 : this.head // when full, head points to the oldest
    for (let i = 0; i < this._size; i++) {
      result[i] = this.buffer[(start + i) % this.capacity] as T
    }
    return result
  }

  /** Return the last N items (newest), in insertion order. */
  lastN(n: number): T[] {
    const count = Math.min(n, this._size)
    if (count === 0) return []
    const result = new Array<T>(count)
    // head points to next write slot, so head-1 is the newest item
    const newest = (this.head - 1 + this.capacity) % this.capacity
    const start = (newest - count + 1 + this.capacity) % this.capacity
    for (let i = 0; i < count; i++) {
      result[i] = this.buffer[(start + i) % this.capacity] as T
    }
    return result
  }

  /**
   * Remove items from the front (oldest) that fail a predicate.
   * Useful for time-window eviction: `buf.drain(cutoff, p => p.timestamp)`
   *
   * Returns the number of items evicted.
   */
  drain(cutoff: number, getTimestamp: (item: T) => number): number {
    if (this._size === 0) return 0

    const start = this._size < this.capacity ? 0 : this.head
    let evicted = 0

    for (let i = 0; i < this._size; i++) {
      const item = this.buffer[(start + i) % this.capacity] as T
      if (getTimestamp(item) > cutoff) break
      evicted++
    }

    if (evicted === 0) return 0
    if (evicted === this._size) {
      this.clear()
      return evicted
    }

    // Compact: shift remaining items to the front
    const remaining = this._size - evicted
    const newStart = (start + evicted) % this.capacity
    const newBuffer = new Array<T | undefined>(this.capacity)
    for (let i = 0; i < remaining; i++) {
      newBuffer[i] = this.buffer[(newStart + i) % this.capacity]
    }
    this.buffer = newBuffer
    this.head = remaining
    this._size = remaining

    return evicted
  }

  /** Clear all items. */
  clear(): void {
    this.buffer = new Array(this.capacity)
    this.head = 0
    this._size = 0
  }

  /** Get the most recent item, or undefined if empty. */
  peek(): T | undefined {
    if (this._size === 0) return undefined
    const idx = (this.head - 1 + this.capacity) % this.capacity
    return this.buffer[idx]
  }
}
