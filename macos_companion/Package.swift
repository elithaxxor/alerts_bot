// swift-tools-version:5.7
import PackageDescription

let package = Package(
    name: "CryptoScreenerApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "CryptoScreenerApp", targets: ["CryptoScreenerApp"])
    ],
    dependencies: [
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.6.4"),
        .package(url: "https://github.com/kishikawakatsumi/KeychainAccess.git", from: "4.2.2"),
        .package(url: "https://github.com/apple/swift-charts.git", from: "1.0.0"),
    ],
    targets: [
        .executableTarget(
            name: "CryptoScreenerApp",
            dependencies: ["Alamofire", "KeychainAccess", .product(name: "Charts", package: "swift-charts")],
            path: "Sources/CryptoScreenerApp"
        )
    ]
)
