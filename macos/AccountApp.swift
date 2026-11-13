import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var service: Process?
    var baseURL: URL?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let icon = Bundle.main.url(forResource: "AccountPanel", withExtension: "icns") {
            NSApp.applicationIconImage = NSImage(contentsOf: icon)
        }
        let menu = NSMenu()
        let item = NSMenuItem()
        menu.addItem(item)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "退出 Claude 账号面板", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = appMenu
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 720), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Claude 账号面板"
        window.minSize = NSSize(width: 390, height: 420)
        window.setFrameAutosaveName("ClaudeAccountPanel")
        window.collectionBehavior = [.fullScreenPrimary]
        web = WKWebView(frame: window.contentView!.bounds)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        window.contentView = web
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startService()
    }

    func startService() {
        guard let resources = Bundle.main.resourceURL,
              let config = NSDictionary(contentsOf: resources.appendingPathComponent("Runtime.plist")),
              let python = config["Python"] as? String,
              let cswap = config["Cswap"] as? String else {
            showError("App 文件不完整，请重新构建。"); return
        }
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [resources.appendingPathComponent("account_app.py").path, "--port", "0", "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = URL(fileURLWithPath: cswap).deletingLastPathComponent().path + ":" + (env["PATH"] ?? "/usr/bin:/bin")
        process.environment = env
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        service = process
        do { try process.run() } catch { showError("无法启动本机服务，请检查 Python 安装。"); return }
        DispatchQueue.global().async { [weak self] in
            let data = pipe.fileHandleForReading.availableData
            let value = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            DispatchQueue.main.async {
                guard let self = self else { return }
                guard let url = URL(string: value), url.scheme == "http", url.host == "127.0.0.1", url.port != nil else {
                    self.showError("本机服务启动失败，请重新打开 App。"); return
                }
                self.baseURL = url
                self.web.load(URLRequest(url: url))
            }
        }
    }

    func showError(_ text: String) {
        let alert = NSAlert()
        alert.messageText = "无法打开账号面板"
        alert.informativeText = text
        alert.runModal()
        NSApp.terminate(nil)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        let allowed = url?.scheme == "http" && url?.host == "127.0.0.1" && url?.port == baseURL?.port
        decisionHandler(allowed ? .allow : .cancel)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        if let process = service, process.isRunning { process.terminate() }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
