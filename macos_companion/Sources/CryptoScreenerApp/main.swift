import SwiftUI
import Alamofire
import KeychainAccess
import Charts

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
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Setup code if needed
    }
}

struct PriceInfo: Identifiable {
    let id = UUID()
    let symbol: String
    let price: Double
    let change: Double
}

struct ContentView: View {
    @State private var prices: [PriceInfo] = []
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
        .onAppear(perform: fetchPrices)
        .padding()
    }

    func fetchPrices() {
        AF.request("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true")
            .responseDecodable(of: [String: [String: Double]].self) { response in
                if case let .success(data) = response.result {
                    prices = [
                        PriceInfo(symbol: "BTC", price: data["bitcoin"]?["usd"] ?? 0, change: data["bitcoin"]?["usd_24h_change"] ?? 0),
                        PriceInfo(symbol: "ETH", price: data["ethereum"]?["usd"] ?? 0, change: data["ethereum"]?["usd_24h_change"] ?? 0),
                        PriceInfo(symbol: "SOL", price: data["solana"]?["usd"] ?? 0, change: data["solana"]?["usd_24h_change"] ?? 0)
                    ]
                }
            }
    }
}
