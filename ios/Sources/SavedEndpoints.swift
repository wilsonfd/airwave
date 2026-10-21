import Foundation

struct SavedEndpoint: Codable, Identifiable, Equatable {
    let host: String
    let port: Int
    var lastUsed: Date

    var id: String {
        "\(host.lowercased()):\(port)"
    }

    var displayAddress: String {
        "\(host):\(port)"
    }
}

enum SavedEndpointsStore {
    static let key = "aw_saved_endpoints"
    static let maxCount = 8

    static func load() -> [SavedEndpoint] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let items = try? JSONDecoder().decode([SavedEndpoint].self, from: data) else {
            return []
        }
        return Array(items.sorted { $0.lastUsed > $1.lastUsed }.prefix(maxCount))
    }

    static func save(_ items: [SavedEndpoint]) {
        let trimmed = Array(items.sorted { $0.lastUsed > $1.lastUsed }.prefix(maxCount))
        if let data = try? JSONEncoder().encode(trimmed) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    /// Adds or refreshes an endpoint and moves it to the front.
    static func add(host: String, port: Int, to items: [SavedEndpoint]) -> [SavedEndpoint] {
        let cleaned = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty, (1024...65535).contains(port) else {
            return items
        }
        var next = items.filter {
            !($0.host.caseInsensitiveCompare(cleaned) == .orderedSame && $0.port == port)
        }
        next.insert(SavedEndpoint(host: cleaned, port: port, lastUsed: Date()), at: 0)
        return Array(next.prefix(maxCount))
    }

    static func remove(id: String, from items: [SavedEndpoint]) -> [SavedEndpoint] {
        items.filter { $0.id != id }
    }
}
