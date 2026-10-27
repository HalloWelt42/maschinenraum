// Menüleistensymbol des Maschinenraums: zeigt die KI-Dienste dieses Rechners mit Zustand und Speicher und öffnet die
// Weboberflächen (Maschinenraum, Steuerprogramme wie das Stellwerk, Leitstelle). Es schaltet nichts: KI-Dienste
// startet und hält der Maschinenraum (Oberfläche, Leitstelle), Apps das Stellwerk in seiner eigenen Oberfläche.
// Jeder Knopf trägt den Namen, den die Oberfläche in ihrem Manifest selbst nennt (Name mit Kurzzweck, etwa
// "Leitstelle · KI-Vermittlung"); bis das Manifest gelesen ist oder wenn es fehlt, den bekannten Namen.

import AppKit
import SwiftUI

struct Messwerte: Decodable {
    let speicher_gesamt_gb: Double
    let speicher_belegt_gb: Double
    let swap_belegt_gb: Double?
    let swap_gesamt_gb: Double?
}

struct Dienst: Decodable, Identifiable {
    let kennung: String
    let name: String
    let zustand: String
    let gb_jetzt: Double?
    let bedarf_gb: Double
    let aktiv: Bool
    var id: String { kennung }
    var laeuft: Bool { zustand == "laeuft" || zustand == "startet" || zustand == "stoppt" }
}

struct Leitstelle: Decodable { let adresse: String? }

// Steuerprogramm des Rechners (etwa das Stellwerk); hier nur, um seine Oberfläche zu öffnen, solange es läuft
struct Steuerprogramm: Decodable, Identifiable {
    let kennung: String
    let name: String
    let zustand: String
    let oberflaeche: String?
    var id: String { kennung }
}

struct Manifest: Decodable { let name: String }

struct Stand: Decodable {
    let rechner: String
    let messwerte: Messwerte?
    let dienste: [Dienst]
    let betrieb: [Steuerprogramm]
    let leitstelle: Leitstelle
}

@MainActor
final class Modell: ObservableObject {
    @Published var stand: Stand?
    @Published var erreichbar = true
    @Published var namen: [String: String] = [:]          // Adresse einer Oberfläche -> Name aus ihrem Manifest
    let basis: URL
    private var zeitgeber: Timer?
    private var namenGelesen = Date.distantPast
    private var namenFuer: [String] = []                   // die Adressen beim letzten Lesen der Manifeste
    private let namenAbstand: TimeInterval = 60           // so oft werden die Manifeste neu gelesen, sonst bei neuen Adressen

    init() {
        let port = Bundle.main.object(forInfoDictionaryKey: "MaschinenraumPort") as? Int ?? 8540
        basis = URL(string: "http://127.0.0.1:\(port)")!
        zeitgeber = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.holen() }
        }
        Task { await holen() }
    }

    func holen() async {
        do {
            let (daten, _) = try await URLSession.shared.data(from: basis.appendingPathComponent("api/stand"))
            stand = try JSONDecoder().decode(Stand.self, from: daten)
            erreichbar = true
        } catch {
            erreichbar = false
        }
        let adressen = [basis.absoluteString] + oberflaechen.map(\.adresse) + [stand?.leitstelle.adresse].compactMap { $0 }
        if adressen != namenFuer || Date().timeIntervalSince(namenGelesen) >= namenAbstand {
            namenFuer = adressen
            namenGelesen = Date()
            await namenHolen(adressen)
        }
    }

    // Name jeder Oberfläche aus ihrem Manifest (site.webmanifest); eine, die nicht antwortet, behält den letzten
    func namenHolen(_ adressen: [String]) async {
        for a in adressen {
            guard let url = URL(string: a)?.appendingPathComponent("site.webmanifest") else { continue }
            if let (daten, _) = try? await URLSession.shared.data(from: url), let m = try? JSONDecoder().decode(Manifest.self, from: daten) {
                namen[a] = m.name
            }
        }
    }

    func name(_ adresse: String, sonst: String) -> String { namen[adresse] ?? sonst }

    // Oberflächen der Steuerprogramme, die gerade laufen
    var oberflaechen: [(name: String, adresse: String)] {
        (stand?.betrieb ?? []).compactMap { p in p.zustand == "laeuft" ? p.oberflaeche.map { (p.name, $0) } : nil }
    }

    func oeffnen(_ adresse: String) {
        if let url = URL(string: adresse) { NSWorkspace.shared.open(url) }
    }
}

func gb(_ wert: Double) -> String {
    wert < 1 ? "\(Int((wert * 1024).rounded())) MB" : String(format: "%.1f GB", wert).replacingOccurrences(of: ".", with: ",")
}

struct Ansicht: View {
    @ObservedObject var modell: Modell

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(modell.name(modell.basis.absoluteString, sonst: "Maschinenraum")).font(.headline)
                Spacer()
                if let s = modell.stand { Text(s.rechner).foregroundStyle(.secondary) }
            }
            if !modell.erreichbar {
                Label("Der Maschinenraum antwortet nicht.", systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if let m = modell.stand?.messwerte {
                VStack(alignment: .leading, spacing: 4) {
                    HStack { Text("Speicher"); Spacer(); Text("\(gb(m.speicher_belegt_gb)) von \(gb(m.speicher_gesamt_gb))").monospacedDigit() }
                    ProgressView(value: min(1, m.speicher_belegt_gb / max(1, m.speicher_gesamt_gb)))
                    if let s = m.swap_belegt_gb, let g = m.swap_gesamt_gb, g > 0 {
                        HStack { Text("Auslagerung"); Spacer(); Text("\(gb(s)) von \(gb(g))").monospacedDigit() }.foregroundStyle(.secondary)
                    }
                }
            }
            Divider()
            Text("KI-Dienste").font(.caption).foregroundStyle(.secondary)
            if let dienste = modell.stand?.dienste, !dienste.isEmpty {
                ForEach(dienste) { d in
                    HStack(spacing: 8) {
                        Circle().fill(d.zustand == "gestoert" ? Color.red : d.laeuft ? Color.green : Color.gray.opacity(0.5)).frame(width: 9, height: 9)
                        Text(d.name).lineLimit(1)
                        Spacer()
                        if d.aktiv { Image(systemName: "gearshape.fill").foregroundStyle(.orange).help("arbeitet gerade") }
                        if let jetzt = d.gb_jetzt { Text(gb(jetzt)).monospacedDigit().foregroundStyle(.secondary).help("Bedarf \(gb(d.bedarf_gb))") }
                    }
                }
            } else {
                Text("Keine KI-Dienste eingetragen.").foregroundStyle(.secondary)
            }
            Divider()
            // Je Oberfläche ein Knopf in eigener Zeile: Name und Kurzzweck sind zu lang für eine Reihe
            VStack(alignment: .leading, spacing: 6) {
                oeffnenKnopf(modell.basis.absoluteString, sonst: "Maschinenraum", hilfe: "Weboberfläche des Maschinenraums öffnen: KI-Dienste starten, anhalten, Protokolle")
                ForEach(modell.oberflaechen, id: \.adresse) { o in
                    oeffnenKnopf(o.adresse, sonst: o.name, hilfe: "Weboberfläche von \(o.name) öffnen")
                }
                if let adresse = modell.stand?.leitstelle.adresse {
                    oeffnenKnopf(adresse, sonst: "Leitstelle", hilfe: "Leitstelle öffnen: zentrale Steuerung und Überwachung")
                }
            }
            HStack {
                Spacer()
                Button("Symbol beenden") { NSApplication.shared.terminate(nil) }
                    .help("Beendet nur dieses Symbol; Maschinenraum, Stellwerk und alle Dienste laufen weiter")
            }
        }
        .padding(14)
        .frame(width: 340)
    }

    func oeffnenKnopf(_ adresse: String, sonst: String, hilfe: String) -> some View {
        Button { modell.oeffnen(adresse) } label: { Label(modell.name(adresse, sonst: sonst), systemImage: "arrow.up.right.square") }
            .buttonStyle(.borderless).help(hilfe)
    }
}

@main
struct MaschinenraumMenue: App {
    @StateObject private var modell = Modell()

    var body: some Scene {
        MenuBarExtra {
            Ansicht(modell: modell)
        } label: {
            let laufen = modell.stand?.dienste.filter { $0.laeuft }.count ?? 0
            Image(systemName: modell.erreichbar ? "gearshape.2" : "gearshape.2.fill")
            if laufen > 0 { Text("\(laufen)") }
        }
        .menuBarExtraStyle(.window)
    }
}
