#!/usr/bin/env swift
// voice-helper: listens on Unix socket, records + transcribes via SFSpeechRecognizer,
// types result into frontmost app via CGEvent keyboard simulation.
// Run in user GUI session (Login Item or manually).

import Foundation
import Speech
import AVFoundation
import AppKit

let SOCK_PATH = NSHomeDirectory() + "/.open-buddy/voice.sock"
let LOG_PATH  = "/tmp/open-buddy-voice.log"

func log(_ msg: String) {
    let ts = ISO8601DateFormatter().string(from: Date())
    let line = "\(ts) \(msg)\n"
    print(line, terminator: "")
    if let fh = FileHandle(forWritingAtPath: LOG_PATH) {
        fh.seekToEndOfFile()
        fh.write(line.data(using: .utf8)!)
        fh.closeFile()
    }
}

// ── Dictation pill overlay ────────────────────────────────────────────────────
class DictationOverlay {
    var panel: NSPanel?
    var dotTimer: Timer?
    var dotPhase = 0

    func show() {
        DispatchQueue.main.async { self._show() }
    }

    func hide() {
        DispatchQueue.main.async { self._hide() }
    }

    private func _show() {
        _hide()  // clean up any existing

        let W: CGFloat = 120, H: CGFloat = 36
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let sf = screen.frame
        // Position: bottom-center, 80px above dock area
        let x = sf.midX - W / 2
        let y = sf.minY + 80

        let p = NSPanel(
            contentRect: NSRect(x: x, y: y, width: W, height: H),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        p.isOpaque = false
        p.backgroundColor = .clear
        p.level = .screenSaver
        p.ignoresMouseEvents = true
        p.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]

        let view = DictationPillView(frame: NSRect(x: 0, y: 0, width: W, height: H))
        p.contentView = view
        p.orderFrontRegardless()
        panel = p

        // Animate dots
        dotPhase = 0
        dotTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            self.dotPhase = (self.dotPhase + 1) % 4
            (self.panel?.contentView as? DictationPillView)?.dotPhase = self.dotPhase
            self.panel?.contentView?.needsDisplay = true
        }
    }

    private func _hide() {
        dotTimer?.invalidate()
        dotTimer = nil
        panel?.orderOut(nil)
        panel = nil
    }
}

class DictationPillView: NSView {
    var dotPhase: Int = 0

    override func draw(_ dirtyRect: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }

        let W = bounds.width, H = bounds.height
        let r = H / 2

        // Shadow
        ctx.setShadow(offset: CGSize(width: 0, height: -2), blur: 8,
                      color: NSColor.black.withAlphaComponent(0.35).cgColor)

        // Green pill
        let pillPath = NSBezierPath(roundedRect: bounds, xRadius: r, yRadius: r)
        NSColor(red: 0.13, green: 0.78, blue: 0.35, alpha: 1.0).setFill()
        pillPath.fill()

        ctx.setShadow(offset: .zero, blur: 0, color: nil)

        // Mic icon (centered)
        let micW: CGFloat = 10, micH: CGFloat = 14
        let mx = (W - micW) / 2
        let my = (H - micH) / 2
        NSColor.white.setFill()

        // Mic body capsule
        let bodyPath = NSBezierPath(roundedRect: NSRect(x: mx + 2, y: my + 5, width: 6, height: 8), xRadius: 3, yRadius: 3)
        bodyPath.fill()

        // Mic arc
        let arcPath = NSBezierPath()
        arcPath.lineWidth = 1.5
        NSColor.white.setStroke()
        arcPath.appendArc(withCenter: NSPoint(x: mx + 5, y: my + 12),
                          radius: 5, startAngle: 0, endAngle: 180, clockwise: true)
        arcPath.stroke()

        // Mic stand
        let standPath = NSBezierPath()
        standPath.lineWidth = 1.5
        standPath.move(to: NSPoint(x: mx + 5, y: my + 7))
        standPath.line(to: NSPoint(x: mx + 5, y: my + 4))
        standPath.stroke()

        // Base line
        let basePath = NSBezierPath()
        basePath.lineWidth = 1.5
        basePath.move(to: NSPoint(x: mx + 2, y: my + 4))
        basePath.line(to: NSPoint(x: mx + 8, y: my + 4))
        basePath.stroke()

        // Animated dots: 2 on each side
        let dotR: CGFloat = 2.5
        let dotY = H / 2
        let dotSpacing: CGFloat = 7
        let micCenterX = W / 2

        for i in 0..<2 {
            let alpha: CGFloat = (dotPhase > i) ? 1.0 : 0.35
            NSColor.white.withAlphaComponent(alpha).setFill()
            // Left dots
            let lx = micCenterX - 14 - CGFloat(i) * dotSpacing
            NSBezierPath(ovalIn: NSRect(x: lx - dotR, y: dotY - dotR, width: dotR*2, height: dotR*2)).fill()
            // Right dots
            let rx = micCenterX + 14 + CGFloat(i) * dotSpacing
            NSBezierPath(ovalIn: NSRect(x: rx - dotR, y: dotY - dotR, width: dotR*2, height: dotR*2)).fill()
        }
    }
}

// ── Typing via CGEvent ────────────────────────────────────────────────────────
func typeString(_ text: String) {
    let src = CGEventSource(stateID: .hidSystemState)
    for scalar in text.unicodeScalars {
        var u = UniChar(scalar.value & 0xFFFF)
        guard let e = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: true) else { continue }
        e.keyboardSetUnicodeString(stringLength: 1, unicodeString: &u)
        e.post(tap: .cghidEventTap)
        guard let up = e.copy() else { continue }
        up.type = .keyUp
        up.post(tap: .cghidEventTap)
        Thread.sleep(forTimeInterval: 0.005)
    }
}

// ── Speech recognition ────────────────────────────────────────────────────────
let overlay = DictationOverlay()

class Recognizer: NSObject, SFSpeechRecognizerDelegate {
    let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))!
    var audioEngine = AVAudioEngine()
    var request: SFSpeechAudioBufferRecognitionRequest?
    var task: SFSpeechRecognitionTask?
    var isRecording = false
    var onResult: ((String) -> Void)?

    func start(completion: @escaping (String) -> Void) {
        guard !isRecording else { return }
        SFSpeechRecognizer.requestAuthorization { status in
            guard status == .authorized else { log("speech auth denied"); return }
            DispatchQueue.main.async { self._start(completion: completion) }
        }
    }

    private func _start(completion: @escaping (String) -> Void) {
        onResult = completion
        request = SFSpeechAudioBufferRecognitionRequest()
        request!.shouldReportPartialResults = false

        let input = audioEngine.inputNode
        let fmt = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: fmt) { buf, _ in
            self.request?.append(buf)
        }
        try? audioEngine.start()
        isRecording = true
        log("recording started")
        overlay.show()

        task = recognizer.recognitionTask(with: request!) { result, error in
            if let r = result, r.isFinal {
                let text = r.bestTranscription.formattedString
                log("transcribed: \(text)")
                completion(text)
            }
        }
    }

    func stop() {
        guard isRecording else { return }
        isRecording = false
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
        request?.endAudio()
        overlay.hide()
        log("recording stopped")
    }
}

// ── Socket server ─────────────────────────────────────────────────────────────
let recognizer = Recognizer()

func handleCommand(_ cmd: String) {
    let c = cmd.trimmingCharacters(in: .whitespacesAndNewlines)
    log("cmd: \(c)")
    if c == "start" {
        recognizer.start { text in
            guard !text.isEmpty else { return }
            DispatchQueue.main.async { typeString(text) }
        }
    } else if c == "stop" {
        recognizer.stop()
    }
}

// Remove stale socket
try? FileManager.default.removeItem(atPath: SOCK_PATH)
FileManager.default.createFile(atPath: LOG_PATH, contents: nil)

let server = socket(AF_UNIX, SOCK_STREAM, 0)
var addr = sockaddr_un()
addr.sun_family = sa_family_t(AF_UNIX)
withUnsafeMutablePointer(to: &addr.sun_path) { ptr in
    SOCK_PATH.withCString { cstr in
        UnsafeMutableRawPointer(ptr).copyMemory(from: cstr, byteCount: SOCK_PATH.utf8.count + 1)
    }
}
let bindResult = withUnsafePointer(to: &addr) {
    $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(server, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
}
guard bindResult == 0 else { log("bind failed"); exit(1) }
listen(server, 5)
chmod(SOCK_PATH, 0o600)
log("voice-helper listening on \(SOCK_PATH)")

// Accept loop in background thread
Thread.detachNewThread {
    while true {
        let client = accept(server, nil, nil)
        guard client >= 0 else { continue }
        var buf = [UInt8](repeating: 0, count: 64)
        let n = read(client, &buf, 63)
        if n > 0 {
            let cmd = String(bytes: buf[0..<n], encoding: .utf8) ?? ""
            DispatchQueue.main.async { handleCommand(cmd) }
        }
        close(client)
    }
}

// Run main loop (required for Speech framework + CGEvent + NSPanel)
NSApplication.shared.run()
