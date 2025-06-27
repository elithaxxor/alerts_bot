import SwiftUI
import Alamofire
import KeychainAccess
import Charts
import Combine

@main
struct CryptoScreenerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    var body: some Scene {
        MenuBarExtra("CryptoScreener") {
            ContentView()
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    let currentVersion = "1.0.0"
    var cancellables = Set<AnyCancellable>()

    func applicationDidFinishLaunching(_ notification: Notification) {
        checkForUpdate()
    }

    func checkForUpdate() {
        guard let url = URL(string: "https://example.com/crypto/version.json") else { return }
        URLSession.shared.dataTaskPublisher(for: url)
            .map { $0.data }
            .decode(type: [String: String].self, decoder: JSONDecoder())
            .replaceError(with: [:])
            .receive(on: RunLoop.main)
            .sink { info in
                if let latest = info["latest"], latest > currentVersion {
                    let alert = NSAlert()
                    alert.messageText = "Update Available"
                    alert.informativeText = "A newer version (\(latest)) is available."
                    alert.runModal()
                }
            }.store(in: &cancellables)
    }
}

struct PriceInfo: Identifiable {
    let id = UUID()
    let symbol: String
    let price: Double
    let change: Double
}

class WebSocketManager: ObservableObject {
    @Published var latestData: String = ""
    private var task: URLSessionWebSocketTask?

    func connect() {
        guard let url = URL(string: "ws://localhost:9999/ws/results") else { return }
        task = URLSession.shared.webSocketTask(with: url)
        task?.receive(completionHandler: handle)
        task?.resume()
    }

    private func handle(result: Result<URLSessionWebSocketTask.Message, Error>) {
        switch result {
        case .success(let msg):
            if case let .string(text) = msg {
                DispatchQueue.main.async { [weak self] in self?.latestData = text }
            }
            task?.receive(completionHandler: handle)
        case .failure:
            break
        }
    }
}

struct ContentView: View {
    @State private var prices: [PriceInfo] = []
    @State private var watchlist: [String] = NSUbiquitousKeyValueStore.default.array(forKey: "watchlist") as? [String] ?? ["BTC","ETH","SOL"]
    @StateObject private var ws = WebSocketManager()
    var body: some View {
        VStack(alignment: .leading) {
            Text("Dashboard").font(.title)
            List(prices) { info in
                HStack {
                    Text(info.symbol)
                    Spacer()
                    Text(String(format: "$%.2f", info.price))
                        .foregroundColor(info.change >= 0 ? .green : .red)
                }
            }
            .frame(width: 200, height: 150)
        }
        .onAppear {
            fetchPrices()
            ws.connect()
            NotificationCenter.default.addObserver(forName: NSUbiquitousKeyValueStore.didChangeExternallyNotification, object: nil, queue: .main) { _ in
                watchlist = NSUbiquitousKeyValueStore.default.array(forKey: "watchlist") as? [String] ?? watchlist
            }
            NSUbiquitousKeyValueStore.default.set(watchlist, forKey: "watchlist")
            NSUbiquitousKeyValueStore.default.synchronize()
        }
        .onReceive(ws.$latestData) { text in
            guard let data = text.data(using: .utf8),
                  let js = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let sc = js["screener"] as? [String: Any] else { return }
            // simple extract of first symbol price
            if let first = sc.first {
                let sym = first.key
                if let info = first.value as? [String: Any],
                   let window = info.values.first as? [String: Any],
                   let price = window["entry_price"] as? Double {
                    prices.insert(PriceInfo(symbol: sym, price: price, change: 0), at: 0)
                }
            }
        }
        .padding()
    }

    func fetchPrices() {
        let ids = watchlist.map { $0.lowercased() }.joined(separator: ",")
        let url = "https://api.coingecko.com/api/v3/simple/price?ids=\(ids)&vs_currencies=usd&include_24hr_change=true"
        AF.request(url)
            .responseDecodable(of: [String: [String: Double]].self) { response in
                if case let .success(data) = response.result {
                    prices = watchlist.map { sym in
                        let lower = sym.lowercased()
                        let p = data[lower]?["usd"] ?? 0
                        let ch = data[lower]?["usd_24h_change"] ?? 0
                        return PriceInfo(symbol: sym, price: p, change: ch)
                    }
                }
            }
    }
}
