import Foundation

/// Sequence-number buffer that tolerates reordering and packet loss.
///
/// It intentionally does not "sort" the whole array: audio only ever moves
/// forward, so an expected-sequence pointer plus a dictionary is both simpler
/// and cheaper on a real-time path.
struct PacketJitterBuffer {
    private(set) var packets: [UInt32: Data] = [:]
    private(set) var expected: UInt32 = 0
    private(set) var primed = false
    private(set) var started = false
    var maxPackets = 120

    func contains(_ seq: UInt32) -> Bool {
        packets[seq] != nil
    }

    var count: Int { packets.count }

    static func isBefore(_ a: UInt32, _ b: UInt32) -> Bool {
        Int32(bitPattern: a &- b) < 0
    }

    /// Signed distance from a to b, taking 32-bit wraparound into account.
    static func distance(from a: UInt32, to b: UInt32) -> Int {
        Int(Int32(bitPattern: b &- a))
    }

    mutating func reset() {
        packets.removeAll(keepingCapacity: true)
        expected = 0
        primed = false
        started = false
    }

    mutating func start(at seq: UInt32) {
        reset()
        expected = seq
        started = true
    }

    mutating func insert(seq: UInt32, pcm: Data) {
        if !started {
            start(at: seq)
        }
        if primed && Self.isBefore(seq, expected) {
            return
        }
        packets[seq] = pcm

        if packets.count > maxPackets {
            let keys = packets.keys.sorted { Self.isBefore($0, $1) }
            for key in keys.prefix(packets.count - maxPackets) {
                packets.removeValue(forKey: key)
            }
        }
    }

    /// Returns true once the pre-buffer target has been reached.
    @discardableResult
    mutating func primeIfReady(_ target: Int) -> Bool {
        if !primed && packets.count >= max(1, target) {
            primed = true
        }
        return primed
    }

    mutating func forcePrime() {
        primed = true
    }

    mutating func unprime() {
        primed = false
    }

    func peekExpected() -> Data? {
        packets[expected]
    }

    mutating func consumeExpected() -> Data? {
        guard let data = packets.removeValue(forKey: expected) else { return nil }
        expected = expected &+ 1
        return data
    }

    /// Advance past a packet that never arrived (only used when the player has
    /// already drained and we must recover instead of stalling forever).
    mutating func skipExpected() {
        packets.removeValue(forKey: expected)
        expected = expected &+ 1
    }
}
